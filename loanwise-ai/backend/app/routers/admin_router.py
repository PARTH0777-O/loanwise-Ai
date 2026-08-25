from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import auth
import models
import schemas
from audit import log_event
from database import get_db
from ml.registry import registry

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/fairness-reports", response_model=list[schemas.FairnessReportOut])
def list_fairness_reports(
    model_version_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("compliance", "admin")),
):
    q = db.query(models.FairnessReport)
    if model_version_id:
        q = q.filter(models.FairnessReport.model_version_id == model_version_id)
    reports = q.order_by(models.FairnessReport.generated_at.desc()).all()
    log_event(db, actor_id=user.id, actor_role=user.role, action="fairness_report.list",
               resource_type="fairness_report")
    return reports


@router.get("/drift-reports", response_model=list[schemas.DriftReportOut])
def list_drift_reports(
    model_version_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("compliance", "admin")),
):
    q = db.query(models.DriftReport)
    if model_version_id:
        q = q.filter(models.DriftReport.model_version_id == model_version_id)
    reports = q.order_by(models.DriftReport.generated_at.desc()).all()
    log_event(db, actor_id=user.id, actor_role=user.role, action="drift_report.list",
               resource_type="drift_report")
    return reports


@router.get("/model-versions", response_model=list[schemas.ModelVersionOut])
def list_model_versions(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("admin", "compliance")),
):
    versions = db.query(models.ModelVersion).order_by(models.ModelVersion.trained_at.desc()).all()
    log_event(db, actor_id=user.id, actor_role=user.role, action="model_version.list",
               resource_type="model_version")
    return versions


@router.post("/model-versions/{model_version_id}/activate", response_model=schemas.ModelVersionOut)
def activate_model_version(
    model_version_id: uuid.UUID,
    payload: schemas.ActivateModelRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("admin")),
):
    """Activating a model is a deliberate, logged, human-attributed action
    (`approved_by`) — never automatic, per Section 9 point 2: a model that
    fails the four-fifths rule isn't blocked automatically, but it can't be
    silently deployed either."""
    target = db.query(models.ModelVersion).filter(models.ModelVersion.id == model_version_id).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model version not found")

    latest_fairness = (
        db.query(models.FairnessReport)
        .filter(models.FairnessReport.model_version_id == model_version_id)
        .order_by(models.FairnessReport.generated_at.desc())
        .first()
    )
    fairness_flagged = bool(latest_fairness.flagged) if latest_fairness else None

    # Deactivate current active version, activate target — logged either way.
    db.query(models.ModelVersion).filter(models.ModelVersion.is_active == True).update(  # noqa: E712
        {"is_active": False}
    )
    target.is_active = True
    target.approved_by = payload.approved_by
    from datetime import datetime, timezone
    target.approved_at = datetime.now(timezone.utc)
    db.flush()

    log_event(
        db, actor_id=user.id, actor_role=user.role, action="model_version.activate",
        resource_type="model_version", resource_id=target.id,
        metadata={"approved_by": payload.approved_by, "fairness_flagged_at_activation": fairness_flagged},
        commit=False,
    )
    db.commit()
    db.refresh(target)

    # Hot-swap the in-memory registry so /predict immediately uses the newly
    # activated model — reload from its manifest.
    import json
    with open(target.artifact_path.replace(".joblib", ".manifest.json")) as f:
        manifest = json.load(f)
    import pandas as pd, os
    holdout_path = os.path.join(os.path.dirname(target.artifact_path), "test_holdout.csv")
    background = pd.read_csv(holdout_path).sample(n=200, random_state=1)
    registry.load_from_manifest(manifest, background)

    return target


@router.get("/audit-logs", response_model=list[schemas.AuditLogOut])
def query_audit_logs(
    resource_type: str | None = None,
    action: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("compliance", "admin")),
):
    q = db.query(models.AuditLog)
    if resource_type:
        q = q.filter(models.AuditLog.resource_type == resource_type)
    if action:
        q = q.filter(models.AuditLog.action == action)
    logs = q.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    # Querying the audit trail is itself audit-worthy (compliance access to
    # sensitive logs should be traceable too).
    log_event(db, actor_id=user.id, actor_role=user.role, action="audit_log.query",
               resource_type="audit_log", metadata={"filters": {"resource_type": resource_type, "action": action}})
    return logs
