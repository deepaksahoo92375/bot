import { useEffect, useRef, useState } from "react";
import { api, getToken } from "./api.js";

const LEVEL_COLOR = {
  ERROR: "var(--error)",
  WARNING: "var(--warn)",
  INFO: "var(--ink)",
  DEBUG: "var(--ink-dim)",
};

export default function LiveLogsPage() {
  const [logs, setLogs] = useState([]);
  const [connected, setConnected] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const wsRef = useRef(null);
  const logEndRef = useRef(null);

  useEffect(() => {
    api.recentLogs().then(setLogs);

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/logs?token=${getToken()}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const entry = JSON.parse(event.data);
      setLogs((prev) => [...prev.slice(-499), entry]);
    };

    return () => ws.close();
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const filtered = filter === "ALL" ? logs : logs.filter((l) => l.level === filter);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">
          Live Logs <span className={`status-dot ${connected ? "online" : "offline"}`} style={{ marginLeft: 10 }} />
          {connected ? "streaming" : "disconnected"}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          {["ALL", "INFO", "WARNING", "ERROR"].map((lvl) => (
            <button
              key={lvl}
              className={`nav-item${filter === lvl ? " active" : ""}`}
              style={{ width: "auto", padding: "4px 12px", fontSize: 11 }}
              onClick={() => setFilter(lvl)}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>
      <div
        className="panel-body mono"
        style={{
          maxHeight: 520,
          overflowY: "auto",
          fontSize: 12,
          lineHeight: 1.7,
          background: "#0a0c0e",
        }}
      >
        {filtered.length === 0 ? (
          <div className="empty-state">No log entries yet.</div>
        ) : (
          filtered.map((l, i) => (
            <div key={i} style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              <span style={{ color: "var(--ink-dim)" }}>{new Date(l.time).toLocaleTimeString()}</span>{" "}
              <span style={{ color: LEVEL_COLOR[l.level] || "var(--ink)", fontWeight: 600 }}>
                {l.level.padEnd(7)}
              </span>{" "}
              <span style={{ color: "var(--ink-dim)" }}>{l.module}</span> — {l.message}
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}
