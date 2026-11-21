"""Read-only architecture probe for the DeepfakeBench EfficientNet-B4 used by DeepTrace.

Run with the model virtualenv, for example:

  backend/.venv-models/bin/python backend/scripts/dev/inspect_efficientnetb4.py \
    --repo backend/vendor/DeepfakeBench \
    --weights backend/models/efficientnetb4/effnb4_best.pth

Prints module names, the Grad-CAM candidate, and tensor shapes for a 1x3x256x256
input. Does not write checkpoints or modify vendor source.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shape(tensor):
    return list(tensor.shape)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo / "training"))
    import torch

    network = load_module("deeptrace_effnet_probe", repo / "training/networks/efficientnetb4.py")
    model = network.EfficientNetB4(dict(num_classes=2, inc=3, dropout=False, mode="Original", pretrained=False))
    state = torch.load(str(args.weights), map_location="cpu", weights_only=True)
    state = state.get("state_dict", state)
    state = {key.removeprefix("module."): value for key, value in state.items()}
    state = {key.removeprefix("backbone."): value for key, value in state.items()}
    model.load_state_dict(state, strict=True)
    model.to(args.device).eval()

    print("modules")
    for name, module in model.named_modules():
        print(f"{name or '<root>'}\t{type(module).__name__}")

    captured = {}

    def save(label):
        def hook(_module, _inputs, output):
            captured[label] = output.detach()
        return hook

    hooks = [
        model.efficientnet._conv_stem.register_forward_hook(save("conv_stem")),
        model.efficientnet._blocks[0].register_forward_hook(save("block_0")),
        model.efficientnet._blocks[9].register_forward_hook(save("block_9")),
        model.efficientnet._blocks[21].register_forward_hook(save("block_21")),
        model.efficientnet._blocks[-1].register_forward_hook(save("last_block")),
        model.efficientnet._conv_head.register_forward_hook(save("conv_head")),
        model.efficientnet._bn1.register_forward_hook(save("bn1")),
    ]
    image = torch.randn(1, 3, 256, 256, device=args.device, requires_grad=True)
    features = model.features(image)
    features.retain_grad()
    logits = model.classifier(features)
    logits[0, 1].backward()
    for hook in hooks:
        hook.remove()

    feature_grad = features.grad
    report = {
        "class": "EfficientNetB4",
        "backbone": "efficientnet_pytorch.EfficientNet.from_name('efficientnet-b4')",
        "checkpoint_loaded_strict": True,
        "mbconv_blocks": len(model.efficientnet._blocks),
        "conv_stem": {
            "module": "efficientnet._conv_stem",
            "in_channels": model.efficientnet._conv_stem.in_channels,
            "out_channels": model.efficientnet._conv_stem.out_channels,
            "kernel_size": list(model.efficientnet._conv_stem.kernel_size),
            "stride": list(model.efficientnet._conv_stem.stride),
            "output_shape": shape(captured["conv_stem"]),
        },
        "conv_head": {
            "module": "efficientnet._conv_head",
            "in_channels": model.efficientnet._conv_head.in_channels,
            "out_channels": model.efficientnet._conv_head.out_channels,
            "kernel_size": list(model.efficientnet._conv_head.kernel_size),
            "output_shape": shape(captured["conv_head"]),
        },
        "bn1_output_shape": shape(captured["bn1"]),
        "block_shapes": {
            "efficientnet._blocks.0": shape(captured["block_0"]),
            "efficientnet._blocks.9": shape(captured["block_9"]),
            "efficientnet._blocks.21": shape(captured["block_21"]),
            f"efficientnet._blocks.{len(model.efficientnet._blocks) - 1}": shape(captured["last_block"]),
        },
        "input_shape": shape(image),
        "features_module": "EfficientNetB4.features -> efficientnet.extract_features",
        "features_shape": shape(features),
        "features_grad_reaches_map": bool(feature_grad is not None and torch.isfinite(feature_grad).all() and feature_grad.abs().sum().item() > 0),
        "input_grad_reaches_pixels": bool(image.grad is not None and image.grad.abs().sum().item() > 0),
        "logits_shape": shape(logits),
        "last_layer": {
            "module": "last_layer",
            "in_features": model.last_layer.in_features,
            "out_features": model.last_layer.out_features,
        },
        "gradcam_target": (
            "Output of EfficientNetB4.features (swish(bn1(conv_head(x)))). "
            "efficientnet._conv_head is the last convolution; Grad-CAM should use the post-activation map that enters adaptive average pooling."
        ),
        "attributed_logit": 1,
    }
    print("PROBE_JSON")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
