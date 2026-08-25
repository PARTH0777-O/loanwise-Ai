"""
Synthetic loan-applicant dataset generator.

Why synthetic, and why not just random noise:
- No real applicant PII is used anywhere in this system (PRD non-goal, Section 2).
- The data-generating process below encodes a genuine, learnable default-risk
  signal (DTI, credit history, income-to-loan ratio, employment stability,
  utilization) so that model comparison (LogReg vs RF vs XGBoost) and
  calibration are meaningful, not fitting noise.
- We also inject a *mild, realistic* correlation between a protected
  attribute (age_band) and both the label and a feature, on purpose. This is
  what makes the fairness audit module (Section 9) something that actually
  finds something, instead of a pipeline stage that always reports "all
  clear" because it was never tested against a biased signal.

The protected attribute is generated independently of the modeling features
used at inference time and is stored only in `applicant_protected` — the
model never sees it. See db.models for the separation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class SyntheticDataConfig:
    n_samples: int = 20_000
    random_state: int = 42


EMPLOYMENT_TYPES = ["salaried", "self_employed", "contract", "unemployed"]
AGE_BANDS = ["18-25", "26-35", "36-45", "46-55", "56-65", "65+"]


def generate(config: SyntheticDataConfig = SyntheticDataConfig()) -> pd.DataFrame:
    rng = np.random.default_rng(config.random_state)
    n = config.n_samples

    # --- Base demographics / protected attribute (audit-only, never a model feature) ---
    age_band = rng.choice(AGE_BANDS, size=n, p=[0.12, 0.28, 0.24, 0.18, 0.12, 0.06])
    age_idx = pd.Series(age_band).map({b: i for i, b in enumerate(AGE_BANDS)}).values

    # --- Modeling features ---
    income = np.clip(rng.lognormal(mean=10.5, sigma=0.55, size=n), 8_000, 2_000_000)

    employment_probs_by_age = np.array([
        [0.35, 0.10, 0.35, 0.20],  # 18-25: more contract/unemployed
        [0.55, 0.15, 0.22, 0.08],
        [0.62, 0.18, 0.15, 0.05],
        [0.58, 0.20, 0.14, 0.08],
        [0.45, 0.20, 0.15, 0.20],
        [0.20, 0.15, 0.10, 0.55],  # 65+: mostly retired/unemployed bucket
    ])
    employment_type = np.array([
        rng.choice(EMPLOYMENT_TYPES, p=employment_probs_by_age[a]) for a in age_idx
    ])

    credit_history_months = np.clip(
        (age_idx * 36 + rng.normal(24, 30, size=n)), 0, 480
    ).astype(int)

    loan_amount = np.clip(rng.lognormal(mean=9.7, sigma=0.6, size=n), 5_000, 5_000_000)
    tenure_months = rng.choice([12, 24, 36, 48, 60, 84, 120], size=n,
                                p=[0.05, 0.15, 0.25, 0.2, 0.2, 0.1, 0.05])

    monthly_income = income / 12
    existing_emi = np.clip(rng.normal(monthly_income * 0.15, monthly_income * 0.1), 0, None)
    proposed_emi = loan_amount / tenure_months * 1.08  # rough amortization proxy
    dti_ratio = np.clip((existing_emi + proposed_emi) / np.maximum(monthly_income, 1), 0, 3)

    credit_utilization = np.clip(rng.beta(2, 3, size=n), 0, 1)
    num_delinquencies_24m = rng.poisson(
        lam=np.clip(0.15 + dti_ratio * 0.5 + credit_utilization * 0.4, 0.05, None)
    )

    # --- True default-generating process (logit form) ---
    employment_risk = np.select(
        [employment_type == "salaried", employment_type == "self_employed",
         employment_type == "contract", employment_type == "unemployed"],
        [-0.35, 0.05, 0.25, 1.1],
    )

    # Small, intentional age-band effect independent of the "real" risk drivers
    # above — this is the injected bias the fairness audit is meant to catch.
    age_band_bias = np.select(
        [age_idx == 0, age_idx == 5],  # youngest and oldest bands
        [0.28, 0.22],
        default=0.0,
    )

    logit = (
        -5.2
        + 4.0 * dti_ratio
        - 0.16 * np.log1p(credit_history_months)
        + 2.8 * credit_utilization
        + 0.65 * num_delinquencies_24m
        + 1.9 * employment_risk
        - 0.4 * np.log1p(income / 50_000)
        + age_band_bias
        + rng.normal(0, 0.24, size=n)  # idiosyncratic noise (reduced vs. signal)
    )
    pd_true = 1 / (1 + np.exp(-logit))
    defaulted = rng.binomial(1, pd_true)

    df = pd.DataFrame({
        "applicant_ref": [f"app_{i:06d}" for i in range(n)],
        "income": income.round(2),
        "loan_amount": loan_amount.round(2),
        "tenure_months": tenure_months,
        "employment_type": employment_type,
        "credit_history_months": credit_history_months,
        "existing_emi": existing_emi.round(2),
        "dti_ratio": dti_ratio.round(4),
        "credit_utilization": credit_utilization.round(4),
        "num_delinquencies_24m": num_delinquencies_24m,
        "age_band": age_band,  # protected attribute, audit-only
        "defaulted": defaulted,  # label: 90+ DPD within 24mo (synthetic definition)
    })
    return df


if __name__ == "__main__":
    df = generate()
    out_path = "/home/claude/loanwise-ai/backend/app/data/synthetic_loans.csv"
    df.to_csv(out_path, index=False)
    print(df.shape)
    print(df["defaulted"].mean())
    print(df.groupby("age_band")["defaulted"].mean())
