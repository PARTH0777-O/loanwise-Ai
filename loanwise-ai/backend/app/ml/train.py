"""
Model training & selection.

Compares Logistic Regression -> Random Forest -> XGBoost on ROC-AUC, F1,
and calibration error (ECE), per PRD Section 14 Phase 2. Calibration is
weighted heavily in model choice: a PD model that is well-ranked (good AUC)
but poorly calibrated is actively dangerous for a system whose whole premise
is "explain the number," because the number itself would be wrong.

Selected model is wrapped in a CalibratedClassifierCV (isotonic) if it
improves ECE, then persisted with a content hash so a tampered artifact
can be detected on load (Section 8.3).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.preprocessing import (  # noqa: E402
    ALL_FEATURES, LABEL_COLUMN, PROTECTED_ATTRIBUTES, build_preprocessor,
)

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "artifacts")
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "synthetic_loans.csv")


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_ids = np.digitize(y_prob, bins) - 1
    bin_ids = np.clip(bin_ids, 0, n_bins - 1)
    ece = 0.0
    n = len(y_true)
    for b in range(n_bins):
        mask = bin_ids == b
        if mask.sum() == 0:
            continue
        conf = y_prob[mask].mean()
        acc = y_true[mask].mean()
        ece += (mask.sum() / n) * abs(conf - acc)
    return float(ece)


def evaluate(model, X_test, y_test) -> dict:
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    return {
        "roc_auc": round(float(roc_auc_score(y_test, y_prob)), 4),
        "f1": round(float(f1_score(y_test, y_pred)), 4),
        "ece": round(expected_calibration_error(y_test.values, y_prob), 4),
    }


def train_all(df: pd.DataFrame) -> dict:
    X = df[ALL_FEATURES]
    y = df[LABEL_COLUMN]

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.30, random_state=42, stratify=y
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, random_state=42, stratify=y_temp
    )

    candidates = {
        "logreg": LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=8, min_samples_leaf=20,
            class_weight="balanced", random_state=42, n_jobs=-1,
        ),
        "xgboost": XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
            random_state=42, n_jobs=-1,
        ),
    }

    results = {}
    fitted = {}
    for name, clf in candidates.items():
        pipe = Pipeline([("prep", build_preprocessor()), ("clf", clf)])
        pipe.fit(X_train, y_train)
        metrics = evaluate(pipe, X_val, y_val)

        # Try isotonic calibration on top; keep whichever has better ECE.
        calibrated = CalibratedClassifierCV(FrozenEstimator(pipe), method="isotonic")
        calibrated.fit(X_val, y_val)
        cal_metrics = evaluate(calibrated, X_test, y_test)
        raw_metrics_on_test = evaluate(pipe, X_test, y_test)

        if cal_metrics["ece"] <= raw_metrics_on_test["ece"]:
            fitted[name] = calibrated
            results[name] = {**cal_metrics, "calibrated": True}
        else:
            fitted[name] = pipe
            results[name] = {**raw_metrics_on_test, "calibrated": False}

        print(f"[{name}] val={metrics} test={results[name]}")

    # Selection: require AUC >= 0.85 (PRD goal), then pick lowest ECE.
    passing = {k: v for k, v in results.items() if v["roc_auc"] >= 0.85}
    pool = passing if passing else results
    best_name = min(pool, key=lambda k: pool[k]["ece"])
    best_model = fitted[best_name]
    best_metrics = results[best_name]

    return {
        "best_name": best_name,
        "best_model": best_model,
        "best_metrics": best_metrics,
        "all_results": results,
        "X_test": X_test, "y_test": y_test,
        "test_df": df.loc[X_test.index],  # retains protected attrs for fairness eval
    }


def save_artifact(model, name: str, metrics: dict) -> dict:
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    version_tag = f"{name}_v{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    artifact_path = os.path.join(ARTIFACT_DIR, f"{version_tag}.joblib")
    joblib.dump(model, artifact_path)

    with open(artifact_path, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()

    manifest = {
        "name": version_tag,
        "algorithm": name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "artifact_path": artifact_path,
        "content_hash": content_hash,
        "preprocessing_version": "1.0",
    }
    manifest_path = os.path.join(ARTIFACT_DIR, f"{version_tag}.manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Saved {artifact_path}\nSHA256: {content_hash}")
    return manifest


if __name__ == "__main__":
    df = pd.read_csv(DATA_PATH)
    result = train_all(df)
    print("\n=== Selected model:", result["best_name"], result["best_metrics"], "===\n")
    manifest = save_artifact(result["best_model"], result["best_name"], result["best_metrics"])

    # Persist test split (with protected attrs) for fairness/drift scripts to reuse.
    result["test_df"].to_csv(os.path.join(ARTIFACT_DIR, "test_holdout.csv"), index=False)
    with open(os.path.join(ARTIFACT_DIR, "latest_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
