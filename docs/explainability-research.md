# Explainability research

Research date: 2026-09-30. This note compares attribution methods against the models DeepTrace actually loads. The inference path, checkpoints, and measured shapes are in `docs/model-inference-audit.md`. Method-specific implementation notes are in `docs/video-attribution-plan.md` and `docs/aasist-attribution-plan.md`.

Attribution answers: which parts of the analyzed input most influenced this model output? It does not establish that a highlighted region was manipulated.

## Locked method split

```text
EfficientNet-B4
  Grad-CAM            primary visual explanation
  Occlusion           explanation validation

AASIST
  Temporal occlusion  primary investigator explanation
  Integrated gradients  secondary experiment
  Graph attention     advanced / research view
```

Time-frequency heatmaps are not in this split. The reason is below.

## Licenses that constrain what we copy

| Work | URL | License | Use in DeepTrace |
| --- | --- | --- | --- |
| DeepfakeBench | https://github.com/SCLBD/DeepfakeBench | CC BY-NC 4.0 (`backend/vendor/DeepfakeBench/LICENSE`) | Vendored detector and face alignment. Non-commercial. Do not republish adapted vendor source as a commercial product without a separate review. |
| efficientnet_pytorch | https://github.com/lukemelas/EfficientNet-PyTorch | Apache-2.0 | The backbone class `EfficientNet`. DeepfakeBench vendors it as efficientnet-pytorch 0.7.1. |
| EfficientNet paper | https://arxiv.org/abs/1905.11946 | Paper, not code | Architecture reference. The released detector is 256px and uses a replaced stem. |
| AASIST | https://github.com/clovaai/aasist | MIT, NAVER Corp. | Model source. A wrapper may hook `_derive_att_map` without forking the file. |
| AASIST paper | https://arxiv.org/abs/2110.01200 | Paper | Forward-pass description. Official scores are bonafide logits; DeepTrace stores spoof softmax. |
| Grad-CAM | https://arxiv.org/abs/1610.02391 | Paper | Definition used below. |
| pytorch-grad-cam | https://github.com/jacobgil/pytorch-grad-cam | MIT | A generic implementation. Not imported. Its EfficientNet examples target other packages and other resolutions. |
| Integrated gradients | https://arxiv.org/abs/1703.01365 | Paper | Definition for the later audio experiment. |
| Occlusion sensitivity | https://arxiv.org/abs/1311.2901 (Zeiler and Fergus) | Paper | Perturbation check, not a proof of localization. |
| Captum | https://github.com/pytorch/captum and https://captum.ai/ | BSD | Not installed in `.venv-models` on 2026-09-30. Acceptable later for integrated gradients and as a cross-check of Grad-CAM. |
| PyTorch | https://pytorch.org/docs/stable/autograd.html | BSD | `inference_mode` disables autograd views. Explain forwards must leave it. |

The Grad-CAM formula already sketched in `backend/deeptrace/ml/attribution.py` (`grad_cam`) matches Selvaraju: global-average-pool the incoming gradients, weight the channels, sum, ReLU, then normalize. It is not wired to `effnb4_best.pth`. Wiring it means running that formula on `EfficientNetB4.features`, not pasting a tutorial that hooks `features.7` on a torchvision EfficientNet.

## Video methods

The attributed output for investigator copy is the fake-class screening score, `softmax(logits)[1]`. Grad-CAM itself is computed on the pre-softmax logit at index 1, which is the quantity whose gradient defines the map (Selvaraju et al.). Index 1 is the fake class in DeepfakeBench `label_dict` and in `EfficientDetector.forward`. Occlusion then checks whether masking high-map regions moves that same softmax more than masking low-map regions.

### Grad-CAM (primary)

| Question | Finding |
| --- | --- |
| What it attributes | Sensitivity of one scalar (here, fake logit index 1) to spatial locations in a chosen activation map. |
| Compatibility | Confirmed for this checkpoint. `EfficientNetB4.features` returns `(1, 1792, 8, 8)` before `adaptive_avg_pool2d` and `last_layer`. The probe's backward from logit 1 reached that map and the 256x256 input. |
| Target layer | The tensor returned by `EfficientNetB4.features`, which is `_swish(_bn1(_conv_head(x)))` inside `efficientnet_pytorch.EfficientNet.extract_features`. `efficientnet._conv_head` is the last `Conv2d` (`1x1`, 448 to 1792) and has the same 8x8 grid, but it is pre-batch-norm and pre-Swish. Hook the post-Swish map that pooling actually reads. |
| Gradients required | Yes. The production runner's `torch.inference_mode()` block cannot host this pass. |
| Cost | One forward and one backward per face crop. Cheap relative to occlusion. |
| Spatial resolution | 8x8 on the 256x256 aligned face, then bilinear resize onto that crop. |
| Map back to the crop | Yes, by resizing 8x8 to 256x256. The crop is the model input. |
| Map back to the sampled frame | Only with the similarity matrix `M` from `extract_aligned_face_dlib`. The runner currently discards `M`. |
| After video-level aggregation | A frame map explains that frame's logit. It does not explain the unweighted mean except as "this frame contributed its own score to the mean." Do not draw one heatmap for the video score. |
| Limitations | Coarse 8x8 grid. Global average pooling mixes channels. Swish is not ReLU, so the usual "positive influence" ReLU is applied to the weighted map, not inside the network. High response can be context the model uses (compression, skin texture, alignment edges), including regions a human would not call a blend boundary. |

### Occlusion (validation)

| Question | Finding |
| --- | --- |
| What it attributes | Change in the fake-class softmax when a region of the 256x256 model input is replaced. |
| Compatibility | Any black-box score. No change to `EfficientNetB4` is required. Run it on the same normalized tensor the runner builds. |
| Gradients required | No. |
| Cost | One forward per mask. A 16x16 grid of masks on every sampled face is tens to hundreds of forwards per frame. Use it on a sample of frames to test Grad-CAM, not as the default picture. |
| Spatial resolution | Chosen by the mask size. Independent of the 8x8 map, which is why it is a check. |
| Map back to the crop | Direct: the mask is already on the crop. |
| Map back to the frame | Same `M` as Grad-CAM if the result is drawn on the JPEG. |
| After aggregation | A perturbation of one crop moves that crop's score. It does not, by itself, explain the mean of other frames. |
| Limitations | The replacement value is a second model input the detector was not trained on. Zeros in normalized space are pixel value 0.5 after undoing `(x - 0.5) / 0.5`, i.e. mid-gray, not black. Document the fill. A single attractive frame is not a validation. |

The sanity tests in the later `tests/explainability/` milestone should show that masking the top of the Grad-CAM map moves `softmax[:, 1]` more than masking the bottom, across more than one frame. If that fails, the heatmap does not ship.

### Integrated gradients (not the video primary)

Integrated gradients attribute a scalar to each input element along a path from a baseline to the input (Sundararajan et al.). Captum's `IntegratedGradients` can do this for the 256x256 tensor. For this detector it is optional:

- The spatial map is noisier than Grad-CAM and needs many steps (cost scales with step count).
- Baseline choice (black, mid-gray, blurred face) changes the picture.
- Grad-CAM already has a defensible spatial target on this architecture, and occlusion can test it without a new library.

Do not add Captum only to produce a second face picture until Grad-CAM has passed the perturbation check.

## Audio methods

The investigator-facing quantity is the spoof screening score, `softmax(logits)[0]`. Official AASIST evaluation stores `logits[:, 1]` (bonafide logit) in `produce_evaluation_file`. Those sources disagree. DeepTrace reports the softmax. Explanations follow the softmax.

The analyzed input is 64600 samples. Audio after 4.0375 seconds is not an input. Repeat-padding of short files means later samples are copies of the start.

### A. Temporal occlusion (primary)

| Question | Finding |
| --- | --- |
| What it attributes | Change in spoof softmax when a time span of the 64600-sample input is replaced. |
| Compatibility | The model is a waveform network with one file-level head. A windowed re-run is well defined. |
| Gradients required | No. |
| Cost | One baseline forward plus one forward per window. About 15 windows for 500 ms masks and a 250 ms hop over 4.0375 s (see the audio plan). Acceptable for a case review. Not acceptable if naively applied to every hop of a one-hour recording the model never sees. |
| Resolution | The window length. 500 ms is the starting investigator scale. Finer hops are a parameter, stored with the artifact. |
| Map back to the waveform | Yes. Windows are sample ranges inside the tensor that was scored. |
| Meaningful after aggregation | There is no segment aggregation in the current runner. The file score is the windowed model's only score. |
| Limitations | A mask is a new waveform. Training crops or tiles (`pad` / `pad_random`); it does not punch holes. Zeros, local mean, and added noise can all be out of distribution. The architecture probe did not pick a winner. Validation must compare them and keep the signed delta. `normalize_series` in `attribution.py` takes the absolute value and would hide whether the score rose or fell. |

Starting contract, to be stored with every artifact:

```text
importance = baseline_spoof_softmax - masked_spoof_softmax
```

A positive value means masking that span lowered the spoof score. The UI sentence is: "Masking this 500 ms segment changed the model screening score by 0.17." It includes the sign and the method. It does not say the span is synthetic.

### B. Integrated gradients (secondary experiment)

| Question | Finding |
| --- | --- |
| What it attributes | Sample-level contribution of the waveform to one scalar, relative to a baseline, averaged along the straight path. |
| Compatibility | The probe's backward from logit 0 reached the `(1, 64600)` input, so a path method is mechanically possible. `eval()` must stay on, and `inference_mode` must stay off. |
| Target | The raw waveform first. An intermediate such as `encoder` output `(1, 64, 23, 29)` is a different object (a learned representation, not samples). |
| Gradients required | Yes. Captum is the library to add later. It is not installed now. |
| Cost | One backward per integration step. Typical step counts (32 to 128) are heavier than a dozen occlusion forwards and harder to explain to a reviewer. |
| Resolution | 64600 numbers. That series must be summed into bins (20 to 50 ms is the candidate) before any API response. |
| Stability | Unknown until the experiment. Raw-sample gradients on a sinc-filter frontend are expected to be noisy. Binning is part of the experiment, not a cosmetic smooth. |
| Map back to audio | Bins map to sample ranges inside the 4.0375 s window. |
| Limitations | Baseline dependence. Completeness (attributions sum to the output difference) is a property of the method only for the chosen baseline and the chosen scalar. If the scalar is the logit and the UI talks about the softmax, say so. Prefer the spoof logit for the integral and also report the softmax delta so the two are not silently swapped. |

This experiment is compared with temporal occlusion (sanity test: high-IG bins should overlap high-occlusion windows more than chance). It does not replace occlusion as the investigator view unless that comparison holds on bona fide and spoof clips.

### C. Time-frequency attribution (not adopted)

AASIST does not take a spectrogram. `Model.forward` takes a waveform. The sinc `CONV` builds 70 filters on a mel spacing, `abs` and `max_pool2d((3, 3))` reduce that to 23 frequency bins, and the encoder ends at `(1, 64, 23, 29)`.

Those 23 and 29 axes are internal. They are not Hertz and seconds of an STFT the model consumed. Drawing a mel spectrogram of the WAV and painting a heatmap on it would show a picture the network never saw.

A later research view could attribute the encoder tensor and label the axes as "encoder frequency bin" and "encoder time bin" with the pooling formula attached. That is not the primary explanation, and it is not implemented by coloring a librosa spectrogram.

Spectral graph nodes are `max` over the encoder's time axis, so they have already discarded time. Temporal nodes are `max` over frequency. A single 2D heatmap is not what either graph contains.

### D. Graph attention (research view)

`GraphAttentionLayer._derive_att_map` builds a softmax attention map and drops it on the floor. `forward` returns only the projected nodes. The probe wrapped `_derive_att_map` in-process and recorded:

| Layer | Attention shape | What the nodes are at that moment |
| --- | --- | --- |
| `GAT_layer_S` | `(1, 23, 23, 1)` | 23 spectral nodes (mel-sinc bins after the frontend pool, plus `pos_S`) |
| `GAT_layer_T` | `(1, 29, 29, 1)` | 29 temporal nodes (encoder time axis) |
| `HtrgGAT_layer_ST11` and `ST21` | `(1, 31, 31, 1)` | 20 temporal + 11 spectral nodes after the first graph pool |
| `HtrgGAT_layer_ST12` and `ST22` | `(1, 15, 15, 1)` | 10 temporal + 5 spectral nodes after the second pool |

`HtrgGraphAttentionLayer` also builds a separate master-node map in `_derive_att_map_master`. The classifier never sees these maps. It sees `last_hidden` `(1, 160)`: max and mean of the remaining temporal nodes, max and mean of the remaining spectral nodes, and the master node.

`GraphPool.top_k_graph` keeps `max(int(n * k), 1)` nodes and gathers them. The surviving indices depend on the input. After that gather, node `i` is not "time bin i" anymore.

Attention weights are internal model attention. They are not a causal explanation of the spoof score unless a later test shows they predict occlusion deltas. The UI label, if this view is ever shown, is "internal model attention," and it stays off the default investigator path.

In `eval()` the dropout modules inside the GAT layers are inactive, so these maps are a deterministic function of the input. They still are not causes.

## What "confidence" means today

| Name in the product | Actual value |
| --- | --- |
| `fake_probability` in runner JSON | Softmax of the positive class for that runner (video class 1, audio class 0) |
| `synthetic_confidence` | That softmax, or the unweighted mean of frame softmaxes |
| `overall_synthetic_confidence` | Weighted mean of the modality softmaxes, default 0.5 / 0.5 |
| UI "model confidence" | The same softmax, rendered as a percent |
| `DetectionResult.calibrated_probability` | Always null |

No reliability diagram, Brier score, or ECE is computed in this repository. Until that exists, new UI copy uses "model screening score." Renaming the field in storage can wait; renaming the sentence the investigator reads should happen when the attribution UI is built.

## Validation required before a DPS-facing map

Video, under `tests/explainability/` when implementation starts:

1. The map changes when the face crop changes.
2. The map changes when the backward target changes from logit 1 to logit 0, where both are defined.
3. Masking high-attribution regions moves the fake softmax more than masking low-attribution regions, on more than one frame.
4. Failures are recorded. A single clean example is not a result.

Audio:

1. Temporal importance changes when the analyzed window changes.
2. Masking high-importance spans moves the spoof softmax more than masking low-importance spans, on bona fide and spoof clips.
3. Integrated-gradient bins, once computed, are compared with occlusion rather than shown alone.
4. The 4.0375 s limit and any repeat-padding are visible in the artifact metadata.

## Language

Use: model attribution, regions contributing to the model output, prediction sensitivity, model-relevant region, this segment had greater influence on the screening score.

Do not use: manipulation detected here, this region proves the video is fake, the model discovered the forged pixels, the explanation proves the voice was synthesized.

Three questions stay separate: what the model output, what influenced that output, and what the human reviewer concludes.
