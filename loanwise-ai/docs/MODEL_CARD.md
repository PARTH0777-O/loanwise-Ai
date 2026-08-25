# Model Card — LoanWise AI Credit Risk Model

**Model version:** `random_forest_v20260820092209`
**Algorithm:** Random Forest (300 trees, max depth 8, min leaf 20), isotonic-calibrated
**Trained:** 2026-08-20
**Content hash (SHA-256):** `7337ae64c60cd22c90f4ca912137e300cb682ab8acf89232197e334746a4f618`

This card documents the model exactly as it is currently registered and
active in the reference deployment. It is generated alongside training —
see `backend/app/ml/train.py`, `fairness.py`, `drift.py` for the code that
produced every number below.

## Intended use

Estimates a **probability of default (PD)** for a loan applicant, to
support (not replace) a human loan officer's decision. Output is always
paired with:
- an explanation of the top contributing factors (SHAP),
- an explicit disclaimer that this is a risk estimate, not a lending
  decision,
- a full audit trail of who requested the estimate and when.

**Out of scope / do not use for:** automated approve/deny decisions
without human review; any jurisdiction where algorithmic credit scoring
requires a specific regulatory certification this reference
implementation does not hold; populations materially different from the
training distribution (see Fairness and Drift sections below).

## Training data

20,000 synthetic applicant records (`backend/app/data/generate_synthetic.py`).
**No real applicant data was used.** The generator encodes a genuine,
learnable default-risk process from income, debt-to-income ratio, credit
history, utilization, delinquency count, and employment type — with an
**intentionally injected mild disparity** tied to applicant age band, so
that this system's fairness auditing has something real to detect rather
than reporting "all clear" by construction. See the module docstring for
the exact mechanism.

Label: synthetic proxy for "90+ days past due within 24 months." Base
rate: 9.97%.

Split: 70% train / 15% validation / 15% test, stratified by label.

## Performance (held-out test set)

| Metric | Value |
|---|---|
| ROC-AUC | **0.8708** |
| F1 | 0.4068 |
| Expected Calibration Error (ECE) | **0.0072** |

Three candidate algorithms (logistic regression, random forest, XGBoost)
were trained and compared; all three cleared the 0.85 AUC target. Random
forest was selected for having the lowest calibration error among
qualifying candidates — see "Why calibration was weighted this heavily"
below.

### Why calibration was weighted this heavily

A model that ranks applicants well (good AUC) but reports a miscalibrated
probability is actively worse than a lower-AUC, well-calibrated model for
this system specifically, because the product's entire premise is
*"here is the number, and here is why."* A PD of 0.30 that is actually a
0.45 doesn't just rank applicants wrong — it makes every explanation
downstream of it wrong too. All three candidates were isotonic-calibrated
post-fit and only kept the calibration wrapper where it measurably
improved ECE.

## Fairness audit results

Run against the held-out test set, protected attribute **age_band**
(never used as a model input — see `ml/preprocessing.py`,
`PROTECTED_ATTRIBUTES`).

| Age band | Approval rate | Disparate impact ratio | Calibration gap |
|---|---|---|---|
| 18-25 | 84.5% | 0.911 | 0.051 |
| 26-35 | 91.5% | 0.986 | 0.007 |
| 36-45 | 92.8% | 1.000 | 0.004 |
| 46-55 | 90.3% | 0.973 | 0.011 |
| 56-65 | 84.6% | 0.912 | 0.031 |
| **65+** | **70.9%** | **0.764** | **0.064** |

**Flagged: yes.** The 65+ band's disparate impact ratio (0.764) falls
below the conventional four-fifths (0.80) screening threshold, and it
also has the model's largest per-group calibration gap.

Equal opportunity difference (max − min true positive rate across
groups): **0.340** — also large; the model is considerably better at
correctly flagging risk for applicants aged 56–65 (TPR 0.788) than for
those aged 26–45 (TPR ≈ 0.45–0.48).

**This is a known, disclosed, unresolved finding**, not a bug we
patched over. Per this system's governance design
(`backend/app/routers/admin_router.py`, `activate_model_version`), a
flagged model is **not blocked automatically** — it can still be
activated, but only by a named human (`approved_by` is required and
logged), and the fairness flag at the moment of activation is recorded
in the audit trail permanently. In the reference deployment this model
was activated by the startup seed script for demo purposes; a real
deployment would require an actual compliance sign-off, and — given this
finding — arguably should not activate this model version as-is. Mitigations
worth evaluating before production use: reweighting the training sample by
age band, a fairness-constrained objective (e.g. exponentiated-gradient
reduction), or a post-hoc threshold adjustment per group with its own
disclosure obligations.

## Drift monitoring

Population Stability Index computed per feature (`ml/drift.py`), flagged
at PSI > 0.2. At registration time (comparing the test holdout against
itself as a stability sanity check), all features report PSI < 0.01 — as
expected, since no live traffic exists yet. See `/admin/drift-reports`
for the current live report once real application traffic accumulates;
the monitoring job is designed to run weekly against a trailing window
(Section 10 of the PRD).

## Explainability

Per-prediction explanations use SHAP (`TreeExplainer` for this model),
bounded to the top 5 contributing factors by absolute impact, per
`backend/app/ml/explain.py`. This bound is deliberate: unbounded
explanation output increases model-extraction attack surface (Section
8.2) without adding proportional value for a human reviewer.

## Known limitations

1. **Synthetic data.** All numbers on this card describe how well the
   model fits a synthetic data-generating process, not real-world credit
   risk. Before any production use, this entire pipeline must be
   retrained on real, compliant data with its own fairness and
   performance evaluation.
2. **Unresolved fairness flag** (above) — do not treat this model version
   as production-ready without addressing it.
3. **F1 of 0.41** reflects the realistic ~10% base default rate — at this
   class imbalance, precision/recall trade-offs deserve more scrutiny
   than a single F1 number gives; see the full precision-recall curve
   before setting an operating threshold, if this were a live deployment.
4. Risk category thresholds (LOW < 0.10, MEDIUM < 0.25, HIGH ≥ 0.25) are
   illustrative, calibrated loosely against this training distribution —
   not a regulatory or actuarial determination.
