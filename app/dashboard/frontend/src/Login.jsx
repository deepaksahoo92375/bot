import { useState } from "react";
import { api, setToken } from "./api.js";

export default function Login({ onSuccess }) {
  const [userId, setUserId] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { access_token } = await api.verifyCode(Number(userId), code);
      setToken(access_token);
      onSuccess();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="brand" style={{ marginBottom: 22 }}>
          <span className="brand-mark" />
          <div>
            <div className="brand-name">CONTROL ROOM</div>
            <div className="brand-sub">vc-music-bot</div>
          </div>
        </div>
        <p className="login-help">
          Send <code className="mono">/dashboardlogin</code> to the bot in a DM to get a one-time
          code, then enter your Telegram user ID and the code below.
        </p>
        <form onSubmit={handleSubmit}>
          <input
            type="number"
            placeholder="Telegram user ID"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            required
          />
          <input
            type="text"
            placeholder="6-digit code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={6}
            required
          />
          {error && (
            <p style={{ color: "var(--error)", fontSize: 12, marginBottom: 10 }}>{error}</p>
          )}
          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? "Verifying…" : "Enter control room"}
          </button>
        </form>
      </div>
    </div>
  );
}
