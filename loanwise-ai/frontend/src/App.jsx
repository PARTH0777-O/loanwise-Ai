import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Shell from "./components/Shell";
import Login from "./pages/Login";
import ApplyForm from "./pages/ApplyForm";
import Result from "./pages/Result";
import WhatIf from "./pages/WhatIf";
import AdminDashboard from "./pages/AdminDashboard";

function Protected({ children, roles }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="max-w-md mx-auto px-6 py-16 text-center">
        <p className="text-risk-high text-sm">
          Your role ({user.role}) doesn't have access to this page.
        </p>
      </div>
    );
  }
  return <Shell>{children}</Shell>;
}

function AppRoutes() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to={user ? "/apply" : "/login"} replace />} />
      <Route path="/apply" element={<Protected><ApplyForm /></Protected>} />
      <Route path="/result/:applicationId" element={<Protected><Result /></Protected>} />
      <Route path="/whatif/:applicationId" element={<Protected><WhatIf /></Protected>} />
      <Route
        path="/admin"
        element={
          <Protected roles={["compliance", "admin"]}>
            <AdminDashboard />
          </Protected>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
