import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const DEMO_ACCOUNTS = [
  { role: "Applicant", email: "applicant@loanwise.demo", password: "ApplicantPass123!" },
  { role: "Loan Officer", email: "officer@loanwise.demo", password: "OfficerPass123!" },
  { role: "Compliance", email: "compliance@loanwise.demo", password: "CompliancePass123!" },
  { role: "Admin", email: "admin@loanwise.demo", password: "AdminPass123!" },
];

export default function Login() {
  const { login, loading, error } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    try {
      await login(email, password);
      navigate("/apply");
    } catch {
      // error surfaced via context
    }
  }

  function fillDemo(account) {
    setEmail(account.email);
    setPassword(account.password);
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6 bg-paper">
      <div className="w-full max-w-md">
        <div className="flex items-end gap-[3px] h-8 mb-6 justify-center">
          <span className="w-1.5 bg-risk-low rounded-sm" style={{ height: "40%" }} />
          <span className="w-1.5 bg-risk-medium rounded-sm" style={{ height: "70%" }} />
          <span className="w-1.5 bg-risk-high rounded-sm" style={{ height: "100%" }} />
        </div>
        <h1 className="font-display font-semibold text-2xl text-center mb-1">LoanWise AI</h1>
        <p className="text-center text-sm text-ink/50 mb-8">Explainable credit risk decision support</p>

        <form onSubmit={handleSubmit} className="bg-surface border border-line rounded-lg p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-ink/60 mb-1.5">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-line rounded font-mono text-sm focus:border-primary outline-none"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-ink/60 mb-1.5">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-line rounded font-mono text-sm focus:border-primary outline-none"
              placeholder="••••••••••"
            />
          </div>
          {error && (
            <div className="text-sm text-risk-high bg-risk-highBg px-3 py-2 rounded">
              {typeof error === "string" ? error : "Invalid email or password."}
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-ink text-white py-2.5 rounded font-medium text-sm hover:bg-primary-dark transition-colors disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-6 bg-surface/60 border border-line rounded-lg p-4">
          <p className="text-xs font-mono text-ink/40 uppercase tracking-wide mb-2">Demo accounts</p>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.email}
                onClick={() => fillDemo(acc)}
                type="button"
                className="text-left text-xs px-2.5 py-2 rounded border border-line hover:border-primary hover:bg-primary-light transition-colors"
              >
                <div className="font-medium">{acc.role}</div>
                <div className="text-ink/40 font-mono truncate">{acc.email}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
