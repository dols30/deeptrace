# Video attribution plan

Date: 2026-09-30. This plan uses the DeepfakeBench EfficientNet-B4 checkpoint DeepTrace already loads. Measured shapes come from `backend/scripts/dev/inspect_efficientnetb4.py`. The method split is Grad-CAM for the investigator picture and occlusion to test that picture.

## Architecture trace

```text
sampled JPEG
  -> largest dlib face
  -> five-point similarity warp, 256x256 aligned crop
  -> (RGB / 255 - 0.5) / 0.5
  -> efficientnet._conv_stem          Conv2d 3 -> 48, kernel 3, stride 2, padding 0
  -> efficientnet._bn0, _swish
  -> efficientnet._blocks[0:32]       32 MBConv blocks
  -> efficientnet._conv_head          Conv2d 448 -> 1792, kernel 1
  -> efficientnet._bn1, _swish        this tensor is EfficientNetB4.features
  -> adaptive_avg_pool2d to 1x1
  -> flatten to 1792
  -> last_layer                       Linear 1792 -> 2
  -> softmax index 1                  fake-class screening score
```

`EfficientNetB4.features` calls `self.efficientnet.extract_features`. `extract_features` in the installed `efficientnet_pytorch` (`model.py`, `EfficientNet.extract_features`) ends with:

```text
x = self._swish(self._bn1(self._conv_head(x)))
return x
```

`EfficientNetB4.classifier` then pools that tensor and applies `last_layer`. Dropout is off (`dropout=False` in the runner config, matching `efficientnetb4.yaml`).

`block_part1`, `block_part2`, and `block_part3` exist on the class and are not called by `forward`. `forward` is `classifier(features(x))`.

## Grad-CAM target

Verified on `effnb4_best.pth` with a `(1, 3, 256, 256)` tensor, strict `load_state_dict`, and a backward from logit index 1:

| Quantity | Measured value |
| --- | --- |
| MBConv blocks | 32 (`efficientnet._blocks`) |
| Last convolution module | `efficientnet._conv_head` |
| `_conv_head` output | `(1, 1792, 8, 8)` |
| Map that enters pooling | `EfficientNetB4.features`, also `(1, 1792, 8, 8)` |
| Logits | `(1, 2)` |
| Gradient reaches the 8x8 map | yes |
| Gradient reaches input pixels | yes |

The module to associate with the map is the output of `EfficientNetB4.features`. `_conv_head` is the last convolution, and its grid is the same 8x8, but batch-norm and Swish still sit between that convolution and the pooling layer. Grad-CAM should weight the post-Swish activations, because those are the activations `adaptive_avg_pool2d` reads.

There is no single `nn.Module` whose `forward` return value is that post-Swish tensor. `extract_features` applies `_swish` as a function after `_bn1`. A Captum `LayerGradCam` hook on `_conv_head` or `_bn1` would be a different tensor. The implementation should retain the `features` tensor (as the probe does with `retain_grad`) or register a hook that runs after `extract_features`. Do not point a generic EfficientNet-B0/B4 tutorial at `features[8]` or at a 380px torchvision model.

Attributed scalar for the gradient: logit index 1 (fake). The number shown next to the picture remains `softmax(logits)[1]`, the screening score. The artifact records both.

`torch.inference_mode()` in `efficientnetb4.py` stays on the score-only path. The explain forward is a separate call with autograd enabled and `model.eval()`.

## Coordinate chain

The face step is `extract_aligned_face_dlib` in `backend/vendor/DeepfakeBench/preprocessing/preprocess.py`, called with `res=256`.

```text
sampled JPEG coordinates
  -> dlib rectangle of the largest face
  -> five landmarks: predictor parts 37, 44, 30, 49, 55
  -> SimilarityTransform onto the 112-template scaled to 256 with scale 1.3
  -> M, shape 2x3, from tform.params[0:2, :]
  -> cv2.warpAffine to 256x256
  -> second dlib detect (gate only; it does not change M)
  -> model tensor (1, 3, 256, 256)
  -> Grad-CAM (1, 8, 8) on features
  -> resize to (256, 256) on the aligned crop
  -> inverse of M back onto the sampled JPEG
```

`img_align_crop` builds `M` and does not return it. The runner keeps the crop and drops the landmarks. An overlay that resizes the 8x8 map onto the JPEG without `M` will paint the wrong pixels. The warp is a similarity transform, not a square crop of the dlib rectangle.

What to persist per scored frame:

- Sampled JPEG name and the timestamp `(frame_number - 1) * frame_interval_seconds`. This is the ffmpeg sample, not a source-frame index from the original container.
- JPEG width and height.
- The five source landmarks and `M` (six floats).
- A flag that the second detect succeeded.
- Model input spatial size, 256.
- Heatmap spatial size, 8.
- The resize used to paint the crop (bilinear onto 256x256).
- The inverse warp used if a full-frame overlay is stored.

The investigator default is the aligned face, side by side with the same crop plus the heatmap. That pair does not depend on a successful inverse. The full-frame overlay is optional and must use the inverse warp.

Unalignable frames stay unscored. They do not get a blank "real" map.

## Occlusion as validation

Occlusion runs on the same normalized 256x256 tensor.

- Fill value is recorded. Zero in this normalized space is mid-gray (pixel 0.5), because the runner stores `(pixel - 0.5) / 0.5`.
- Score delta uses `softmax[:, 1]`, so it is in the same units as the screening score.
- The check is statistical across frames: high Grad-CAM regions move that softmax more than low Grad-CAM regions. One frame that looks sharp is not enough.
- Occlusion is not the default image in the UI.

## What a frame map does not explain

The video screening score is the unweighted mean of per-frame fake softmaxes. Each heatmap is evidence about one crop. The UI shows the frame screening score and the video screening score as separate numbers, plus the method name and the checkpoint id already produced by `checkpoint_id`.

Copy next to the picture: "Highlighted areas had greater influence on this model output."

## Implementation note for a later milestone

`grad_cam` in `backend/deeptrace/ml/attribution.py` is the Selvaraju reduction on in-memory lists. `EfficientNetB4Detector.explain` only succeeds when `feature_maps` and `gradients` are already on `DetectionResult.metadata`. The runner does not produce them. The later prototype should compute the map in the model process and return an artifact URI plus the coordinate record. It should not ship the 8x8 grid by hoping the API virtualenv imports torch.
