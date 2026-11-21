# Seven-week implementation roadmap

Agency milestones (original dates TBD) and the team-proposed calendar below follow [DEEPTRACE_PROPOSAL.md](../DEEPTRACE_PROPOSAL.md). Proposed start dates are subject to Hub and DPS.

| Week | Outcome | Exit criteria | Proposed start |
|---|---|---|---|
| 1 | Kickoff and access verification | Confirm scope and approved data/media sources | 09/15/26 |
| 2 | Environment and model exploration | Container/env ready; audio/video candidate review (GAN artifacts, frequency analysis, biological-signal inconsistency); LEVA/SWGDE review | 09/22/26 |
| 3 | Video detection integration | Frame/facial-region assessment and confidence scoring | 09/29/26 |
| 4 | Audio module and unified report | Mel-spectrogram/vocoder and voice-synthesis signals; unified report | 10/06/26 |
| 5 | Benchmarking and refinement | Accuracy on labeled test set; feedback-driven refinements | 10/13/26 |
| 6 | Closeout | Documentation and GitHub finalization | 10/20/26 |
| 7 | Showcase | Final presentation | 10/27/26 |

**Candidate models (not final):** video — DeepfakeBench EfficientNet-B4; audio — AASIST / AASIST-L (Nes2Net retained as alternate). **Benchmarks:** FaceForensics++; ASVspoof 2021.

### Roles

| Member | Focus |
|---|---|
| Dol Raj Bashyal | Application & cloud integration |
| Krish Karki | Audio analysis & evaluation |
| Tarbi Pyakurel | Video analysis & ML evaluation |

Out of scope for this PoC: production/live investigative use; DPS case/evidence/records integration; forensic certification; chain-of-custody; real-time streams; external access; detecting every manipulation technique.

Domain-shift evaluation details are in [evaluation.md](evaluation.md).
