"""
Drift monitoring via Population Stability Index (PSI) — PRD Section 10.

Run weekly (scheduled job) comparing the trailing window of live applicant
traffic to the training-time distribution, per feature. PSI > 0.2 on any
feature is the conventional industry flag for "the population this model
sees no longer resembles the population it was trained on" — a silent
failure mode most portfolio projects never revisit after deployment.

Interpretation guide (standard PSI bands, not something we invented):
  < 0.1  : no significant shift
  0.1-0.2: moderate shift, watch
  > 0.2  : significant shift, investigate / consider retraining
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PSI_FLAG_THRESHOLD = 0.2
PSI_WATCH_THRESHOLD = 0.1


def _psi_numeric(reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    quantiles = np.linspace(0, 1, n_bins + 1)
    bin_edges = np.unique(np.quantile(reference, quantiles))
    if len(bin_edges) < 3:
        return 0.0  # degenerate feature, not enough variation to bin

    ref_counts, _ = np.histogram(reference, bins=bin_edges)
    cur_counts, _ = np.histogram(current, bins=bin_edges)

    ref_pct = np.clip(ref_counts / max(len(reference), 1), 1e-4, None)
    cur_pct = np.clip(cur_counts / max(len(current), 1), 1e-4, None)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def _psi_categorical(reference: pd.Series, current: pd.Series) -> float:
    categories = sorted(set(reference.unique()) | set(current.unique()))
    ref_pct = reference.value_counts(normalize=True).reindex(categories, fill_value=1e-4)
    cur_pct = current.value_counts(normalize=True).reindex(categories, fill_value=1e-4)
    ref_pct = ref_pct.clip(lower=1e-4)
    cur_pct = cur_pct.clip(lower=1e-4)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def compute_drift_report(reference_df: pd.DataFrame, current_df: pd.DataFrame,
                          numeric_features: list[str], categorical_features: list[str]) -> dict:
    feature_psi = {}
    for feat in numeric_features:
        feature_psi[feat] = round(_psi_numeric(
            reference_df[feat].dropna().values, current_df[feat].dropna().values
        ), 4)
    for feat in categorical_features:
        feature_psi[feat] = round(_psi_categorical(
            reference_df[feat].dropna(), current_df[feat].dropna()
        ), 4)

    flagged = any(v > PSI_FLAG_THRESHOLD for v in feature_psi.values())
    watch = {k: v for k, v in feature_psi.items() if PSI_WATCH_THRESHOLD < v <= PSI_FLAG_THRESHOLD}
    breached = {k: v for k, v in feature_psi.items() if v > PSI_FLAG_THRESHOLD}

    return {
        "feature_psi": feature_psi,
        "flagged": bool(flagged),
        "watch_features": watch,
        "breached_features": breached,
    }


if __name__ == "__main__":
    import json
    import os

    sys_path_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import sys
    sys.path.insert(0, sys_path_root)
    from ml.preprocessing import NUMERIC_FEATURES, CATEGORICAL_FEATURES

    ARTIFACT_DIR = os.path.join(sys_path_root, "..", "artifacts")
    reference_df = pd.read_csv(os.path.join(ARTIFACT_DIR, "test_holdout.csv"))

    # Demo: simulate a drifted "current window" by shifting income & utilization
    # (in production this comes from the last N days of `applications`).
    rng = np.random.default_rng(7)
    current_df = reference_df.copy()
    current_df["income"] = current_df["income"] * rng.normal(1.35, 0.05, len(current_df))
    current_df["credit_utilization"] = np.clip(
        current_df["credit_utilization"] + rng.normal(0.2, 0.05, len(current_df)), 0, 1
    )

    report = compute_drift_report(reference_df, current_df, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    print(json.dumps(report, indent=2))

    with open(os.path.join(ARTIFACT_DIR, "latest_drift_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # Also emit a "no drift" baseline report (current == reference) to show
    # the monitor doesn't cry wolf on a stable population.
    stable_report = compute_drift_report(reference_df, reference_df.sample(frac=0.5, random_state=1),
                                          NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    print("\nStable-population sanity check (should be low):")
    print(json.dumps(stable_report, indent=2))
