"""
Fairness audit module (PRD Section 9).

Computed per protected-attribute group, joined ONLY here from the held-out
evaluation set — never at inference time, and never by the prediction
service's runtime code path. This mirrors the production design where
`applicant_protected` lives in a separate table joined only during batch
fairness report generation (Section 9, point 3).

Three metrics, deliberately not just one, because they catch different
failure modes:
  - Disparate Impact Ratio: are we approving one group at a systematically
    lower rate? (Four-fifths rule, a screening heuristic, not a legal
    determination.)
  - Equal Opportunity Difference: among applicants who will NOT actually
    default, are we correctly identifying them as low-risk at the same rate
    across groups? A model can have similar approval rates by group and
    still be worse at recognizing creditworthy applicants in one group.
  - Calibration gap: does a predicted 20% PD mean ~20% actual default rate
    within each group? A model can pass both metrics above and still
    systematically over- or under-estimate risk for a subgroup.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.preprocessing import RISK_THRESHOLDS

FOUR_FIFTHS_THRESHOLD = 0.8
APPROVAL_RISK_CATEGORIES = {"LOW", "MEDIUM"}  # "approved for further review" proxy


def _approved(pd_scores: np.ndarray) -> np.ndarray:
    return np.array([
        RISK_THRESHOLDS.categorize(p) in APPROVAL_RISK_CATEGORIES for p in pd_scores
    ])


def disparate_impact_ratio(pd_scores: np.ndarray, group: np.ndarray, groups: list[str]) -> dict:
    approved = _approved(pd_scores)
    rates = {}
    for g in groups:
        mask = group == g
        rates[g] = approved[mask].mean() if mask.sum() > 0 else np.nan
    privileged_rate = max(rates.values())
    return {g: round(float(r / privileged_rate), 4) if privileged_rate > 0 else np.nan
            for g, r in rates.items()}, rates


def equal_opportunity_difference(y_true: np.ndarray, pd_scores: np.ndarray,
                                   group: np.ndarray, groups: list[str]) -> dict:
    """TPR here = P(correctly flagged as elevated-risk | will actually default).
    We report per-group TPR and the max-min gap."""
    approved = _approved(pd_scores)
    flagged_high_risk = ~approved
    tprs = {}
    for g in groups:
        mask = (group == g) & (y_true == 1)
        if mask.sum() == 0:
            tprs[g] = np.nan
            continue
        tprs[g] = float(flagged_high_risk[mask].mean())
    valid = [v for v in tprs.values() if not np.isnan(v)]
    gap = round(max(valid) - min(valid), 4) if valid else np.nan
    return tprs, gap


def calibration_gap(y_true: np.ndarray, pd_scores: np.ndarray,
                     group: np.ndarray, groups: list[str], n_bins: int = 5) -> dict:
    """Per-group |predicted PD - realized default rate|, averaged over bins,
    weighted by bin size — a per-group expected calibration error."""
    bins = np.linspace(0, 1, n_bins + 1)
    gaps = {}
    for g in groups:
        mask = group == g
        if mask.sum() < 20:  # too few samples to bin meaningfully
            gaps[g] = np.nan
            continue
        yt, ps = y_true[mask], pd_scores[mask]
        bin_ids = np.clip(np.digitize(ps, bins) - 1, 0, n_bins - 1)
        ece = 0.0
        for b in range(n_bins):
            bmask = bin_ids == b
            if bmask.sum() == 0:
                continue
            ece += (bmask.sum() / mask.sum()) * abs(ps[bmask].mean() - yt[bmask].mean())
        gaps[g] = round(float(ece), 4)
    return gaps


def run_fairness_audit(y_true: np.ndarray, pd_scores: np.ndarray,
                        group: np.ndarray, attribute_name: str) -> dict:
    groups = sorted(pd.unique(group).tolist())
    di_ratios, raw_rates = disparate_impact_ratio(pd_scores, group, groups)
    tprs, eo_gap = equal_opportunity_difference(y_true, pd_scores, group, groups)
    cal_gaps = calibration_gap(y_true, pd_scores, group, groups)

    min_di = min(v for v in di_ratios.values() if not np.isnan(v))
    flagged = min_di < FOUR_FIFTHS_THRESHOLD

    return {
        "attribute": attribute_name,
        "disparate_impact_ratio": di_ratios,
        "approval_rate_by_group": {k: round(v, 4) for k, v in raw_rates.items()},
        "min_disparate_impact_ratio": round(min_di, 4),
        "flagged_four_fifths_rule": bool(flagged),
        "true_positive_rate_by_group": {k: (round(v, 4) if not np.isnan(v) else None)
                                          for k, v in tprs.items()},
        "equal_opportunity_diff": eo_gap,
        "calibration_gap_by_group": {k: (v if not np.isnan(v) else None)
                                       for k, v in cal_gaps.items()},
        "max_calibration_gap": round(max(v for v in cal_gaps.values() if not np.isnan(v)), 4),
    }


if __name__ == "__main__":
    import json
    import os
    import joblib

    ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "artifacts")
    with open(os.path.join(ARTIFACT_DIR, "latest_manifest.json")) as f:
        manifest = json.load(f)
    model = joblib.load(manifest["artifact_path"])
    test_df = pd.read_csv(os.path.join(ARTIFACT_DIR, "test_holdout.csv"))

    from ml.preprocessing import ALL_FEATURES, LABEL_COLUMN
    X_test = test_df[ALL_FEATURES]
    y_test = test_df[LABEL_COLUMN].values
    pd_scores = model.predict_proba(X_test)[:, 1]

    report = run_fairness_audit(y_test, pd_scores, test_df["age_band"].values, "age_band")
    print(json.dumps(report, indent=2))

    with open(os.path.join(ARTIFACT_DIR, "latest_fairness_report.json"), "w") as f:
        json.dump(report, f, indent=2)
