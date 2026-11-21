"""Score evaluation and calibration fitting.

Fitted parameters must be stored with the checkpoint, dataset version, and
preprocessing configuration. Nothing here is applied to live screening unless
a calibration version is configured.
"""

from dataclasses import dataclass


def _rank_scores(labels: list[int], scores: list[float]) -> list[tuple[float, int]]:
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must be the same non-empty length")
    if any(label not in (0, 1) for label in labels):
        raise ValueError("labels must be 0 or 1")
    return sorted(zip(scores, labels), key=lambda item: item[0])


def roc_points(labels: list[int], scores: list[float]) -> list[tuple[float, float]]:
    pairs = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("ROC requires both classes")
    points = [(0.0, 0.0)]
    true_positive = false_positive = 0
    for _score, label in pairs:
        if label == 1:
            true_positive += 1
        else:
            false_positive += 1
        points.append((false_positive / negatives, true_positive / positives))
    return points


def auc(labels: list[int], scores: list[float]) -> float:
    points = roc_points(labels, scores)
    area = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        area += (x1 - x0) * (y0 + y1) / 2
    return area


def confusion(labels: list[int], scores: list[float], threshold: float) -> dict[str, int]:
    matrix = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for label, score in zip(labels, scores):
        predicted = score >= threshold
        if predicted and label == 1:
            matrix["tp"] += 1
        elif predicted and label == 0:
            matrix["fp"] += 1
        elif not predicted and label == 0:
            matrix["tn"] += 1
        else:
            matrix["fn"] += 1
    return matrix


def binary_rates(matrix: dict[str, int]) -> dict[str, float | None]:
    tp, fp, tn, fn = matrix["tp"], matrix["fp"], matrix["tn"], matrix["fn"]

    def ratio(numerator: int, denominator: int) -> float | None:
        if denominator == 0:
            return None
        return numerator / denominator

    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    return {
        "sensitivity": recall,
        "specificity": ratio(tn, tn + fp),
        "precision": precision,
        "recall": recall,
    }


def equal_error_rate(labels: list[int], scores: list[float]) -> float:
    """Threshold-free EER approximation from the ROC, for score evaluation only."""
    points = roc_points(labels, scores)
    best = 1.0
    for false_positive, true_positive in points:
        false_negative = 1 - true_positive
        best = min(best, max(false_positive, false_negative))
    return best


def brier_score(labels: list[int], probabilities: list[float]) -> float:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("labels and probabilities must be the same non-empty length")
    return sum((probability - label) ** 2 for label, probability in zip(labels, probabilities)) / len(labels)


def expected_calibration_error(labels: list[int], probabilities: list[float], bins: int = 10) -> float:
    if bins < 1:
        raise ValueError("bins must be positive")
    totals = [0] * bins
    correct = [0.0] * bins
    confidence = [0.0] * bins
    for label, probability in zip(labels, probabilities):
        index = min(bins - 1, int(probability * bins))
        totals[index] += 1
        correct[index] += label
        confidence[index] += probability
    count = len(labels)
    error = 0.0
    for index, total in enumerate(totals):
        if total:
            error += total / count * abs(correct[index] / total - confidence[index] / total)
    return error


def calibration_curve(labels: list[int], probabilities: list[float], bins: int = 10) -> list[dict[str, float]]:
    totals = [0] * bins
    correct = [0.0] * bins
    confidence = [0.0] * bins
    for label, probability in zip(labels, probabilities):
        index = min(bins - 1, int(probability * bins))
        totals[index] += 1
        correct[index] += label
        confidence[index] += probability
    curve = []
    for index, total in enumerate(totals):
        if total:
            curve.append({
                "bin_start": index / bins,
                "mean_score": confidence[index] / total,
                "fraction_positive": correct[index] / total,
                "count": float(total),
            })
    return curve


@dataclass
class TemperatureScaler:
    temperature: float
    dataset_version: str
    preprocessing_version: str

    def apply(self, logit: float) -> float:
        from math import exp
        scaled = logit / self.temperature
        return 1 / (1 + exp(-scaled))


def fit_temperature(logits: list[float], labels: list[int], *, dataset_version: str, preprocessing_version: str) -> TemperatureScaler:
    """Grid search on binary NLL. The result is a versioned calibration artifact, not a live default."""
    if len(logits) != len(labels) or not logits:
        raise ValueError("logits and labels are required")
    best_temperature = 1.0
    best_loss = float("inf")
    for step in range(1, 51):
        temperature = step / 10
        scaler = TemperatureScaler(temperature, dataset_version, preprocessing_version)
        loss = 0.0
        for logit, label in zip(logits, labels):
            probability = min(1 - 1e-12, max(1e-12, scaler.apply(logit)))
            loss += -(label * _log(probability) + (1 - label) * _log(1 - probability))
        if loss < best_loss:
            best_loss = loss
            best_temperature = temperature
    return TemperatureScaler(best_temperature, dataset_version, preprocessing_version)


def _log(value: float) -> float:
    from math import log
    return log(value)


def fit_platt(scores: list[float], labels: list[int], *, steps: int = 400, learning_rate: float = 0.1) -> tuple[float, float]:
    """Logistic calibration on a model score. Returns (slope, intercept)."""
    if len(scores) != len(labels) or not scores:
        raise ValueError("scores and labels are required")
    slope, intercept = 1.0, 0.0
    for _ in range(steps):
        grad_slope = grad_intercept = 0.0
        for score, label in zip(scores, labels):
            probability = 1 / (1 + _exp(-(slope * score + intercept)))
            error = probability - label
            grad_slope += error * score
            grad_intercept += error
        slope -= learning_rate * grad_slope / len(scores)
        intercept -= learning_rate * grad_intercept / len(scores)
    return slope, intercept


def _exp(value: float) -> float:
    from math import exp
    return exp(max(-60.0, min(60.0, value)))


def apply_platt(score: float, slope: float, intercept: float) -> float:
    return 1 / (1 + _exp(-(slope * score + intercept)))
