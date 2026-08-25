import { useState, useCallback, useRef } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import PdGauge, { riskColor } from "../components/PdGauge";

export default function WhatIf() {
  const { applicationId } = useParams();
  const { token } = useAuth();
  const [overrides, setOverrides] = useState({
    credit_utilization: 0.3,
    existing_emi: 0,
    num_delinquencies_24m: 0,
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);

  const runSimulation = useCallback((next) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api.whatIf(token, applicationId, next);
        setResult(res);
      } catch {
        // silently ignore transient errors during slider drag
      } finally {
        setLoading(false);
      }
    }, 250);
  }, [applicationId, token]);

  function update(field, value) {
    const next = { ...overrides, [field]: value };
    setOverrides(next);
    runSimulation(next);
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-primary mb-1.5">Simulation</p>
      <h1 className="font-display font-semibold text-2xl mb-1">What-if explorer</h1>
      <p className="text-sm text-ink/50 mb-6">
        Adjust the sliders to see how the risk estimate would change. Nothing here is saved — this is a
        hypothetical simulation against your submitted application.
      </p>

      <div className="bg-surface border border-line rounded-lg p-6 space-y-6 mb-6">
        <Slider
          label="Credit utilization"
          value={overrides.credit_utilization}
          min={0} max={1} step={0.01}
          format={(v) => v.toFixed(2)}
          onChange={(v) => update("credit_utilization", v)}
        />
        <Slider
          label="Existing monthly EMI"
          value={overrides.existing_emi}
          min={0} max={50000} step={500}
          format={(v) => `₹${v.toLocaleString()}`}
          onChange={(v) => update("existing_emi", v)}
        />
        <Slider
          label="Delinquencies (24 months)"
          value={overrides.num_delinquencies_24m}
          min={0} max={10} step={1}
          format={(v) => v}
          onChange={(v) => update("num_delinquencies_24m", v)}
        />
      </div>

      <div className="bg-surface border border-line rounded-lg p-6">
        {result ? (
          <>
            <div className="flex items-baseline justify-between mb-4">
              <div>
                <div
                  className="text-3xl font-mono font-semibold transition-opacity"
                  style={{ color: riskColor(result.risk_category), opacity: loading ? 0.5 : 1 }}
                >
                  {(result.pd_score * 100).toFixed(1)}%
                </div>
                <div className="text-xs text-ink/40 mt-1">simulated probability of default</div>
              </div>
              <DeltaBadge delta={result.delta_pd} />
            </div>
            <PdGauge pdScore={result.pd_score} />
            <p className="text-xs text-ink/40 italic mt-4">{result.disclaimer}</p>
          </>
        ) : (
          <div className="text-center py-6 text-ink/40 font-mono text-sm">
            {loading ? "Simulating…" : "Adjust a slider to see the simulated result."}
          </div>
        )}
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, format, onChange }) {
  return (
    <div>
      <div className="flex justify-between mb-2">
        <label className="text-sm font-medium text-ink/70">{label}</label>
        <span className="font-mono text-sm text-primary-dark">{format(value)}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-primary"
      />
    </div>
  );
}

function DeltaBadge({ delta }) {
  const isDown = delta < 0;
  const isFlat = Math.abs(delta) < 0.001;
  const color = isFlat ? "#12181F80" : isDown ? "#1E7F6E" : "#B23A2E";
  const arrow = isFlat ? "→" : isDown ? "↓" : "↑";
  return (
    <span className="font-mono text-sm px-2.5 py-1 rounded" style={{ color, backgroundColor: `${color}1A` }}>
      {arrow} {Math.abs(delta * 100).toFixed(1)} pts vs. baseline
    </span>
  );
}
