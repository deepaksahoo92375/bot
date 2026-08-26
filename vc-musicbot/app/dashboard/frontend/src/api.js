const TOKEN_KEY = "vc_dashboard_token";

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const token = getToken();
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  verifyCode: (user_id, code) =>
    request("/auth/verify", { method: "POST", body: JSON.stringify({ user_id, code }) }),
  overview: () => request("/analytics/overview"),
  activeChats: () => request("/analytics/active-chats"),
  topTracks: () => request("/analytics/top-tracks"),
  dailyActiveUsers: () => request("/analytics/daily-active-users"),
  assistants: () => request("/assistants/"),
  groups: () => request("/groups/"),
  groupHistory: (chatId) => request(`/groups/${chatId}/history`),
  recentLogs: (level) => request(`/logs/recent${level ? `?level=${level}` : ""}`),
  sendBroadcast: (target, text) =>
    request("/broadcast/", { method: "POST", body: JSON.stringify({ target, text }) }),
  broadcastStatus: (jobId) => request(`/broadcast/${jobId}`),
};
