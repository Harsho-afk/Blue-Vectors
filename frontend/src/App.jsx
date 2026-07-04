import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./contexts/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./components/Login";
import Register from "./components/Register";
import CaseDashboard from "./components/CaseDashboard";
import NewCase from "./components/NewCase";
import CaseDetail from "./components/CaseDetail";
import "./styles/aria.css";

function Navigation() {
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <nav className="aria-nav">
      <div className="aria-nav__brand">ARIA</div>
      <div className="aria-nav__user">
        <span className="aria-nav__email">{user.email}</span>
        <button className="aria-nav__logout" onClick={logout}>
          LOGOUT
        </button>
      </div>
    </nav>
  );
}

export default function App() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="aria-loading-page">
        <p>Initializing ARIA...</p>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Navigation />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <CaseDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/new"
          element={
            <ProtectedRoute>
              <NewCase />
            </ProtectedRoute>
          }
        />
        <Route
          path="/cases/:id"
          element={
            <ProtectedRoute>
              <CaseDetail />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to={user ? "/" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
