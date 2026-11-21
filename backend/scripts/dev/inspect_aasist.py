"""Read-only architecture probe for the official AASIST model used by DeepTrace.

Run with the model virtualenv, for example:

  backend/.venv-models/bin/python backend/scripts/dev/inspect_aasist.py \
    --repo backend/vendor/aasist \
    --weights backend/models/aasist/AASIST.pth

Prints module names and tensor shapes for one 64600-sample waveform.
Does not write checkpoints or modify vendor source. Attention-map shapes are
captured by a temporary wrapper around _derive_att_map inside this process.
"""
import argparse
import importlib
import json
import sys
from pathlib import Path


def shape(value):
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return [shape(item) for item in value]
    if hasattr(value, "shape"):
        return list(value.shape)
    return str(type(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--variant", choices=["aasist", "aasist-l"], default="aasist")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    repo = args.repo.resolve()
    name = "AASIST-L" if args.variant == "aasist-l" else "AASIST"
    config = json.loads((repo / "config" / (name + ".conf")).read_text())["model_config"]
    sys.path.insert(0, str(repo))
    import torch

    module = importlib.import_module("models." + config["architecture"])
    model = module.Model(config).to(args.device)
    state = torch.load(str(args.weights), map_location="cpu", weights_only=True)
    state = state.get("state_dict", state)
    model.load_state_dict({key.removeprefix("module."): value for key, value in state.items()}, strict=True)
    model.eval()

    print("modules")
    for module_name, submodule in model.named_modules():
        print(f"{module_name or '<root>'}\t{type(submodule).__name__}")

    captured = {}
    attention = {}

    def save(label):
        def hook(_module, _inputs, output):
            captured[label] = output
        return hook

    watched = [
        "conv_time",
        "first_bn",
        "encoder",
        "GAT_layer_S",
        "GAT_layer_T",
        "pool_S",
        "pool_T",
        "HtrgGAT_layer_ST11",
        "HtrgGAT_layer_ST12",
        "HtrgGAT_layer_ST21",
        "HtrgGAT_layer_ST22",
        "pool_hS1",
        "pool_hT1",
        "pool_hS2",
        "pool_hT2",
        "out_layer",
    ]
    hooks = [getattr(model, label).register_forward_hook(save(label)) for label in watched]

    originals = {}

    def wrap(label, layer):
        original = layer._derive_att_map
        originals[label] = (layer, original)

        def wrapped(*inner_args, **inner_kwargs):
            att_map = original(*inner_args, **inner_kwargs)
            attention[label] = list(att_map.shape)
            return att_map

        layer._derive_att_map = wrapped

    for label in ("GAT_layer_S", "GAT_layer_T", "HtrgGAT_layer_ST11", "HtrgGAT_layer_ST12", "HtrgGAT_layer_ST21", "HtrgGAT_layer_ST22"):
        wrap(label, getattr(model, label))

    waveform = torch.randn(1, 64600, device=args.device, requires_grad=True)
    last_hidden, logits = model(waveform)
    logits[0, 0].backward()
    for hook in hooks:
        hook.remove()
    for layer, original in originals.values():
        layer._derive_att_map = original

    report = {
        "class": "models.AASIST.Model",
        "variant": name,
        "checkpoint_loaded_strict": True,
        "config": config,
        "input_shape": shape(waveform),
        "module_output_shapes": {label: shape(captured[label]) for label in watched},
        "attention_map_shapes": attention,
        "last_hidden_shape": shape(last_hidden),
        "logits_shape": shape(logits),
        "out_layer": {
            "module": "out_layer",
            "in_features": model.out_layer.in_features,
            "out_features": model.out_layer.out_features,
        },
        "pos_S_shape": shape(model.pos_S),
        "spoof_logit_grad_reaches_waveform": bool(waveform.grad is not None and waveform.grad.abs().sum().item() > 0),
        "attention_returned_by_forward": False,
    }
    print("PROBE_JSON")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
