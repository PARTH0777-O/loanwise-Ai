from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import settings
from database import Base, engine, SessionLocal
from rate_limit import limiter
from routers import auth_router, loans_router, admin_router
import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed.bootstrap(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="LoanWise AI",
    description="Explainable credit risk & loan decision support system — "
                 "decision support, not auto-approval.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Baseline security headers (Section 8.3: TLS/HSTS at the edge in
    # production; these are the application-level headers that complement it).
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.include_router(auth_router.router)
app.include_router(loans_router.router)
app.include_router(admin_router.router)


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak stack traces / internals to the client (information
    # disclosure, Section 8.5). Real error detail goes to server logs only.
    import logging
    logging.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
