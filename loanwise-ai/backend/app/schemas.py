from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["applicant", "officer", "compliance", "admin"]
EmploymentType = Literal["salaried", "self_employed", "contract", "unemployed"]


# ---------- Auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: Role = "applicant"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    role: Role
    mfa_enabled: bool


# ---------- Applications ----------
# Every numeric field carries explicit bounds — malformed or adversarial
# input is rejected before it ever reaches preprocessing or the model
# (Section 7 contract rules, Section 8.2).
class ApplicationCreate(BaseModel):
    income: float = Field(gt=0, le=50_000_000, description="Annual income")
    loan_amount: float = Field(gt=0, le=100_000_000)
    tenure_months: int = Field(ge=1, le=480)
    employment_type: EmploymentType
    credit_history_months: int = Field(ge=0, le=600, default=0)
    existing_emi: float = Field(ge=0, le=10_000_000, default=0)
    credit_utilization: float = Field(ge=0, le=1, default=0.3)
    num_delinquencies_24m: int = Field(ge=0, le=50, default=0)
    age_band: Literal["18-25", "26-35", "36-45", "46-55", "56-65", "65+"]


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    applicant_ref: uuid.UUID
    income: float
    loan_amount: float
    tenure_months: int
    employment_type: str
    credit_history_months: int
    existing_emi: float
    dti_ratio: float
    credit_utilization: float
    num_delinquencies_24m: int
    created_at: datetime


# ---------- Predictions ----------
class PredictionResponse(BaseModel):
    application_id: uuid.UUID
    model_version: str
    pd_score: float
    risk_category: str
    disclaimer: str = "This is a model-based risk estimate, not a final lending decision."
    prediction_id: uuid.UUID


class FactorOut(BaseModel):
    feature: str
    impact: float
    direction: Literal["increases_risk", "decreases_risk"]


class ExplanationResponse(BaseModel):
    prediction_id: uuid.UUID
    top_factors: list[FactorOut]
    narrative: str


class WhatIfRequest(BaseModel):
    """Simulation only — never persisted as a new application (Section 7)."""
    income: Optional[float] = Field(default=None, gt=0, le=50_000_000)
    loan_amount: Optional[float] = Field(default=None, gt=0, le=100_000_000)
    tenure_months: Optional[int] = Field(default=None, ge=1, le=480)
    employment_type: Optional[EmploymentType] = None
    credit_history_months: Optional[int] = Field(default=None, ge=0, le=600)
    existing_emi: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    credit_utilization: Optional[float] = Field(default=None, ge=0, le=1)
    num_delinquencies_24m: Optional[int] = Field(default=None, ge=0, le=50)


class WhatIfResponse(BaseModel):
    pd_score: float
    risk_category: str
    delta_pd: float
    disclaimer: str = "This is a hypothetical simulation only, not linked to any stored application."


# ---------- Admin ----------
class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    algorithm: str
    trained_at: datetime
    metrics: dict
    is_active: bool
    approved_by: Optional[str]
    approved_at: Optional[datetime]


class ActivateModelRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=200)


class FairnessReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    model_version_id: uuid.UUID
    group_attribute: str
    flagged: bool
    full_report: dict
    generated_at: datetime


class DriftReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    model_version_id: uuid.UUID
    feature_psi: dict
    flagged: bool
    generated_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: Optional[uuid.UUID]
    actor_role: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[uuid.UUID]
    audit_metadata: Optional[dict]
    created_at: datetime
