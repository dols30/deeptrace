from scripts.benchmark import calculate


def test_metrics():
    result = calculate([{"label": "0", "score": ".1"}, {"label": "0", "score": ".8"},
        {"label": "1", "score": ".7"}, {"label": "1", "score": ".9"}])
    assert result["accuracy"] == .75
    assert result["false_positive_rate"] == .5
    assert result["auroc"] == .75
