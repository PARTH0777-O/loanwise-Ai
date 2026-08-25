"""
SHAP explanation service (PRD Section 7 sample response, Section 12).

Design choices:
- We explain the underlying tree/linear model's decision function, not the
  isotonic calibration wrapper (SHAP doesn't have a clean story for
  calibrators). The pre-calibration score is directionally identical; the
  narrative talks about "factors that increase/decrease risk," not the
  literal probability, so this doesn't mislead.
- Output is bounded to top-N factors (Section 8.2) — this is a security
  control (limits model-extraction surface area), not just a UX choice.
- KernelExplainer is too slow for interactive latency; we use TreeExplainer
  for tree models and LinearExplainer for logistic regression, chosen by
  introspecting the fitted estimator type.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

TOP_N_FACTORS = 5


class ExplanationService:
    def __init__(self, calibrated_model, background_df: pd.DataFrame, feature_names: list[str]):
        """
        calibrated_model: the full CalibratedClassifierCV (or raw pipeline)
        background_df: small sample of training data (raw feature columns) for
                        explainer background distribution
        """
        self.feature_names = feature_names
        # Unwrap to the underlying fitted Pipeline(prep, clf) to explain the
        # base estimator's decision function pre-calibration.
        self._pipeline, self._explainer = self._build_explainer(calibrated_model, background_df)

    def _unwrap_pipeline(self, model):
        # CalibratedClassifierCV(FrozenEstimator(pipe)) after fit exposes
        # calibrated_classifiers_[i].estimator which is the FrozenEstimator
        # wrapping the fitted pipeline.
        if hasattr(model, "calibrated_classifiers_"):
            inner = model.calibrated_classifiers_[0].estimator
            if hasattr(inner, "estimator"):  # FrozenEstimator wraps .estimator
                return inner.estimator
            return inner
        return model  # already a raw Pipeline

    def _build_explainer(self, model, background_df: pd.DataFrame):
        pipeline = self._unwrap_pipeline(model)
        prep = pipeline.named_steps["prep"]
        clf = pipeline.named_steps["clf"]
        background_transformed = prep.transform(background_df)

        if isinstance(clf, (RandomForestClassifier, XGBClassifier)):
            explainer = shap.TreeExplainer(clf, feature_names=self.feature_names)
        elif isinstance(clf, LogisticRegression):
            explainer = shap.LinearExplainer(clf, background_transformed, feature_names=self.feature_names)
        else:
            explainer = shap.KernelExplainer(clf.predict_proba, shap.sample(background_transformed, 50))
        return pipeline, explainer

    def explain(self, raw_input_df: pd.DataFrame) -> dict:
        """raw_input_df: single-row DataFrame with ALL_FEATURES columns."""
        prep = self._pipeline.named_steps["prep"]
        X_transformed = prep.transform(raw_input_df)

        shap_values = self._explainer.shap_values(X_transformed)
        if isinstance(shap_values, list):  # binary clf sometimes returns [class0, class1]
            shap_values = shap_values[1]
        if shap_values.ndim == 3:  # (n_samples, n_features, n_classes) for some TreeExplainer paths
            shap_values = shap_values[:, :, 1]

        row_values = shap_values[0]
        pairs = sorted(
            zip(self.feature_names, row_values),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:TOP_N_FACTORS]

        factors = [
            {
                "feature": name,
                "impact": round(float(val), 4),
                "direction": "increases_risk" if val > 0 else "decreases_risk",
            }
            for name, val in pairs
        ]
        narrative = self._build_narrative(factors)
        return {"top_factors": factors, "narrative": narrative}

    @staticmethod
    def _build_narrative(factors: list[dict]) -> str:
        if not factors:
            return "No dominant risk factors identified."
        increasing = [f["feature"] for f in factors if f["direction"] == "increases_risk"][:2]
        decreasing = [f["feature"] for f in factors if f["direction"] == "decreases_risk"][:2]

        def humanize(name: str) -> str:
            return name.replace("_", " ").replace("=", ": ")

        parts = []
        if increasing:
            parts.append("primarily driven by " + " and ".join(humanize(f) for f in increasing))
        if decreasing:
            parts.append("partially offset by " + " and ".join(humanize(f) for f in decreasing))
        return "The prediction is " + "; ".join(parts) + "." if parts else "Mixed, low-magnitude factors."
