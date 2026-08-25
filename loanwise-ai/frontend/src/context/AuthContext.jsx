import { createContext, useContext, useState, useCallback } from "react";
import { api } from "../api/client";

// Tokens are kept in memory only (React state), not localStorage/sessionStorage —
// deliberately, to limit XSS token-theft exposure in this reference SPA. This
// means a hard page refresh logs the user out; a production deployment would
// pair a short-lived access token with an httpOnly, Secure, SameSite=strict
// refresh cookie set by the backend, so JS never touches the refresh token at all.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    setError(null);
    try {
      const tokens = await api.login(email, password);
      const me = await api.me(tokens.access_token);
      setToken(tokens.access_token);
      setUser(me);
      return me;
    } catch (e) {
      setError(e.detail || "Login failed");
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, login, logout, loading, error }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
