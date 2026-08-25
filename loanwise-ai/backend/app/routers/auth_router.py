from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import auth
import models
import schemas
from audit import log_event
from database import get_db
from rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    """Reference-implementation convenience endpoint. A production deployment
    would gate role != 'applicant' behind an admin-only invite flow instead
    of open self-registration."""
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = models.User(
        email=payload.email,
        password_hash=auth.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event(db, actor_id=user.id, actor_role=user.role, action="user.register",
               resource_type="user", resource_id=user.id)
    return user


@router.post("/login", response_model=schemas.TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    # Constant-shape failure: don't reveal whether the email exists.
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        log_event(db, actor_id=None, actor_role=None, action="auth.login_failed",
                   resource_type="user", metadata={"email": payload.email})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    access = auth.create_access_token(user)
    refresh = auth.create_refresh_token(user)
    log_event(db, actor_id=user.id, actor_role=user.role, action="auth.login",
               resource_type="user", resource_id=user.id)
    return schemas.TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    access, refresh_token, user = auth.rotate_refresh_token(payload.refresh_token, db)
    log_event(db, actor_id=user.id, actor_role=user.role, action="auth.refresh",
               resource_type="user", resource_id=user.id)
    return schemas.TokenResponse(access_token=access, refresh_token=refresh_token)


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.get_current_user)):
    return user
