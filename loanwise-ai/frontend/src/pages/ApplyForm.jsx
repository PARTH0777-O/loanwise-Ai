import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";

const EMPLOYMENT_TYPES = [
  { value: "salaried", label: "Salaried" },
  { value: "self_employed", label: "Self-employed" },
  { value: "contract", label: "Contract" },
  { value: "unemployed", label: "Unemployed" },
];
const AGE_BANDS = ["18-25", "26-35", "36-45", "46-55", "56-65", "65+"];

const initialForm = {
  income: "",
  loan_amount: "",
  tenure_months: "36",
  employment_type: "salaried",
  credit_history_months: "24",
  existing_emi: "0",
  credit_utilization: "0.3",
  num_delinquencies_24m: "0",
  age_band: "26-35",
};

export default function ApplyForm() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        income: Number(form.income),
        loan_amount: Number(form.loan_amount),
        tenure_months: Number(form.tenure_months),
        employment_type: form.employment_type,
        credit_history_months: Number(form.credit_history_months),
        existing_emi: Number(form.existing_emi),
        credit_utilization: Number(form.credit_utilization),
        num_delinquencies_24m: Number(form.num_delinquencies_24m),
        age_band: form.age_band,
      };
      const application = await api.submitApplication(token, payload);
      navigate(`/result/${application.id}`);
    } catch (err) {
      setError(err.detail || "Could not submit application. Check the values above.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="mb-8">
        <p className="font-mono text-xs uppercase tracking-widest text-primary mb-1.5">New submission</p>
        <h1 className="font-display font-semibold text-2xl">Loan application</h1>
        <p className="text-sm text-ink/50 mt-1">
          Every field below is bounds-checked before it reaches the risk model — see the API contract in
          the docs for the full validation rules.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="bg-surface border border-line rounded-lg p-6 space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Annual income" prefix="₹">
            <input type="number" min="1" required value={form.income}
              onChange={(e) => update("income", e.target.value)} className={inputClass} placeholder="600000" />
          </Field>
          <Field label="Loan amount requested" prefix="₹">
            <input type="number" min="1" required value={form.loan_amount}
              onChange={(e) => update("loan_amount", e.target.value)} className={inputClass} placeholder="1500000" />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Tenure (months)">
            <input type="number" min="1" max="480" required value={form.tenure_months}
              onChange={(e) => update("tenure_months", e.target.value)} className={inputClass} />
          </Field>
          <Field label="Employment type">
            <select value={form.employment_type} onChange={(e) => update("employment_type", e.target.value)}
              className={inputClass}>
              {EMPLOYMENT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Credit history (months)">
            <input type="number" min="0" max="600" value={form.credit_history_months}
              onChange={(e) => update("credit_history_months", e.target.value)} className={inputClass} />
          </Field>
          <Field label="Existing monthly EMI" prefix="₹">
            <input type="number" min="0" value={form.existing_emi}
              onChange={(e) => update("existing_emi", e.target.value)} className={inputClass} />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Credit utilization" hint="0.00 – 1.00">
            <input type="number" min="0" max="1" step="0.01" value={form.credit_utilization}
              onChange={(e) => update("credit_utilization", e.target.value)} className={inputClass} />
          </Field>
          <Field label="Delinquencies (24 mo)">
            <input type="number" min="0" max="50" value={form.num_delinquencies_24m}
              onChange={(e) => update("num_delinquencies_24m", e.target.value)} className={inputClass} />
          </Field>
        </div>

        <Field label="Age band" hint="Recorded for fairness auditing only — never passed to the risk model">
          <select value={form.age_band} onChange={(e) => update("age_band", e.target.value)} className={inputClass}>
            {AGE_BANDS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </Field>

        {error && (
          <div className="text-sm text-risk-high bg-risk-highBg px-3 py-2 rounded">{String(error)}</div>
        )}

        <button type="submit" disabled={submitting}
          className="w-full bg-ink text-white py-2.5 rounded font-medium text-sm hover:bg-primary-dark transition-colors disabled:opacity-50">
          {submitting ? "Submitting…" : "Submit & assess risk"}
        </button>
      </form>
    </div>
  );
}

const inputClass = "w-full px-3 py-2 border border-line rounded font-mono text-sm focus:border-primary outline-none bg-white";

function Field({ label, hint, prefix, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-ink/60 mb-1.5">{label}</label>
      <div className="relative">
        {prefix && <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40 text-sm font-mono">{prefix}</span>}
        <div className={prefix ? "[&_input]:pl-7" : ""}>{children}</div>
      </div>
      {hint && <p className="text-[11px] text-ink/40 mt-1">{hint}</p>}
    </div>
  );
}
