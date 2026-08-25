# Threat Model — LoanWise AI

This documents the attack surface actually present in this reference
implementation, and what is (and isn't) mitigated. Written to be checked
against the code, not aspirational.

## Assets to protect

1. Applicant financial data (`applications` table)
2. Protected attributes used only for fairness auditing (`applicant_protected`)
3. Model artifacts (a stolen/tampered model can misprice risk at scale)
4. The audit trail itself (its value depends on being tamper-evident)
5. Credentials / session tokens

## Threats and mitigations

### T1 — Credential compromise / brute force
**Mitigation:** Argon2id password hashing (`auth.py`), rate-limited login
(10/min, `rate_limit_login`), short-lived (15 min) access tokens, single-use
rotating refresh tokens with theft-reuse detection (`rotate_refresh_token`).
**Not implemented in this reference build:** MFA enforcement (the `User`
model has `mfa_enabled`/`mfa_secret` columns and demo compliance/admin
accounts are seeded with `mfa_enabled=True`, but TOTP verification itself
is not wired into `/auth/login`). Flagged as a gap, not silently omitted.

### T2 — Privilege escalation via role tampering
**Mitigation:** role lives in the JWT claims signed server-side
(`create_access_token`) and is independently re-checked on every
sensitive route via `require_roles(...)` (`auth.py`). The frontend hiding
a nav link is UX only — it is never the enforcement point. Verified by
the RBAC test in the development log (applicant → `/admin/*` returns 403).

### T3 — Model extraction via repeated querying
**Mitigation:** per-identity rate limiting on `/predict` and `/whatif`
(20/min, `rate_limit.py`), and explanation output is bounded to the top 5
SHAP factors (`ml/explain.py`, `TOP_N_FACTORS`) rather than full feature
attribution — both deliberately reduce how much of the decision boundary
an attacker can reconstruct per unit of API access.
**Residual risk:** 20/min still permits meaningful boundary-mapping over
days; a production deployment should add anomaly detection on
`whatif` query patterns per user, not just a flat rate.

### T4 — Artifact tampering (swapped/corrupted model file)
**Mitigation:** every artifact is content-hashed (SHA-256) at save time
(`ml/train.py`, `save_artifact`) and the hash is re-verified before load
(`ml/registry.py`, `ArtifactIntegrityError`). A modified `.joblib` file —
whether from disk corruption or a compromised deployment pipeline — is
refused at startup/activation rather than silently loaded.

### T5 — Audit log tampering or deletion
**Mitigation, Postgres deployment only:** `migrations/grants.sql` grants
the application's runtime DB role `INSERT, SELECT` on `audit_logs` and
explicitly `REVOKE`s `UPDATE, DELETE, TRUNCATE`. Even full RCE against the
running application server cannot rewrite history through the app's own
DB connection — only a separately authenticated superuser connection can,
and that connection is logged at the infrastructure layer.
**Caveat:** the SQLite configuration used for local development in this
reference build has no equivalent row/table permission model — this
protection is real only in the Postgres deployment target. Documented,
not silently assumed.

### T6 — Protected-attribute leakage into the model or into an
unauthorized read path
**Mitigation:** `age_band` is stored in a separate table
(`applicant_protected`), is never included in `ALL_FEATURES`
(`preprocessing.py`), and the prediction/explanation code path never
queries that table — only the offline fairness-audit code does. In the
Postgres deployment, `grants.sql` additionally denies the app's runtime
role any grant on `applicant_protected` at all, so this separation holds
even against an application-layer bug that tried to join it.

### T7 — Information disclosure via error messages
**Mitigation:** a global exception handler (`main.py`,
`unhandled_exception_handler`) returns a generic 500 to the client and
logs the real stack trace server-side only. Login failure responses are
identical whether the email doesn't exist or the password is wrong
(`routers/auth_router.py`) to avoid user enumeration.

### T8 — Malformed / adversarial input reaching the model
**Mitigation:** every numeric field in `schemas.py` carries explicit
`gt`/`ge`/`le` bounds (income, loan amount, tenure, utilization, etc.) —
Pydantic rejects out-of-range or wrong-typed input with a 422 before it
reaches preprocessing, verified in testing (negative income → 422).

### T9 — Man-in-the-middle / transport security
**Mitigation (production only):** `Strict-Transport-Security` header is
set when `ENVIRONMENT=production` (`main.py`). TLS termination itself is
expected at the load balancer / ingress, not in this application code —
document this clearly for whoever deploys it, since the app cannot
enforce TLS on its own.

### T10 — Undetected data drift silently degrading model quality
Not a security threat in the classic sense, but a decision-integrity one:
a model whose input population has shifted can systematically misprice
risk without any error being thrown. Mitigated by the PSI-based drift
monitor (`ml/drift.py`) intended to run on a weekly schedule against
live traffic; verified to correctly flag simulated drift and stay silent
on a stable population.

## Explicitly out of scope for this reference implementation

- DDoS / infrastructure-layer protection (expected from the hosting
  platform, e.g. a WAF/CDN in front of this API)
- Secrets management beyond environment variables (`config.py` documents
  that production secrets belong in a real secrets manager, not `.env`)
- Formal penetration testing — this document describes intended
  mitigations as implemented, not the output of an independent audit
