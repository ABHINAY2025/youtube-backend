// Thin API client.
// - Monolith (Flask serves this build): leave VITE_API_BASE unset -> "/api".
// - Standalone frontend (e.g. Vercel) pointing at the HF backend: set
//   VITE_API_BASE=https://marripelli-youtube-backend.hf.space at build time.
const API_BASE = import.meta.env.VITE_API_BASE || "";
const BASE = `${API_BASE}/api`;

// A stable per-browser device id powers the anonymous 2-download limit.
export function getDeviceId() {
  let id = localStorage.getItem("devx_device_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("devx_device_id", id);
  }
  return id;
}

export function getToken() {
  return localStorage.getItem("devx_token") || "";
}
export function setToken(t) {
  if (t) localStorage.setItem("devx_token", t);
  else localStorage.removeItem("devx_token");
}

function headers(json = true) {
  const h = { "X-Device-Id": getDeviceId() };
  if (json) h["Content-Type"] = "application/json";
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || "Request failed.");
    err.status = res.status;
    err.code = data.code;
    throw err;
  }
  return data;
}

export const api = {
  me: () => fetch(`${BASE}/me`, { headers: headers(false) }).then(handle),

  status: () => fetch(`${BASE}/status`, { headers: headers(false) }).then(handle),

  register: (username, password) =>
    fetch(`${BASE}/auth/register`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ username, password }),
    }).then(handle),

  login: (username, password) =>
    fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ username, password }),
    }).then(handle),

  info: (url) =>
    fetch(`${BASE}/info`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ url }),
    }).then(handle),

  download: (url, format_id, mode) =>
    fetch(`${BASE}/download`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ url, format_id, mode }),
    }).then(handle),

  progress: (jobId) =>
    fetch(`${BASE}/progress/${jobId}`, { headers: headers(false) }).then(handle),

  fileUrl: (jobId) => `${BASE}/file/${jobId}`,
};
