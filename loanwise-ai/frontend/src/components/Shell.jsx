import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const ROLE_LABELS = {
  applicant: "Applicant",
  officer: "Loan Officer",
  compliance: "Compliance",
  admin: "Administrator",
};

export default function Shell({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line bg-surface">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="flex items-end gap-[2px] h-5">
              <span className="w-[3px] bg-risk-low rounded-sm" style={{ height: "40%" }} />
              <span className="w-[3px] bg-risk-medium rounded-sm" style={{ height: "70%" }} />
              <span className="w-[3px] bg-risk-high rounded-sm" style={{ height: "100%" }} />
            </div>
            <span className="font-display font-semibold text-lg tracking-tight">LoanWise</span>
            <span className="font-mono text-[10px] text-ink/40 tracking-widest uppercase pt-0.5">AI</span>
          </Link>

          {user && (
            <div className="flex items-center gap-4">
              <nav className="flex items-center gap-1 font-body text-sm">
                <NavLink to="/apply" label="New Application" />
                {(user.role === "compliance" || user.role === "admin") && (
                  <NavLink to="/admin" label="Governance" />
                )}
              </nav>
              <div className="w-px h-5 bg-line" />
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs px-2 py-1 rounded bg-primary-light text-primary-dark">
                  {ROLE_LABELS[user.role] || user.role}
                </span>
                <span className="text-sm text-ink/70">{user.email}</span>
              </div>
              <button
                onClick={() => { logout(); navigate("/login"); }}
                className="text-sm text-ink/50 hover:text-ink transition-colors"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-line py-4">
        <div className="max-w-6xl mx-auto px-6 flex items-center justify-between text-xs text-ink/40 font-mono">
          <span>LoanWise AI — decision support, not automated approval.</span>
          <span>Reference implementation v1.0.0</span>
        </div>
      </footer>
    </div>
  );
}

function NavLink({ to, label }) {
  return (
    <Link to={to} className="px-3 py-1.5 rounded hover:bg-paper transition-colors text-ink/70 hover:text-ink">
      {label}
    </Link>
  );
}
