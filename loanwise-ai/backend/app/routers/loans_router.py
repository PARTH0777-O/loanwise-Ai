from __future__ import annotations

import uuid

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import auth
import models
import schemas
from audit import log_event
from database import get_db
from ml.preprocessing import ALL_FEATURES, RISK_THRESHOLDS, compute_derived_fields
from ml.registry import registry
from rate_limit import limiter

router = APIRouter(tags=["loans"])


@router.post("/applications", response_model=schemas.ApplicationOut, status_code=status.HTTP_201_CREATED)
def submit_application(
    payload: schemas.ApplicationCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("applicant", "officer", "admin")),
):
    applicant_ref = uuid.uuid4()
    derived = compute_derived_fields({
        "income": payload.income, "loan_amount": payload.loan_amount,
        "tenure_months": payload.tenure_months, "existing_emi": payload.existing_emi,
    })

    application = models.Application(
        applicant_ref=applicant_ref,
        owner_user_id=user.id,
        income=payload.income,
        loan_amount=payload.loan_amount,
        tenure_months=payload.tenure_months,
        employment_type=payload.employment_type,
        credit_history_months=payload.credit_history_months,
        existing_emi=payload.existing_emi,
        dti_ratio=derived["dti_ratio"],
        credit_utilization=payload.credit_utilization,
        num_delinquencies_24m=payload.num_delinquencies_24m,
    )
    db.add(application)
    db.flush()

    # Protected attribute stored ONLY in the separate audit-only table,
    # never on the applications row and never passed to the model.
    protected = models.ApplicantProtected(applicant_ref=applicant_ref, age_band=payload.age_band)
    db.add(protected)

    log_event(db, actor_id=user.id, actor_role=user.role, action="application.submit",
               resource_type="application", resource_id=application.id, commit=False)
    db.commit()
    db.refresh(application)
    return application


def _application_to_frame(app: models.Application) -> pd.DataFrame:
    return pd.DataFrame([{
        "income": float(app.income),
        "loan_amount": float(app.loan_amount),
        "tenure_months": app.tenure_months,
        "employment_type": app.employment_type,
        "credit_history_months": app.credit_history_months,
        "existing_emi": float(app.existing_emi or 0),
        "dti_ratio": float(app.dti_ratio),
        "credit_utilization": float(app.credit_utilization),
        "num_delinquencies_24m": app.num_delinquencies_24m,
    }])[ALL_FEATURES]


@router.post("/predict/{application_id}", response_model=schemas.PredictionResponse)
@limiter.limit("20/minute")
def predict(
    request: Request,
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("applicant", "officer", "admin")),
):
    request.state.user_id = str(user.id)
    application = db.query(models.Application).filter(models.Application.id == application_id).first()
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    active = registry.active
    model, explainer, manifest = active["model"], active["explainer"], active["manifest"]

    X = _application_to_frame(application)
    pd_score = float(model.predict_proba(X)[0, 1])
    risk_category = RISK_THRESHOLDS.categorize(pd_score)
    explanation = explainer.explain(X)

    model_version = db.query(models.ModelVersion).filter(
        models.ModelVersion.name == manifest["name"]
    ).first()
    if model_version is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Active model version not registered in DB")

    prediction = models.Prediction(
        application_id=application.id,
        model_version_id=model_version.id,
        pd_score=pd_score,
        risk_category=risk_category,
        shap_values=explanation,
    )
    db.add(prediction)
    db.flush()

    # Logged BEFORE the response is returned — a crash after this point never
    # produces an unlogged decision (Section 7 contract rules).
    log_event(db, actor_id=user.id, actor_role=user.role, action="prediction.create",
               resource_type="prediction", resource_id=prediction.id,
               metadata={"model_version": manifest["name"], "risk_category": risk_category},
               commit=False)
    db.commit()
    db.refresh(prediction)

    return schemas.PredictionResponse(
        application_id=application.id,
        model_version=manifest["name"],
        pd_score=round(pd_score, 4),
        risk_category=risk_category,
        prediction_id=prediction.id,
    )


@router.get("/explain/{prediction_id}", response_model=schemas.ExplanationResponse)
def explain(
    prediction_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("applicant", "officer", "admin")),
):
    prediction = db.query(models.Prediction).filter(models.Prediction.id == prediction_id).first()
    if prediction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prediction not found")

    log_event(db, actor_id=user.id, actor_role=user.role, action="explanation.view",
               resource_type="prediction", resource_id=prediction.id)

    stored = prediction.shap_values
    return schemas.ExplanationResponse(
        prediction_id=prediction.id,
        top_factors=[schemas.FactorOut(**f) for f in stored["top_factors"]],
        narrative=stored["narrative"],
    )


@router.post("/whatif/{application_id}", response_model=schemas.WhatIfResponse)
@limiter.limit("20/minute")
def whatif(
    request: Request,
    application_id: uuid.UUID,
    payload: schemas.WhatIfRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_roles("applicant", "officer", "admin")),
):
    """Simulation only. Deliberately never writes a new `applications` row —
    otherwise an applicant could spam variations to game the audit trail
    (Section 7 contract rules)."""
    request.state.user_id = str(user.id)
    application = db.query(models.Application).filter(models.Application.id == application_id).first()
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    baseline_X = _application_to_frame(application)
    active = registry.active
    model = active["model"]
    baseline_pd = float(model.predict_proba(baseline_X)[0, 1])

    modified = baseline_X.copy()
    overrides = payload.model_dump(exclude_none=True)
    for field, value in overrides.items():
        if field in modified.columns:
            modified.at[0, field] = value

    # Recompute dti_ratio if any of its inputs changed.
    if any(f in overrides for f in ("income", "loan_amount", "tenure_months")):
        derived = compute_derived_fields({
            "income": modified.at[0, "income"],
            "loan_amount": modified.at[0, "loan_amount"],
            "tenure_months": modified.at[0, "tenure_months"],
            "existing_emi": modified.at[0, "existing_emi"],
        })
        modified.at[0, "dti_ratio"] = derived["dti_ratio"]

    new_pd = float(model.predict_proba(modified[ALL_FEATURES])[0, 1])
    risk_category = RISK_THRESHOLDS.categorize(new_pd)

    # What-if calls ARE still logged (it's a query against a real
    # applicant's data, which is audit-relevant) — just no new application
    # row is created.
    log_event(db, actor_id=user.id, actor_role=user.role, action="whatif.simulate",
               resource_type="application", resource_id=application.id,
               metadata={"overrides": overrides})

    return schemas.WhatIfResponse(
        pd_score=round(new_pd, 4),
        risk_category=risk_category,
        delta_pd=round(new_pd - baseline_pd, 4),
    )
