"""Versioned screening rules; these do not calibrate scores or certify performance."""

EFFICIENTNET_POC_RULE = "ffpp_c23_kaggle_v1"
EFFICIENTNET_POC_THRESHOLD = 0.9967585206031799
EFFICIENTNET_RULES = {
    "default_0_5": (0.5, "default_model_decision_rule"),
    EFFICIENTNET_POC_RULE: (EFFICIENTNET_POC_THRESHOLD, "ffpp_c23_kaggle_v1_development_only_any_frame"),
}
