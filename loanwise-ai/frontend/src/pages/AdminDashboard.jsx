import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";

const TABS = ["Fairness", "Drift", "Models", "Audit log"];

export default function AdminDashboard() {
  const [tab, setTab] = useState("Fairness");

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <p className="font-mono text-xs uppercase tracking-widest text-primary mb-1.5">Governance</p>
      <h1 className="font-display font-semibold text-2xl mb-6">Model oversight</h1>

      <div className="flex gap-1 mb-6 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? "border-primary text-primary" : "border-transparent text-ink/50 hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Fairness" && <FairnessTab />}
      {tab === "Drift" && <DriftTab />}
      {tab === "Models" && <ModelsTab />}
      {tab === "Audit log" && <AuditTab />}
    </div>
  );
}

function Card({ children }) {
  return <div className="bg-surface border border-line rounded-lg p-6">{children}</div>;
}

function useLoad(fn) {
  const { token } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fn(token).then((d) => !cancelled && setData(d)).catch((e) => !cancelled && setError(e));
    return () => { cancelled = true; };
  }, [token]);
  return { data, error };
}

function FairnessTab() {
  const { data: reports, error } = useLoad(api.fairnessReports);
  if (error) return <ErrorBox err={error} />;
  if (!reports) return <Loading />;
  if (reports.length === 0) return <EmptyBox text="No fairness reports have been generated yet." />;

  return (
    <div className="space-y-5">
      {reports.map((r) => {
        const dir = r.full_report.disparate_impact_ratio;
        return (
          <Card key={r.id}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-display font-semibold text-sm">
                  Protected attribute: <span className="font-mono text-primary-dark">{r.group_attribute}</span>
                </h3>
                <p className="text-xs text-ink/40 mt-0.5">
                  Generated {new Date(r.generated_at).toLocaleString()}
                </p>
              </div>
              <FlagBadge flagged={r.flagged} passText="Passes 4/5ths rule" failText="Below 4/5ths threshold" />
            </div>

            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink/40 uppercase tracking-wide">
                  <th className="pb-2 font-medium">Group</th>
                  <th className="pb-2 font-medium text-right">Approval rate</th>
                  <th className="pb-2 font-medium text-right">Disparate impact ratio</th>
                  <th className="pb-2 font-medium text-right">Calibration gap</th>
                </tr>
              </thead>
              <tbody className="font-mono text-xs">
                {Object.keys(dir).map((group) => {
                  const ratio = dir[group];
                  const flagged = ratio < 0.8;
                  return (
                    <tr key={group} className="border-t border-line">
                      <td className="py-2 font-body">{group}</td>
                      <td className="py-2 text-right">
                        {(r.full_report.approval_rate_by_group[group] * 100).toFixed(1)}%
                      </td>
                      <td className={`py-2 text-right font-semibold ${flagged ? "text-risk-high" : "text-ink"}`}>
                        {ratio.toFixed(3)}
                      </td>
                      <td className="py-2 text-right">
                        {r.full_report.calibration_gap_by_group[group]?.toFixed(3) ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="text-[11px] text-ink/40 mt-3">
              Four-fifths rule: any group's approval rate below 80% of the most-favored group's rate is
              flagged for review. This is a screening heuristic, not a legal determination.
            </p>
          </Card>
        );
      })}
    </div>
  );
}

function DriftTab() {
  const { data: reports, error } = useLoad(api.driftReports);
  if (error) return <ErrorBox err={error} />;
  if (!reports) return <Loading />;
  if (reports.length === 0) return <EmptyBox text="No drift reports have been generated yet." />;

  return (
    <div className="space-y-5">
      {reports.map((r) => (
        <Card key={r.id}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-display font-semibold text-sm">Population Stability Index</h3>
              <p className="text-xs text-ink/40 mt-0.5">Generated {new Date(r.generated_at).toLocaleString()}</p>
            </div>
            <FlagBadge flagged={r.flagged} passText="Population stable" failText="Drift detected" />
          </div>
          <div className="space-y-2">
            {Object.entries(r.feature_psi).map(([feature, psi]) => (
              <PsiBar key={feature} feature={feature} psi={psi} />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function PsiBar({ feature, psi }) {
  const breached = psi > 0.2;
  const watch = psi > 0.1 && psi <= 0.2;
  const color = breached ? "#B23A2E" : watch ? "#C08A2E" : "#1E7F6E";
  const width = Math.min(100, (psi / 0.4) * 100);
  return (
    <div className="flex items-center gap-3">
      <div className="w-44 text-xs text-ink/70">{feature.replace(/_/g, " ")}</div>
      <div className="flex-1 h-4 bg-paper rounded-sm relative overflow-hidden">
        <div className="absolute top-0 bottom-0 w-px bg-ink/20" style={{ left: "50%" }} />
        <div className="h-full rounded-sm" style={{ width: `${width}%`, backgroundColor: color, opacity: 0.75 }} />
      </div>
      <div className="w-16 text-right font-mono text-xs" style={{ color }}>{psi.toFixed(4)}</div>
    </div>
  );
}

function ModelsTab() {
  const { token, user } = useAuth();
  const { data: versions, error } = useLoad(api.modelVersions);
  const [activating, setActivating] = useState(null);
  const [localVersions, setLocalVersions] = useState(null);

  const list = localVersions || versions;

  async function handleActivate(id) {
    const approvedBy = user.email;
    setActivating(id);
    try {
      await api.activateModel(token, id, approvedBy);
      const refreshed = await api.modelVersions(token);
      setLocalVersions(refreshed);
    } catch (e) {
      alert(e.detail || "Activation failed");
    } finally {
      setActivating(null);
    }
  }

  if (error) return <ErrorBox err={error} />;
  if (!list) return <Loading />;

  return (
    <div className="space-y-4">
      {list.map((v) => (
        <Card key={v.id}>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="font-mono text-sm font-semibold">{v.name}</h3>
                {v.is_active && (
                  <span className="text-[10px] font-mono uppercase tracking-wide bg-risk-lowBg text-risk-low px-2 py-0.5 rounded">
                    Active
                  </span>
                )}
              </div>
              <p className="text-xs text-ink/40">
                {v.algorithm} · trained {new Date(v.trained_at).toLocaleDateString()}
              </p>
            </div>
            {!v.is_active && (
              <button
                onClick={() => handleActivate(v.id)}
                disabled={activating === v.id}
                className="text-xs font-medium px-3 py-1.5 rounded border border-primary text-primary hover:bg-primary-light transition-colors disabled:opacity-50"
              >
                {activating === v.id ? "Activating…" : "Activate"}
              </button>
            )}
          </div>

          <div className="grid grid-cols-3 gap-4 mt-4 font-mono text-sm">
            <Metric label="ROC-AUC" value={v.metrics.roc_auc} />
            <Metric label="F1" value={v.metrics.f1} />
            <Metric label="ECE (calibration err.)" value={v.metrics.ece} />
          </div>

          {v.approved_by && (
            <p className="text-[11px] text-ink/40 mt-4 ledger-rule pt-3">
              Approved by <span className="font-mono">{v.approved_by}</span>
              {v.approved_at && ` on ${new Date(v.approved_at).toLocaleString()}`}
            </p>
          )}
        </Card>
      ))}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div>
      <div className="text-ink/40 text-[10px] uppercase tracking-wide mb-1">{label}</div>
      <div className="text-base font-semibold">{value}</div>
    </div>
  );
}

function AuditTab() {
  const { token } = useAuth();
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.auditLogs(token, { limit: 100 }).then(setLogs).catch(setError);
  }, [token]);

  if (error) return <ErrorBox err={error} />;
  if (!logs) return <Loading />;

  return (
    <Card>
      <div className="overflow-x-auto -mx-6 px-6">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink/40 uppercase tracking-wide">
              <th className="pb-2 font-medium">Time</th>
              <th className="pb-2 font-medium">Actor role</th>
              <th className="pb-2 font-medium">Action</th>
              <th className="pb-2 font-medium">Resource</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {logs.map((log) => (
              <tr key={log.id} className="border-t border-line">
                <td className="py-2 text-ink/60 whitespace-nowrap">
                  {new Date(log.created_at).toLocaleString()}
                </td>
                <td className="py-2">{log.actor_role || "—"}</td>
                <td className="py-2 text-primary-dark">{log.action}</td>
                <td className="py-2 text-ink/60">
                  {log.resource_type}{log.resource_id ? `:${log.resource_id.slice(0, 8)}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function FlagBadge({ flagged, passText, failText }) {
  const color = flagged ? "#B23A2E" : "#1E7F6E";
  return (
    <span
      className="font-mono text-[11px] font-semibold px-2.5 py-1 rounded uppercase tracking-wide"
      style={{ color, backgroundColor: `${color}1A` }}
    >
      {flagged ? failText : passText}
    </span>
  );
}

function Loading() {
  return <div className="text-center py-12 text-ink/40 font-mono text-sm">Loading…</div>;
}
function ErrorBox({ err }) {
  return (
    <div className="bg-risk-highBg text-risk-high px-4 py-3 rounded text-sm">
      {err.detail ? String(err.detail) : "Failed to load."}
    </div>
  );
}
function EmptyBox({ text }) {
  return <div className="text-center py-12 text-ink/40 text-sm">{text}</div>;
}
