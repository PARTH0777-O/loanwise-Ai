"""
Preprocessing pipeline shared by training and inference.

This module is versioned alongside the model (Section 6 design note: dti_ratio
is persisted on the applications row precisely so a prediction can be
reproduced even if this file changes later). PREPROCESSING_VERSION is bumped
whenever the feature contract changes, and is stored on the model_versions
row so we can tell, at audit time, exactly which feature contract produced
a given prediction.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder

PREPROCESSING_VERSION = "1.0"

# Model features — protected attributes (age_band) are explicitly excluded.
NUMERIC_FEATURES = [
    "income",
    "loan_amount",
    "tenure_months",
    "credit_history_months",
    "existing_emi",
    "dti_ratio",
    "credit_utilization",
    "num_delinquencies_24m",
]
CATEGORICAL_FEATURES = ["employment_type"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Attributes retained ONLY for audit-time fairness reporting.
# Never passed to the model. Never joined by the prediction service's DB role
# (enforced at the application layer here; enforced at the DB grant layer in
# the schema — see docs/THREAT_MODEL.md).
PROTECTED_ATTRIBUTES = ["age_band"]

LABEL_COLUMN = "defaulted"


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )


def get_feature_names(preprocessor: ColumnTransformer) -> list[str]:
    """Human-readable feature names post-transform, in transform-output order."""
    names: list[str] = list(NUMERIC_FEATURES)
    cat_encoder = preprocessor.named_transformers_["cat"]
    for col, cats in zip(CATEGORICAL_FEATURES, cat_encoder.categories_):
        names.extend([f"{col}={c}" for c in cats])
    return names


def compute_derived_fields(row: dict) -> dict:
    """Compute dti_ratio etc. from raw application inputs at submission time.

    Mirrors the synthetic generator's logic so live traffic and training
    data share a feature definition. Stored on the applications row (not
    recomputed at prediction time) for audit reproducibility.
    """
    monthly_income = row["income"] / 12
    proposed_emi = row["loan_amount"] / row["tenure_months"] * 1.08
    dti_ratio = (row.get("existing_emi", 0) + proposed_emi) / max(monthly_income, 1)
    return {"dti_ratio": round(float(np.clip(dti_ratio, 0, 3)), 4)}


@dataclass
class RiskThresholds:
    """PD -> risk category mapping. Calibrated against training distribution
    terciles-ish; not a regulatory threshold, documented as such."""
    low_max: float = 0.10
    medium_max: float = 0.25

    def categorize(self, pd_score: float) -> str:
        if pd_score < self.low_max:
            return "LOW"
        if pd_score < self.medium_max:
            return "MEDIUM"
        return "HIGH"


RISK_THRESHOLDS = RiskThresholds()
