import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { API } from "../lib/api";

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setIsLoading(true);

    try {
      const res = await fetch(`${API}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email,
          password,
          full_name: fullName || null,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Registration failed");
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
        <h1 className="aria-auth-title">ARIA REGISTER</h1>
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
            <label className="aria-form-label">Full Name (optional)</label>
            <input
              type="text"
              className="aria-form-input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
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
              placeholder="Min. 8 characters"
              required
              disabled={isLoading}
            />
          </div>

          <button
            type="submit"
            className="aria-auth-button"
            disabled={isLoading || !email || !password}
          >
            {isLoading ? "REGISTERING..." : "REGISTER ▶"}
          </button>
        </form>

        <p className="aria-auth-footer">
          Already have an account? <Link to="/login" className="aria-auth-link">Login here</Link>
        </p>
      </div>
    </div>
  );
}
