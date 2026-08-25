import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import PdGauge, { riskColor } from "../components/PdGauge";

export default function Result() {
  const { applicationId } = useParams();
  const { token } = useAuth();
  const [prediction, setPrediction] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      try {
        const pred = await api.predict(token, applicationId);
        if (cancelled) return;
        setPrediction(pred);
        const exp = await api.explain(token, pred.prediction_id);
        if (cancelled) return;
        setExplanation(exp);
      } catch (err) {
        if (!cancelled) setError(err.detail || "Could not generate a prediction for this application.");
      }
    }
    run();
    return () => { cancelled = true; };
  }, [applicationId, token]);

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="bg-risk-highBg text-risk-high px-4 py-3 rounded">{String(error)}</div>
      </div>
    );
  }

  if (!prediction) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center text-ink/40 font-mono text-sm">
        Scoring application…
      </div>
    );
  }

  const color = riskColor(prediction.risk_category);

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-primary mb-1.5">Assessment result</p>
      <h1 className="font-display font-semibold text-2xl mb-6">Risk estimate</h1>

      <div className="bg-surface border border-line rounded-lg p-6 mb-4">
        <div className="flex items-baseline justify-between mb-5">
          <div>
            <div className="text-4xl font-mono font-semibold" style={{ color }}>
              {(prediction.pd_score * 100).toFixed(1)}%
            </div>
            <div className="text-xs text-ink/40 mt-1">probability of default</div>
          </div>
          <span
            className="font-mono text-xs font-semibold px-3 py-1.5 rounded uppercase tracking-wide"
            style={{ color, backgroundColor: `${color}1A` }}
          >
            {prediction.risk_category} risk
          </span>
        </div>

        <PdGauge pdScore={prediction.pd_score} />

        <div className="ledger-rule mt-6 pt-4">
          <p className="text-xs text-ink/50 italic">{prediction.disclaimer}</p>
          <p className="font-mono text-[11px] text-ink/30 mt-2">
            Model: {prediction.model_version} · Prediction ID: {prediction.prediction_id.slice(0, 8)}
          </p>
        </div>
      </div>

      {explanation && (
        <div className="bg-surface border border-line rounded-lg p-6 mb-4">
          <h2 className="font-display font-semibold text-sm uppercase tracking-wide text-ink/60 mb-4">
            What drove this estimate
          </h2>
          <p className="text-sm text-ink/70 mb-5">{explanation.narrative}</p>

          <div className="space-y-2.5">
            {explanation.top_factors.map((f, i) => (
              <FactorBar key={i} factor={f} />
            ))}
          </div>
        </div>
      )}

      <Link
        to={`/whatif/${applicationId}`}
        className="block text-center bg-ink text-white py-2.5 rounded font-medium text-sm hover:bg-primary-dark transition-colors"
      >
        Explore what-if scenarios
      </Link>
    </div>
  );
}

function FactorBar({ factor }) {
  const magnitude = Math.min(1, Math.abs(factor.impact) / 0.3);
  const isRisk = factor.direction === "increases_risk";
  const color = isRisk ? "#B23A2E" : "#1E7F6E";
  const name = factor.feature.replace(/_/g, " ").replace("=", ": ");

  return (
    <div className="flex items-center gap-3">
      <div className="w-40 text-xs text-ink/70 truncate" title={name}>{name}</div>
      <div className="flex-1 h-5 bg-paper rounded-sm overflow-hidden relative">
        <div
          className="h-full rounded-sm transition-all"
          style={{ width: `${magnitude * 100}%`, backgroundColor: color, opacity: 0.75 }}
        />
      </div>
      <div className="w-14 text-right font-mono text-xs" style={{ color }}>
        {isRisk ? "+" : "−"}{Math.abs(factor.impact).toFixed(3)}
      </div>
    </div>
  );
}
