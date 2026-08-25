"""
Audit logging (PRD Section 7 contract rules, Section 8.4).

`log_event` is called synchronously, in-transaction, BEFORE the response is
constructed and returned — so a crash between "decision made" and "response
sent" can never produce an unlogged decision. This is why routers call
`log_event(db, ...)` and `db.commit()` prior to building the response body,
not in a background task or `finally` block.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

import models


def log_event(
    db: Session,
    *,
    actor_id: uuid.UUID | None,
    actor_role: str | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    metadata: dict | None = None,
    commit: bool = True,
) -> models.AuditLog:
    entry = models.AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        audit_metadata=metadata or {},
    )
    db.add(entry)
    db.flush()  # assign id, catch constraint errors before we tell the caller it worked
    if commit:
        db.commit()
    return entry
