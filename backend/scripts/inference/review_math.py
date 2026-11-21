"""Small numerical review measurements. Inputs are measured, not classified as fake."""
import math


def eye_aspect_ratio(points):
    distance = lambda a, b: math.hypot(a[0]-b[0], a[1]-b[1])
    horizontal = distance(points[0], points[3])
    if horizontal <= 0:
        return None
    return (distance(points[1], points[5]) + distance(points[2], points[4])) / (2 * horizontal)


def closure_intervals(samples, threshold, max_gap):
    """Candidate closures relative to a recorded baseline, never an unnatural-blink verdict."""
    intervals, start, previous = [], None, None
    for timestamp, value in samples:
        if value is None:
            start = previous = None
            continue
        if previous is not None and timestamp - previous > max_gap:
            start = None  # Never bridge occlusion or face loss.
        if value < threshold:
            if start is None:
                start = timestamp
        elif start is not None:
            intervals.append({"start_time": start, "end_time": timestamp, "description": "Candidate eye closure"})
            start = None
        previous = timestamp
    # An unclosed interval at EOF cannot establish a complete blink.
    return intervals


def block_boundary_ratio(gray, np, block=8):
    """8-pixel grid contrast in native decoded pixels; no JPEG re-encoding."""
    boundary_means, interior_means = [], []
    for axis in (0, 1):
        delta = np.abs(np.diff(gray.astype(np.float32), axis=axis))
        indices = np.arange(delta.shape[axis]) + 1
        boundary = np.take(delta, np.where(indices % block == 0)[0], axis=axis)
        interior = np.take(delta, np.where(indices % block != 0)[0], axis=axis)
        if boundary.size and interior.size:
            boundary_means.append(float(boundary.mean()))
            interior_means.append(float(interior.mean()))
    return sum(boundary_means) / (sum(interior_means) + 1e-6) if boundary_means else 0.0


def spectrum_metrics(gray, np):
    image = gray.astype(np.float32)
    image -= image.mean()
    taper = np.outer(np.hanning(image.shape[0]), np.hanning(image.shape[1]))
    power = np.abs(np.fft.fftshift(np.fft.fft2(image * taper))) ** 2
    yy, xx = np.ogrid[-1:1:complex(image.shape[0]), -1:1:complex(image.shape[1])]
    radius = np.sqrt(xx*xx + yy*yy)
    return {"high_frequency_energy_ratio": float(power[radius > .5].sum() / (power.sum() + 1e-12))}
