"""
Startup seeding for the reference implementation.

In production, model registration happens via the training pipeline's CI job
writing a `model_versions` row (not activated) and a human approving
activation through /admin/model-versions/{id}/activate (Section 9 point 2).
This seed script reproduces that flow locally so the API is usable
immediately after `docker compose up`, using the artifact already produced
by `ml/train.py`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

import auth
import models
from ml import fairness as fairness_mod
from ml import drift as drift_mod
from ml.preprocessing import ALL_FEATURES, LABEL_COLUMN, NUMERIC_FEATURES, CATEGORICAL_FEATURES
from ml.registry import registry

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts")

DEMO_USERS = [
    ("applicant@loanwise.demo", "ApplicantPass123!", "applicant"),
    ("officer@loanwise.demo", "OfficerPass123!", "officer"),
    ("compliance@loanwise.demo", "CompliancePass123!", "compliance"),
    ("admin@loanwise.demo", "AdminPass123!", "admin"),
]


def seed_demo_users(db: Session) -> None:
    for email, password, role in DEMO_USERS:
        if db.query(models.User).filter(models.User.email == email).first():
            continue
        db.add(models.User(
            email=email,
            password_hash=auth.hash_password(password),
            role=role,
            mfa_enabled=(role in ("compliance", "admin")),
        ))
    db.commit()


def seed_model_version(db: Session) -> models.ModelVersion:
    manifest_path = os.path.join(ARTIFACT_DIR, "latest_manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)

    existing = db.query(models.ModelVersion).filter(models.ModelVersion.name == manifest["name"]).first()
    if existing:
        return existing

    mv = models.ModelVersion(
        name=manifest["name"],
        algorithm=manifest["algorithm"],
        trained_at=datetime.fromisoformat(manifest["trained_at"]),
        metrics=manifest["metrics"],
        artifact_path=manifest["artifact_path"],
        content_hash=manifest["content_hash"],
        preprocessing_version=manifest["preprocessing_version"],
        is_active=False,
    )
    db.add(mv)
    db.commit()
    db.refresh(mv)
    return mv


def run_and_store_fairness_report(db: Session, model_version: models.ModelVersion) -> models.FairnessReport:
    import joblib
    manifest_path = os.path.join(ARTIFACT_DIR, "latest_manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    model = joblib.load(manifest["artifact_path"])
    test_df = pd.read_csv(os.path.join(ARTIFACT_DIR, "test_holdout.csv"))

    X_test = test_df[ALL_FEATURES]
    y_test = test_df[LABEL_COLUMN].values
    pd_scores = model.predict_proba(X_test)[:, 1]

    report = fairness_mod.run_fairness_audit(y_test, pd_scores, test_df["age_band"].values, "age_band")

    fr = models.FairnessReport(
        model_version_id=model_version.id,
        group_attribute="age_band",
        disparate_impact_ratio=report["min_disparate_impact_ratio"],
        equal_opportunity_diff=report["equal_opportunity_diff"],
        calibration_gap=report["max_calibration_gap"],
        full_report=report,
        flagged=report["flagged_four_fifths_rule"],
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return fr


def run_and_store_drift_report(db: Session, model_version: models.ModelVersion) -> models.DriftReport:
    test_df = pd.read_csv(os.path.join(ARTIFACT_DIR, "test_holdout.csv"))
    # Baseline "current window" = reference itself at startup (no live traffic
    # yet). A real deployment points `current_df` at the last N days of the
    # `applications` table via the scheduled Celery-beat job (Section 13).
    report = drift_mod.compute_drift_report(
        test_df, test_df.sample(frac=0.8, random_state=3), NUMERIC_FEATURES, CATEGORICAL_FEATURES
    )
    dr = models.DriftReport(
        model_version_id=model_version.id,
        feature_psi=report["feature_psi"],
        flagged=report["flagged"],
    )
    db.add(dr)
    db.commit()
    db.refresh(dr)
    return dr


def bootstrap(db: Session) -> None:
    seed_demo_users(db)
    model_version = seed_model_version(db)

    if not db.query(models.FairnessReport).filter(
        models.FairnessReport.model_version_id == model_version.id
    ).first():
        run_and_store_fairness_report(db, model_version)

    if not db.query(models.DriftReport).filter(
        models.DriftReport.model_version_id == model_version.id
    ).first():
        run_and_store_drift_report(db, model_version)

    # Auto-activate at startup for the reference implementation so /predict
    # works out of the box. Attribute the activation to a named seed actor
    # so the audit trail doesn't have to lie about who approved it.
    if not model_version.is_active:
        model_version.is_active = True
        model_version.approved_by = "seed-bootstrap (see README: replace with real sign-off)"
        model_version.approved_at = datetime.now(timezone.utc)
        db.commit()

    background = pd.read_csv(os.path.join(ARTIFACT_DIR, "test_holdout.csv")).sample(n=200, random_state=1)
    manifest_path = os.path.join(ARTIFACT_DIR, "latest_manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    registry.load_from_manifest(manifest, background)
