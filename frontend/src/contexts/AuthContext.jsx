/**
 * AuthContext — global authentication state.
 *
 * On mount it calls GET /api/auth/me (with the HttpOnly cookie) to restore an
 * existing session.  All child components read `useAuth()` to get:
 *   - user        : { id, email, full_name, role } | null
 *   - isLoading   : true while the initial /me check is in flight
 *   - login(data) : store user returned by the server after login/register
 *   - logout()    : call POST /api/auth/logout then clear state
 */
import { createContext, useContext, useEffect, useState } from "react";
import { API } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user,      setUser]      = useState(null);
  const [isLoading, setIsLoading] = useState(true);   // true until /me resolves

  // Restore session on app load
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then(r => (r.ok ? r.json() : null))
      .then(data => setUser(data ?? null))
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  function login(userData) {
    setUser(userData);
  }

  async function logout() {
    await fetch(`${API}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
    }).catch(() => {});
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
