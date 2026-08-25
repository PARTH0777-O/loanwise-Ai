"""
ORM models mirroring PRD Section 6, with one deliberate addition:
`applicant_protected` is a separate table from `applications`, holding only
the protected attribute (age_band) used for fairness auditing. It is never
joined at inference time and the prediction code path never queries it —
only the offline fairness-audit job does. In a real Postgres deployment
this table would additionally have its own restrictive GRANT so the
prediction service's DB role literally cannot SELECT from it (documented
in docs/THREAT_MODEL.md since SQLite has no row/table-level GRANT model).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON, TypeDecorator, CHAR

from database import Base


class GUID(TypeDecorator):
    """Portable UUID type: native UUID on Postgres, CHAR(36) on SQLite."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID
            return dialect.type_descriptor(UUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(str(value))


def gen_uuid():
    return uuid.uuid4()


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(GUID, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # applicant | officer | compliance | admin
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Application(Base):
    __tablename__ = "applications"

    id = Column(GUID, primary_key=True, default=gen_uuid)
    applicant_ref = Column(GUID, nullable=False, index=True)
    owner_user_id = Column(GUID, ForeignKey("users.id"), nullable=True)

    income = Column(Numeric, nullable=False)
    loan_amount = Column(Numeric, nullable=False)
    tenure_months = Column(Integer, nullable=False)
    employment_type = Column(String, nullable=False)
    credit_history_months = Column(Integer)
    existing_emi = Column(Numeric)
    dti_ratio = Column(Numeric)  # derived, stored for audit reproducibility
    credit_utilization = Column(Numeric)
    num_delinquencies_24m = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    predictions = relationship("Prediction", back_populates="application")


class ApplicantProtected(Base):
    """Audit-only. Never queried by the prediction/explanation code path."""
    __tablename__ = "applicant_protected"

    id = Column(GUID, primary_key=True, default=gen_uuid)
    applicant_ref = Column(GUID, nullable=False, index=True)
    age_band = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(GUID, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    algorithm = Column(String, nullable=False)
    trained_at = Column(DateTime(timezone=True), nullable=False)
    metrics = Column(JSON, nullable=False)
    artifact_path = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    preprocessing_version = Column(String, nullable=False, default="1.0")
    is_active = Column(Boolean, default=False)
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    predictions = relationship("Prediction", back_populates="model_version")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(GUID, primary_key=True, default=gen_uuid)
    application_id = Column(GUID, ForeignKey("applications.id"), nullable=False)
    model_version_id = Column(GUID, ForeignKey("model_versions.id"), nullable=False)
    pd_score = Column(Numeric, nullable=False)
    risk_category = Column(String, nullable=False)
    shap_values = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    application = relationship("Application", back_populates="predictions")
    model_version = relationship("ModelVersion", back_populates="predictions")


class FairnessReport(Base):
    __tablename__ = "fairness_reports"

    id = Column(GUID, primary_key=True, default=gen_uuid)
    model_version_id = Column(GUID, ForeignKey("model_versions.id"), nullable=False)
    group_attribute = Column(String, nullable=False)
    disparate_impact_ratio = Column(Numeric, nullable=True)
    equal_opportunity_diff = Column(Numeric, nullable=True)
    calibration_gap = Column(Numeric, nullable=True)
    full_report = Column(JSON, nullable=False)
    flagged = Column(Boolean, default=False)
    generated_at = Column(DateTime(timezone=True), default=utcnow)


class DriftReport(Base):
    __tablename__ = "drift_reports"

    id = Column(GUID, primary_key=True, default=gen_uuid)
    model_version_id = Column(GUID, ForeignKey("model_versions.id"), nullable=False)
    feature_psi = Column(JSON, nullable=False)
    flagged = Column(Boolean, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Append-only. In Postgres, the app's DB role is granted INSERT + SELECT
    only — no UPDATE/DELETE (Section 8.4). See migrations/grants.sql."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(GUID, nullable=True)
    actor_role = Column(String, nullable=True)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(GUID, nullable=True)
    audit_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
