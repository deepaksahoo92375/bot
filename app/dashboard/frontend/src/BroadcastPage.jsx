import { useState } from "react";
import { api } from "./api.js";

export default function BroadcastPage() {
  const [target, setTarget] = useState("groups");
  const [text, setText] = useState("");
  const [status, setStatus] = useState(null);
  const [sending, setSending] = useState(false);

  async function handleSend() {
    if (!text.trim()) return;
    setSending(true);
    setStatus(null);
    try {
      const job = await api.sendBroadcast(target, text);
      setStatus({ state: "queued", jobId: job.job_id });
      pollJob(job.job_id);
    } catch (err) {
      setStatus({ state: "error", message: err.message });
      setSending(false);
    }
  }

  function pollJob(jobId) {
    const interval = setInterval(async () => {
      const job = await api.broadcastStatus(jobId);
      if (job && job.status === "completed") {
        clearInterval(interval);
        setStatus({ state: "completed", sent: job.sent, failed: job.failed, total: job.total });
        setSending(false);
      }
    }, 2000);
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Broadcast Message</span>
      </div>
      <div className="panel-body">
        <p style={{ fontSize: 12, color: "var(--ink-dim)", marginBottom: 16 }}>
          Sends a message via the bot. Picked up and delivered by the running bot process
          (requires the bot to be online).
        </p>

        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          {["groups", "users", "all"].map((t) => (
            <button
              key={t}
              className={`nav-item${target === t ? " active" : ""}`}
              style={{ width: "auto", padding: "8px 16px" }}
              onClick={() => setTarget(t)}
            >
              {t}
            </button>
          ))}
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Message to broadcast..."
          rows={5}
          style={{
            width: "100%",
            background: "var(--bg-void)",
            border: "1px solid var(--line)",
            borderRadius: 6,
            padding: 12,
            color: "var(--ink)",
            fontFamily: "Space Grotesk",
            fontSize: 14,
            resize: "vertical",
            marginBottom: 14,
          }}
        />

        <button className="btn-primary" style={{ width: "auto", padding: "10px 24px" }} onClick={handleSend} disabled={sending}>
          {sending ? "Sending…" : `Broadcast to ${target}`}
        </button>

        {status && (
          <div style={{ marginTop: 16, fontSize: 13, fontFamily: "JetBrains Mono, monospace" }}>
            {status.state === "queued" && <span style={{ color: "var(--warn)" }}>Queued, waiting for bot to pick it up…</span>}
            {status.state === "error" && <span style={{ color: "var(--error)" }}>Error: {status.message}</span>}
            {status.state === "completed" && (
              <span style={{ color: "var(--signal)" }}>
                Done — sent {status.sent}/{status.total} ({status.failed} failed)
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
