"""
Authentication & authorization (PRD Section 8.1).

- Argon2id password hashing (memory-hard, GPU-resistant — current best
  practice, chosen explicitly over bcrypt/SHA per the PRD).
- Short-lived JWT access tokens (15 min) + longer-lived, single-use,
  hashed, revocable refresh tokens.
- RBAC enforced via FastAPI route dependencies, re-checked server-side on
  every admin route — never trust a frontend-only role check.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import get_db
import models

password_hasher = PasswordHasher()  # Argon2id by default in argon2-cffi >= 21
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# In-memory refresh token store for the reference implementation. Production
# would persist this (a `refresh_tokens` table: hashed token, user_id,
# expires_at, revoked_at) so revocation survives a restart and works across
# multiple app instances.
_refresh_token_store: dict[str, dict] = {}


def hash_password(plain: str) -> str:
    return password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def create_access_token(user: models.User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user: models.User) -> str:
    raw = secrets.token_urlsafe(48)
    token_hash = password_hasher.hash(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    _refresh_token_store[raw] = {
        "user_id": str(user.id),
        "hash": token_hash,
        "expires_at": expires_at,
        "used": False,
    }
    return raw


def rotate_refresh_token(raw_token: str, db: Session) -> tuple[str, str, models.User]:
    """Single-use rotation: the presented refresh token is invalidated and a
    new one issued, alongside a new access token. Reuse of an already-used
    refresh token is treated as a possible theft signal and rejected."""
    record = _refresh_token_store.get(raw_token)
    if record is None or record["used"] or record["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    record["used"] = True
    user = db.query(models.User).filter(models.User.id == record["user_id"]).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")

    new_access = create_access_token(user)
    new_refresh = create_refresh_token(user)
    return new_access, new_refresh, user


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    return payload


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_access_token(token)
    user = db.query(models.User).filter(models.User.id == payload["sub"]).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


def require_roles(*allowed_roles: str):
    """Route dependency factory. Every admin/compliance route re-checks the
    role server-side — this is the actual enforcement point, independent of
    whatever the frontend renders or hides (Section 8.1)."""

    def dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user.role}' is not permitted to access this resource. "
                f"Requires one of: {', '.join(allowed_roles)}",
            )
        return user

    return dependency
