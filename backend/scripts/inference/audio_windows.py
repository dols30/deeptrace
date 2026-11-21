"""Deterministic non-overlapping AASIST windows; no ML dependencies."""
WINDOW_SAMPLES = 64600
SAMPLE_RATE = 16000


def windows(sample_count: int, mode: str = "first"):
    if sample_count < 1 or mode not in {"first", "full"}:
        raise ValueError("Nonempty audio and first/full window mode are required")
    stop = sample_count if mode == "full" else min(sample_count, WINDOW_SAMPLES)
    for start in range(0, stop, WINDOW_SAMPLES):
        yield start, min(start + WINDOW_SAMPLES, stop)
