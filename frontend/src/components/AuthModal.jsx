import { useState } from "react";
import { api, setToken } from "../api";

export default function AuthModal({ open, onClose, onAuthed, reason }) {
  const [mode, setMode] = useState("register"); // anonymous limit -> register first
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const fn = mode === "login" ? api.login : api.register;
      const data = await fn(username.trim(), password);
      setToken(data.token);
      onAuthed(data);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>

        <div className="modal-tabs">
          <button
            className={mode === "register" ? "tab active" : "tab"}
            onClick={() => setMode("register")}
          >
            REGISTER
          </button>
          <button
            className={mode === "login" ? "tab active" : "tab"}
            onClick={() => setMode("login")}
          >
            LOGIN
          </button>
        </div>

        {reason && <p className="modal-reason">{reason}</p>}

        <form onSubmit={submit} className="modal-form">
          <input
            type="text"
            placeholder="username"
            value={username}
            autoComplete="username"
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="password"
            value={password}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p className="modal-error">{error}</p>}
          <button type="submit" className="modal-submit" disabled={busy}>
            {busy ? "…" : mode === "login" ? "LOG IN" : "CREATE ACCOUNT"}
          </button>
        </form>

        <p className="modal-hint">
          {mode === "register"
            ? "Free accounts get 2 downloads per day."
            : "Welcome back!"}
        </p>
      </div>
    </div>
  );
}
