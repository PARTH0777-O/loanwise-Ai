# LoanWise AI — Reference Implementation

An explainable credit-risk decision-support system: applicants submit loan
details, get a calibrated probability-of-default estimate with a
plain-language explanation of what drove it, and can explore
what-if scenarios — all behind role-based access control, with every
decision logged to an append-only audit trail, and the model itself
continuously checked for fairness and drift.

This is a **working reference implementation**, not a mockup. Every number
in the [Model Card](docs/MODEL_CARD.md) came from actually running the
training pipeline; the fairness audit actually flagged a real disparity
(see below); every API route was exercised end-to-end during development,
including the failure paths (RBAC denial, invalid input, bad credentials).

## What's real vs. what's a documented gap

**Fully implemented and tested:**
- Synthetic data generation → 3-way model comparison (LogReg/RF/XGBoost)
  → calibration → SHA-256-hashed versioned artifacts
- SHAP-based per-prediction explanations, bounded to top 5 factors
- Fairness audit (disparate impact, equal opportunity, calibration gap)
  that **actually caught the bias** injected into the synthetic data
- PSI-based drift monitoring, verified against both drifted and stable
  populations
- JWT + Argon2id auth, RBAC enforced server-side, rate limiting,
  write-before-response audit logging
- Full API: register/login/refresh, submit application, predict, explain,
  what-if simulate, admin fairness/drift/model-version/audit-log views
- React frontend covering the full applicant and compliance flows

**Documented gaps, not silently omitted** (see [Threat Model](docs/THREAT_MODEL.md)):
- MFA columns exist on the user model but TOTP verification isn't wired
  into login yet
- Refresh tokens are held in-memory in this reference build (a restart
  invalidates all sessions) — production should persist them
- Local dev runs on SQLite; the append-only audit-log guarantee
  (`REVOKE UPDATE, DELETE`) only takes effect in the Postgres deployment
  target, via `backend/migrations/grants.sql`

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   React SPA │─────▶│  FastAPI backend │─────▶│  PostgreSQL       │
│  (Vite,     │      │  (JWT+RBAC,      │      │  - applications    │
│   Tailwind) │      │   rate limiting, │      │  - applicant_protected (audit-only)
└─────────────┘      │   audit logging) │      │  - predictions      │
                      └────────┬─────────┘      │  - model_versions   │
                               │                 │  - fairness_reports │
                               ▼                 │  - drift_reports    │
                      ┌──────────────────┐       │  - audit_logs (append-only)
                      │  Model Registry   │      └─────────────────┘
                      │  (hash-verified   │
                      │   artifact load)  │
                      └────────┬─────────┘
                               ▼
                      RandomForest + SHAP explainer
```

Why Postgres over the SQLite used for local dev: the append-only audit log
guarantee (Threat T5 in the threat model) is enforced at the database
permission layer via `REVOKE UPDATE, DELETE, TRUNCATE`, which SQLite has no
equivalent for. The ORM layer (`backend/app/models.py`) is portable between
both; only `grants.sql` is Postgres-specific.

## Quick start (Docker)

```bash
git clone <this repo>
cd loanwise-ai

# 1. Train the model (writes backend/artifacts/*.joblib + manifest)
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app/data/generate_synthetic.py
python app/ml/train.py
python app/ml/fairness.py    # writes latest_fairness_report.json
python app/ml/drift.py       # writes latest_drift_report.json
cd ..

# 2. Set required secrets
cp .env.example .env   # edit JWT_SECRET_KEY and POSTGRES_PASSWORD

# 3. Bring up the full stack
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:8080

On first boot, `backend/app/seed.py` registers the trained model,
runs the fairness and drift audits, and seeds four demo accounts (one per
role — see `seed.py` for credentials). **The seeded model has a known,
disclosed fairness flag** — see the Model Card before treating this as
production-ready.

## Local dev without Docker

Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd app && uvicorn main:app --reload
# Defaults to a local SQLite file (loanwise.db) — no Postgres needed for dev.
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Repository layout

```
backend/
  app/
    main.py              FastAPI app, middleware, startup bootstrap
    config.py             Environment-driven settings (no hardcoded secrets)
    models.py              SQLAlchemy schema
    schemas.py              Pydantic request/response contracts (bounds-checked)
    auth.py                  Argon2id + JWT + RBAC dependencies
    audit.py                  Write-before-response audit logging helper
    seed.py                    Demo bootstrap (users, model registration, audits)
    routers/                   auth / loans (predict, explain, whatif) / admin
    ml/
      preprocessing.py          Shared feature contract (training + inference)
      train.py                    Model comparison + selection + hashing
      explain.py                   SHAP explanation service
      fairness.py                    Disparate impact / equal opportunity / calibration
      drift.py                        Population Stability Index monitor
      registry.py                      Hash-verified model loading
    data/
      generate_synthetic.py             Synthetic applicant data generator
  migrations/grants.sql                Postgres append-only audit-log grants
  Dockerfile
frontend/                                 React + Vite + Tailwind SPA
docs/
  MODEL_CARD.md                          Honest model documentation, incl. the fairness flag
  THREAT_MODEL.md                         Attack surface + implemented mitigations
docker-compose.yml
```

## Roadmap beyond this reference build

1. **Resolve the fairness flag** on the current model version before any
   real activation — see Model Card for candidate mitigations.
2. Wire TOTP MFA verification into `/auth/login` for compliance/admin roles.
3. Persist refresh tokens (replace the in-memory store in `auth.py`).
4. Point the drift monitor at real trailing-window traffic from
   `applications` instead of a startup sanity-check comparison.
5. Add a scheduled job (Celery beat or equivalent) to re-run fairness and
   drift audits weekly, per the design already in `ml/fairness.py` /
   `ml/drift.py`.
6. Independent security review before handling real applicant data —
   this threat model documents intended mitigations, not an outside audit.
