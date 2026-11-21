# AASIST attribution plan

Date: 2026-09-30. This plan traces the vendored AASIST `Model` and fixes temporal occlusion as the investigator explanation. Integrated gradients are a later experiment. Graph attention is an internal view. Shapes were measured by `backend/scripts/dev/inspect_aasist.py` on `AASIST.pth` with a `(1, 64600)` input.

## Sources

| Item | Location |
| --- | --- |
| Repository | https://github.com/clovaai/aasist at `a04c9863f63d44471dde8a6abcb3b082b07cd1d1` |
| License | MIT, NAVER Corp. |
| Paper | https://arxiv.org/abs/2110.01200 |
| Class | `Model.forward` in `backend/vendor/aasist/models/AASIST.py` |
| Config | `backend/vendor/aasist/config/AASIST.conf` |
| Checkpoint | `backend/models/aasist/AASIST.pth`, SHA-256 `51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0` |
| Score DeepTrace stores | `softmax(logits)[0]`, spoof |
| Score official eval stores | `logits[:, 1]`, bonafide logit, in `produce_evaluation_file` |

Explanations use the spoof softmax so a reported delta matches the screening score.

## Forward trace

```text
raw waveform (1, 64600)                         data_utils.pad, 16 kHz mono
  -> unsqueeze channel
  -> conv_time                                  CONV sinc frontend, 70 filters, kernel 129
       output (1, 70, 64472)
  -> abs, max_pool2d (3, 3), first_bn, selu
       first_bn output (1, 1, 23, 21490)
  -> encoder                                    six Residual_block stages
       output (1, 64, 23, 29)                   (batch, channels, frequency, time)
  -> spectral branch
       max over time, plus pos_S (1, 23, 64)
       GAT_layer_S                              GraphAttentionLayer
       output (1, 23, 64)
       pool_S                                   GraphPool ratio 0.5 -> (1, 11, 64)
  -> temporal branch
       max over frequency
       GAT_layer_T
       output (1, 29, 64)
       pool_T                                   GraphPool ratio 0.7 -> (1, 20, 64)
  -> heterogeneous stack, two parallel branches
       HtrgGAT_layer_ST11 / ST21               HtrgGraphAttentionLayer
       pool_hT* ratio 0.5, pool_hS* ratio 0.5
       HtrgGAT_layer_ST12 / ST22
       residual add, then max across the two branches
  -> readout
       temporal max and mean, spectral max and mean, master node
       last_hidden (1, 160)
  -> dropout (inactive in eval), out_layer
  -> logits (1, 2)
  -> softmax index 0                           spoof screening score
```

`first_conv` in the config is 128. `CONV.__init__` increments an even kernel, so the sinc kernel is 129. That matches `64600 - 64472 + 1`.

The encoder's six `Residual_block`s each end in `MaxPool2d((1, 3))`, which pools time and leaves the 23 frequency bins. Six stride-3 pools take 21490 time steps to 29. The 23 frequency bins are the mel-spaced sinc bank after the frontend's 3x3 pool. They are not STFT bins.

`Model.forward` returns `(last_hidden, output)`. The runner discards `last_hidden`.

## Where each function lives

| Stage | Class or function | Method |
| --- | --- | --- |
| Frontend | `CONV` | `forward` (`conv_time`) |
| Encoder | `Residual_block` inside `Model.encoder` | `forward` |
| Spectral graph | `GraphAttentionLayer` | `GAT_layer_S.forward` |
| Temporal graph | `GraphAttentionLayer` | `GAT_layer_T.forward` |
| Graph attention map | `GraphAttentionLayer._derive_att_map` | not returned |
| Heterogeneous attention | `HtrgGraphAttentionLayer` | `HtrgGAT_layer_ST11`, `ST12`, `ST21`, `ST22` |
| Heterogeneous map | `HtrgGraphAttentionLayer._derive_att_map` | not returned |
| Master-node map | `HtrgGraphAttentionLayer._derive_att_map_master` | not returned |
| Pooling | `GraphPool.top_k_graph` | `pool_S`, `pool_T`, `pool_hS1`, `pool_hT1`, `pool_hS2`, `pool_hT2` |
| Readout | `Model.forward` | max/mean concat into `last_hidden` |
| Classifier | `nn.Linear` | `out_layer` |

## Attention maps the probe recorded

`forward` does not return attention. The probe wrapped `_derive_att_map` for one eval forward and then restored the original methods.

| Map | Shape | Nodes |
| --- | --- | --- |
| `GAT_layer_S` | `(1, 23, 23, 1)` | Spectral nodes before the pool. Index aligns with the 23 frontend frequency bins plus `pos_S`. |
| `GAT_layer_T` | `(1, 29, 29, 1)` | Temporal nodes before the pool. Index aligns with the encoder time axis. |
| `HtrgGAT_layer_ST11`, `ST21` | `(1, 31, 31, 1)` | 20 pooled temporal nodes and 11 pooled spectral nodes, concatenated. |
| `HtrgGAT_layer_ST12`, `ST22` | `(1, 15, 15, 1)` | 10 temporal and 5 spectral nodes after the second pool. |

`GraphPool` keeps `max(int(n * ratio), 1)` nodes. The count is determined by the ratio. The identities are a top-k on an input-dependent score, and `torch.gather` packs them to the front. After the first pool, temporal node 0 is not encoder time bin 0.

The readout then collapses remaining nodes with max and mean. The classifier cannot be inverted back to a time bin from `last_hidden` alone.

These maps may be shown later as "internal model attention." They are not the reason for the prediction unless a separate test says they track occlusion deltas. They are not the primary investigator view.

## Why a spectrogram heatmap is not the explanation

The network never receives a librosa or STFT spectrogram. Painting one would attribute a representation AASIST does not consume.

The closest internal grid is `encoder` output `(1, 64, 23, 29)`. A research figure of that tensor would have to say "encoder channel activation," with frequency bin = sinc-filter index after the 3x3 pool, and time bin = position after six `MaxPool2d((1, 3))` stages. Even then, spectral GAT max-pools away time, and temporal GAT max-pools away frequency. That figure is optional, labeled as an internal representation, and out of the first audio UI.

## Temporal occlusion contract

This is the investigator explanation.

Analyzed span: samples `[0, 64600)` of the 16 kHz mono decode, which is `[0, 4.0375)` seconds. If the file is shorter, `pad` repeats it. Repeated samples are copies, and the artifact says so. If the file is longer, samples at or after 64600 are outside the model input. The waveform UI may still draw the whole file for playback. Attribution is drawn only on the analyzed span.

Starting window, stored in `parameters_json` so it can change without silent history:

- Window: 0.5 s = 8000 samples
- Hop: 0.25 s = 4000 samples
- Starts: `0, 4000, 8000, ...` while `start + 8000 <= 64600`
- That list ends at start 56000 (end 64000). The last 600 samples (37.5 ms) are covered by an extra closing window `[64600 - 8000, 64600)` if it is not already in the list, or they are reported as a residual tail. The artifact records the exact starts that were run.

For each window:

```text
baseline = softmax(model(x))[0]
masked = softmax(model(mask(x, start, end)))[0]
score_delta = baseline - masked
```

`score_delta` is signed. Positive means the spoof score fell when the span was masked. The API stores the signed value. A bar chart may encode magnitude, but the click detail shows the signed change: "Masking this 500 ms segment changed the model screening score by 0.17."

Fills to compare in validation, before one of them becomes the default:

| Fill | What it does | Training-distribution concern |
| --- | --- | --- |
| Zeros | Writes 0 into the span | `pad` tiles or truncates. It does not insert a hole of zeros inside a clip. A zero hole can dominate a sinc frontend. |
| Local mean | Writes the mean of the span, or of a short neighborhood | A constant segment is also uncommon in ASVspoof speech. |
| Low-level noise | Writes noise at a documented amplitude | Closer to a quiet gap only if the amplitude is in the range of the file. Still not a phoneme that was there. |

The architecture probe did not score these fills. It measured shapes. Choosing a fill because a demo looks smooth is out of bounds. The validation tests record which fill moves bona fide and spoof clips, and whether the ranking of windows flips when the fill changes. If the ranking flips, the UI shows the method and the fill, and the disagreement stays in the artifact.

`model.eval()` stays on so dropout in the GAT and the classifier does not reshuffle the score between the baseline and the mask. The production runner's `inference_mode` is fine for occlusion, because occlusion does not need gradients.

Output shape the future adapter can return:

```json
[
  {"start": 3.5, "end": 4.0, "score_delta": 0.18}
]
```

Times are seconds from the start of the decoded 16 kHz waveform, inside the analyzed window. `ModelSample.end_time` is currently the full file duration (`audio.py`). That field overstates the analyzed span. The occlusion artifact carries its own start and end and does not inherit that end time.

`normalize_series` in `backend/deeptrace/ml/attribution.py` divides by the peak of the absolute values. Passing `score_delta` through it would drop the sign. The investigator payload keeps the signed delta. A normalized magnitude can be a separate display field.

## Integrated gradients (secondary)

The probe's backward from logit 0 reached the waveform, so sample-level gradients exist when autograd is on. Captum is not installed in `.venv-models`.

When the experiment runs:

- Attribute the spoof logit (index 0), and also store the spoof softmax of the endpoint so the UI is not silently talking about a different scalar.
- Baseline is an explicit choice (zeros and at least one alternative). The same out-of-distribution caution as occlusion applies.
- Sum absolute or signed attributions into bins of 20 to 50 ms before the value leaves the model process. Do not return 64600 floats to the browser.
- Compare bins with the occlusion windows on bona fide and spoof files. The experiment write-up includes cases where they disagree.

This view does not replace temporal occlusion unless that comparison holds.

## Graph attention (research view)

A debug script may hook `_derive_att_map` and `_derive_att_map_master` the way the probe does, write the maps, and label them "internal model attention."

It should also record:

- Node counts before and after each `GraphPool`
- The gather indices from `top_k_graph`, if a mapping back to encoder time is attempted
- That heterogeneous maps mix temporal and spectral nodes
- That max/mean readout discards node order

Without those indices, a 29-length attention summary is not a timeline. Do not build one by averaging a 29x29 matrix and calling it seconds.

## Analyzer gap

`AASISTAudioAnalyzer` will attach `temporal_relevance`, `spectral_relevance`, and `graph_attention` if the runner JSON includes them. `aasist.py` does not emit them. `AASISTDetector.explain` looks for those keys on `detection.metadata["attribution"]`, while `detection_from_component` puts adapter attribution on the finding, not on that metadata dict. Both gaps are real. The occlusion implementation should return a structured artifact from the model process rather than a bare list squeezed through `normalize_series`.
