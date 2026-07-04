import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { API } from "../lib/api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const res = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Login failed");
      }

      const user = await res.json();
      login(user);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="aria-auth-page">
      <div className="aria-auth-card">
        <h1 className="aria-auth-title">ARIA LOGIN</h1>
        <form onSubmit={handleSubmit} className="aria-auth-form">
          {error && <div className="aria-auth-error">{error}</div>}

          <div className="aria-form-group">
            <label className="aria-form-label">Email</label>
            <input
              type="email"
              className="aria-form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>

          <div className="aria-form-group">
            <label className="aria-form-label">Password</label>
            <input
              type="password"
              className="aria-form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
            />
          </div>

          <button
            type="submit"
            className="aria-auth-button"
            disabled={isLoading || !email || !password}
          >
            {isLoading ? "LOGGING IN..." : "LOGIN ▶"}
          </button>
        </form>

        <p className="aria-auth-footer">
          No account? <Link to="/register" className="aria-auth-link">Register here</Link>
        </p>
      </div>
    </div>
  );
}
