import { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";

export default function GroupsPage() {
  const [groups, setGroups] = useState([]);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);

  const load = useCallback(async () => {
    setGroups(await api.groups());
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, [load]);

  async function openGroup(group) {
    setSelected(group);
    setHistory(await api.groupHistory(group.chat_id));
  }

  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Connected Groups ({groups.length})</span>
        </div>
        {groups.length === 0 ? (
          <div className="empty-state">No groups have used the bot yet.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Chat ID</th>
                <th>Status</th>
                <th>Joined</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.chat_id}>
                  <td style={{ fontFamily: "Space Grotesk" }}>{g.title || "(untitled)"}</td>
                  <td>{g.chat_id}</td>
                  <td>
                    <span className={`status-dot ${g.currently_playing ? "online" : "offline"}`} />
                    {g.currently_playing ? `playing via ${g.assistant}` : "idle"}
                  </td>
                  <td>{g.created_at ? new Date(g.created_at).toLocaleDateString() : "—"}</td>
                  <td>
                    <button
                      className="nav-item"
                      style={{ padding: "4px 10px", width: "auto" }}
                      onClick={() => openGroup(g)}
                    >
                      History
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Play History — {selected.title || selected.chat_id}</span>
            <button
              className="nav-item"
              style={{ padding: "4px 10px", width: "auto" }}
              onClick={() => setSelected(null)}
            >
              Close
            </button>
          </div>
          {history.length === 0 ? (
            <div className="empty-state">No play history for this group yet.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Artist</th>
                  <th>Played At</th>
                  <th>Requested By</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={i}>
                    <td style={{ fontFamily: "Space Grotesk" }}>{h.title}</td>
                    <td>{h.artist || "—"}</td>
                    <td>{new Date(h.played_at).toLocaleString()}</td>
                    <td>{h.requested_by || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  );
}
