"""AASIST explanations computed in the model process.

Temporal occlusion is the investigator record. Integrated gradients are binned
and compared with those windows. Graph attention is stored as shapes and pool
indices, not as a timeline.
"""
SAMPLE_RATE = 16000
ANALYZED_SAMPLES = 64600
WINDOW_SAMPLES = 8000
HOP_SAMPLES = 4000
FILLS = ("zeros", "local_mean", "low_level_noise")
DISPLAYED_FILL = "local_mean"
IG_BIN_SAMPLES = 800
OCCLUSION_BATCH = 3

ATTENTION_ROLES = {
    "GAT_layer_S": "Spectral nodes before pooling. This axis is not time.",
    "GAT_layer_T": "Encoder time nodes before GraphPool. Averaging this map does not produce seconds.",
    "HtrgGAT_layer_ST11": "Mixed temporal and spectral nodes after the first pool. Not a timeline.",
    "HtrgGAT_layer_ST21": "Mixed temporal and spectral nodes after the first pool. Not a timeline.",
    "HtrgGAT_layer_ST12": "Mixed nodes after the second pool. Not a timeline.",
    "HtrgGAT_layer_ST22": "Mixed nodes after the second pool. Not a timeline.",
}


def window_starts(length=ANALYZED_SAMPLES, window=WINDOW_SAMPLES, hop=HOP_SAMPLES):
    """Hop-aligned starts, plus a closing window when the tail would otherwise be left out."""
    if window > length or hop <= 0:
        raise ValueError("window must fit the analyzed span")
    starts = list(range(0, length - window + 1, hop))
    closing = length - window
    if closing not in starts:
        starts.append(closing)
    return starts


def mask_span(samples, start, end, fill, noise):
    """Return a copy with [start, end) replaced. noise is used only for low_level_noise."""
    masked = samples.copy()
    if fill == "zeros":
        masked[start:end] = 0
    elif fill == "local_mean":
        masked[start:end] = float(samples[start:end].mean())
    elif fill == "low_level_noise":
        masked[start:end] = noise
    else:
        raise ValueError(f"unknown fill {fill}")
    return masked


def top_indices(values, count=3):
    order = sorted(range(len(values)), key=lambda index: (values[index], -index), reverse=True)
    return order[:count]


def rankings_agree(series, count=3):
    """True when each fill's highest-delta windows are the same set."""
    if not series:
        return False
    tops = [set(top_indices(values, count)) for values in series]
    return all(item == tops[0] for item in tops)


def bin_attributions(values, sample_rate=SAMPLE_RATE, bin_samples=IG_BIN_SAMPLES):
    """Sum sample attributions into short bins. The sample vector is not returned."""
    bins = []
    for start in range(0, len(values), bin_samples):
        chunk = values[start:start + bin_samples]
        bins.append({
            "start": round(start / sample_rate, 6),
            "end": round((start + len(chunk)) / sample_rate, 6),
            "signed": round(float(sum(chunk)), 6),
            "absolute": round(float(sum(abs(item) for item in chunk)), 6),
        })
    return bins


def window_masses(values, starts, window=WINDOW_SAMPLES):
    return [round(float(sum(abs(item) for item in values[start:start + window])), 6) for start in starts]


def overlap_record(occlusion_deltas, ig_masses, starts, ig_baseline, occlusion_fill):
    occlusion_top = top_indices(occlusion_deltas)
    ig_top = top_indices(ig_masses)
    shared = set(occlusion_top) & set(ig_top)
    return {
        "ig_baseline": ig_baseline,
        "occlusion_fill": occlusion_fill,
        "top_occlusion_starts": [starts[index] for index in occlusion_top],
        "top_ig_starts": [starts[index] for index in ig_top],
        "shared_top_windows": len(shared),
        "top_sets_match": len(shared) == len(occlusion_top),
    }


def _round(value):
    return round(float(value), 6)


def explain_waveform(model, waveform, np, *, original_samples, ig_steps=8):
    """waveform is a (1, 64600) tensor on the model device. model.eval() is already set."""
    import torch

    if tuple(waveform.shape) != (1, ANALYZED_SAMPLES):
        raise ValueError("AASIST attribution expects the padded 64600-sample input")
    starts = window_starts()
    attention, pools = _capture_structure(model, torch, waveform)
    with torch.inference_mode():
        _, baseline_logits = model(waveform)
    if tuple(baseline_logits.shape) != (1, 2):
        raise ValueError("Expected two ASVspoof logits")
    baseline = float(torch.softmax(baseline_logits, dim=1)[0, 0])
    logits = [_round(item) for item in baseline_logits[0].tolist()]
    samples = waveform[0].detach().cpu().numpy()
    scale = max(1e-4, 0.05 * float(np.std(samples)))
    rng = np.random.default_rng(0)
    fill_deltas = {}
    for fill in FILLS:
        batch = []
        for start in starts:
            noise = rng.normal(0.0, scale, WINDOW_SAMPLES).astype(samples.dtype) if fill == "low_level_noise" else None
            masked = mask_span(samples, start, start + WINDOW_SAMPLES, fill, noise)
            batch.append(masked)
        tensor = torch.from_numpy(np.stack(batch)).to(waveform.device)
        chunks = []
        with torch.inference_mode():
            # AASIST's SincConv front end needs ~200 MB per 4 s clip; all windows at once exceed small containers.
            for chunk in tensor.split(OCCLUSION_BATCH):
                _, masked_logits = model(chunk)
                chunks.append(torch.softmax(masked_logits, dim=1)[:, 0].detach().cpu())
        masked_scores = torch.cat(chunks)
        fill_deltas[fill] = [_round(baseline - float(score)) for score in masked_scores]

    displayed = fill_deltas[DISPLAYED_FILL]
    windows = []
    for index, start in enumerate(starts):
        windows.append({
            "start": round(start / SAMPLE_RATE, 6),
            "end": round((start + WINDOW_SAMPLES) / SAMPLE_RATE, 6),
            "start_sample": start,
            "end_sample": start + WINDOW_SAMPLES,
            "score_delta": displayed[index],
            "fill": DISPLAYED_FILL,
        })
    gradients = _integrated_gradients(model, torch, waveform, samples, ig_steps)
    comparisons = []
    for ig_name, values in gradients.items():
        masses = window_masses(values, starts)
        for fill, deltas in fill_deltas.items():
            comparisons.append(overlap_record(deltas, masses, starts, ig_name, fill))
    return {
        "method": "temporal_occlusion",
        "target": "spoof_softmax_index_0",
        "baseline_spoof_softmax": _round(baseline),
        "logits": logits,
        "repeat_padded": original_samples < ANALYZED_SAMPLES,
        "truncated": original_samples > ANALYZED_SAMPLES,
        "original_samples": int(original_samples),
        "analyzed_end_seconds": ANALYZED_SAMPLES / SAMPLE_RATE,
        "displayed_fill": DISPLAYED_FILL,
        "noise_scale": _round(scale),
        "fill_rankings_agree": rankings_agree([fill_deltas[fill] for fill in FILLS]),
        "parameters": {
            "sample_rate": SAMPLE_RATE,
            "analyzed_samples": ANALYZED_SAMPLES,
            "window_samples": WINDOW_SAMPLES,
            "hop_samples": HOP_SAMPLES,
            "starts": starts,
            "fills": list(FILLS),
            "displayed_fill": DISPLAYED_FILL,
            "noise_scale": _round(scale),
            "noise_rule": "Gaussian, standard deviation 0.05 times the analyzed waveform, floor 0.0001, seed 0.",
            "score_delta": "baseline spoof softmax minus masked spoof softmax",
        },
        "windows": windows,
        "fills": fill_deltas,
        "integrated_gradients": {
            "available": True,
            "target": "spoof_logit_index_0",
            "endpoint_spoof_softmax": _round(baseline),
            "steps": ig_steps,
            "bin_samples": IG_BIN_SAMPLES,
            "baselines": {
                name: bin_attributions(values) for name, values in gradients.items()
            },
            "occlusion_comparison": comparisons,
            "role": "secondary experiment",
        },
        "attention": {
            "label": "internal model attention",
            "maps": attention,
            "pools": pools,
            "role": "research view",
        },
    }


def _capture_structure(model, torch, waveform):
    shapes = {}
    pools = []
    originals = []

    def wrap_attention(name, layer):
        original = layer._derive_att_map

        def wrapped(*args, **kwargs):
            att_map = original(*args, **kwargs)
            shapes[name] = list(att_map.shape)
            return att_map

        layer._derive_att_map = wrapped
        originals.append((layer, "_derive_att_map", original))

    for name in ATTENTION_ROLES:
        layer = getattr(model, name)
        wrap_attention(name, layer)
        if hasattr(layer, "_derive_att_map_master"):
            original = layer._derive_att_map_master

            def wrapped_master(*args, _name=name, _original=original, **kwargs):
                att_map = _original(*args, **kwargs)
                shapes[_name + "_master"] = list(att_map.shape)
                return att_map

            layer._derive_att_map_master = wrapped_master
            originals.append((layer, "_derive_att_map_master", original))

    def wrap_pool(name, layer):
        original = layer.top_k_graph

        def wrapped(scores, hidden, ratio):
            nodes = int(hidden.size(1))
            kept = max(int(nodes * ratio), 1)
            _, index = torch.topk(scores, kept, dim=1)
            pools.append({
                "name": name,
                "input_nodes": nodes,
                "kept": kept,
                "indices": [int(item) for item in index[0, :, 0].tolist()],
            })
            return original(scores, hidden, ratio)

        layer.top_k_graph = wrapped
        originals.append((layer, "top_k_graph", original))

    for name, layer in model.named_modules():
        if type(layer).__name__ == "GraphPool":
            wrap_pool(name, layer)
    try:
        with torch.inference_mode():
            model(waveform)
    finally:
        for layer, attr, original in originals:
            setattr(layer, attr, original)
    maps = [
        {"name": name, "shape": shapes.get(name), "role": role}
        for name, role in ATTENTION_ROLES.items()
    ]
    for name, shape in shapes.items():
        if name.endswith("_master"):
            maps.append({
                "name": name,
                "shape": shape,
                "role": "Master-node attention. Not a timeline.",
            })
    return maps, pools


def _integrated_gradients(model, torch, waveform, samples, steps):
    if steps < 1:
        raise ValueError("integrated gradient steps must be positive")
    mean = float(samples.mean())
    baselines = {
        "zeros": torch.zeros_like(waveform),
        "constant_mean": torch.full_like(waveform, mean),
    }
    attributed = {}
    for name, baseline in baselines.items():
        delta = waveform - baseline
        total = torch.zeros_like(waveform)
        for step in range(1, steps + 1):
            point = (baseline + (step / steps) * delta).detach().requires_grad_(True)
            model.zero_grad(set_to_none=True)
            _, logits = model(point)
            logits[0, 0].backward()
            total = total + point.grad.detach()
        attributed[name] = (delta * total / steps)[0].detach().cpu().tolist()
    return attributed
