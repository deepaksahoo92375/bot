import { useEffect, useState, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip } from "recharts";
import { api, getToken, clearToken } from "./api.js";
import Login from "./Login.jsx";
import GroupsPage from "./GroupsPage.jsx";
import BroadcastPage from "./BroadcastPage.jsx";
import LiveLogsPage from "./LiveLogsPage.jsx";

const NAV = [
  { id: "overview", label: "Overview" },
  { id: "chats", label: "Active Voice Chats" },
  { id: "groups", label: "Connected Groups" },
  { id: "assistants", label: "Assistants" },
  { id: "tracks", label: "Top Tracks" },
  { id: "logs", label: "Live Logs" },
  { id: "broadcast", label: "Broadcast" },
];

function Waveform() {
  return (
    <div className="waveform" aria-hidden="true">
      <span className="bar" />
      <span className="bar" />
      <span className="bar" />
      <span className="bar" />
      <span className="bar" />
    </div>
  );
}

function StatCard({ label, value, signal }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value${signal ? " signal" : ""}`}>{value}</div>
    </div>
  );
}

function OverviewPage() {
  const [data, setData] = useState(null);
  const [trend, setTrend] = useState([]);

  const load = useCallback(async () => {
    const [overview, dau] = await Promise.all([api.overview(), api.dailyActiveUsers()]);
    setData(overview);
    setTrend(dau.map((d) => ({ date: d._id, users: d.active_users })));
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [load]);

  if (!data) return <div className="empty-state">Loading telemetry…</div>;

  return (
    <>
      <div className="stat-grid">
        <StatCard label="Active Voice Chats" value={data.active_voice_chats} signal />
        <StatCard label="Songs Played (24h)" value={data.songs_played_24h} />
        <StatCard label="Total Groups" value={data.total_groups} />
        <StatCard label="Total Users" value={data.total_users} />
      </div>

      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Daily Active Users — 7 day</span>
        </div>
        <div className="panel-body" style={{ height: 220 }}>
          {trend.length === 0 ? (
            <div className="empty-state">No activity data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend}>
                <XAxis dataKey="date" stroke="#7C8893" fontSize={11} />
                <YAxis stroke="#7C8893" fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#1C2127", border: "1px solid #262C33", fontSize: 12 }}
                />
                <Line type="monotone" dataKey="users" stroke="#4DFFB4" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </>
  );
}

function ActiveChatsPage() {
  const [chats, setChats] = useState({});

  const load = useCallback(async () => {
    setChats(await api.activeChats());
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  const entries = Object.entries(chats);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Live Voice Chats</span>
        {entries.length > 0 && <Waveform />}
      </div>
      {entries.length === 0 ? (
        <div className="empty-state">No active voice chats right now.</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Chat ID</th>
              <th>Assistant</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([chatId, info]) => (
              <tr key={chatId}>
                <td>{chatId}</td>
                <td>{info.assistant}</td>
                <td>
                  <span className="status-dot online" />
                  streaming
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AssistantsPage() {
  const [assistants, setAssistants] = useState([]);

  const load = useCallback(async () => {
    setAssistants(await api.assistants());
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Assistant Pool</span>
      </div>
      {assistants.length === 0 ? (
        <div className="empty-state">No assistant health data yet.</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Label</th>
              <th>Status</th>
              <th>Active Calls</th>
              <th>Errors</th>
              <th>Last Heartbeat</th>
            </tr>
          </thead>
          <tbody>
            {assistants.map((a) => (
              <tr key={a.session_label}>
                <td>{a.session_label}</td>
                <td>
                  <span className={`status-dot ${a.is_online ? "online" : "offline"}`} />
                  {a.is_online ? "online" : "offline"}
                </td>
                <td>{a.active_calls}</td>
                <td>{a.error_count}</td>
                <td>{new Date(a.last_heartbeat).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function TopTracksPage() {
  const [tracks, setTracks] = useState([]);

  useEffect(() => {
    api.topTracks().then(setTracks);
  }, []);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Most Played Tracks</span>
      </div>
      {tracks.length === 0 ? (
        <div className="empty-state">No play history yet.</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Title</th>
              <th>Plays</th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((t, i) => (
              <tr key={t._id}>
                <td>{i + 1}</td>
                <td className="mono" style={{ fontFamily: "Space Grotesk" }}>
                  {t._id}
                </td>
                <td>{t.play_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const PAGES = {
  overview: OverviewPage,
  chats: ActiveChatsPage,
  groups: GroupsPage,
  assistants: AssistantsPage,
  tracks: TopTracksPage,
  logs: LiveLogsPage,
  broadcast: BroadcastPage,
};

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [page, setPage] = useState("overview");

  if (!authed) {
    return <Login onSuccess={() => setAuthed(true)} />;
  }

  const PageComponent = PAGES[page];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" />
          <div>
            <div className="brand-name">CONTROL ROOM</div>
            <div className="brand-sub">vc-music-bot</div>
          </div>
        </div>
        {NAV.map((item) => (
          <button
            key={item.id}
            className={`nav-item${page === item.id ? " active" : ""}`}
            onClick={() => setPage(item.id)}
          >
            {item.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          className="nav-item"
          onClick={() => {
            clearToken();
            setAuthed(false);
          }}
        >
          Sign out
        </button>
      </aside>
      <main className="main">
        <div className="page-header">
          <span className="page-title">{NAV.find((n) => n.id === page)?.label}</span>
          <span className="page-meta mono">live · auto-refreshing</span>
        </div>
        <PageComponent />
      </main>
    </div>
  );
}
