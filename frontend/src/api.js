let token = null;
try { token = localStorage.getItem("ori_token"); } catch {}
export const setToken = (t) => {
  token = t;
  try { t ? localStorage.setItem("ori_token", t) : localStorage.removeItem("ori_token"); } catch {}
};
export const hasToken = () => !!token;

async function call(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = "Bearer " + token;
  const res = await fetch("/api" + path, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try { const j = await res.json(); detail = j.detail ?? detail; } catch {}
    const err = new Error(typeof detail === "string" ? detail : detail.message || "Request failed");
    err.status = res.status; err.detail = detail;
    throw err;
  }
  return res;
}
const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  register: (b) => call("/auth/register", json(b)).then((r) => r.json()),
  login: (b) => call("/auth/login", json(b)).then((r) => r.json()),
  me: () => call("/me").then((r) => r.json()),
  forms: () => call("/forms").then((r) => r.json()),
  extract: (fd) => call("/extract", { method: "POST", body: fd }).then((r) => r.json()),
  extractStream: async (fd, onProgress) => {
    const res = await call("/extract-stream", { method: "POST", body: fd });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "", finalResult = null;
    while (true) {
      const { value, done } = await reader.read();
      if (value) buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.error) throw new Error(ev.error);
        if (onProgress && ev.msg) onProgress({ pct: ev.pct || 0, msg: ev.msg });
        if (ev.result) finalResult = ev.result;
      }
      if (done) break;
    }
    if (buf.trim()) {
      const ev = JSON.parse(buf);
      if (ev.error) throw new Error(ev.error);
      if (ev.result) finalResult = ev.result;
    }
    if (!finalResult) throw new Error("Extraction ended without a result");
    return finalResult;
  },
  missing: (b) => call("/missing", json(b)).then((r) => r.json()),
  create: (b) => call("/applications", json(b)).then((r) => r.json()),
  history: () => call("/applications").then((r) => r.json()),
  one: (id) => call("/applications/" + id).then((r) => r.json()),
  adminApps: (q, form) => call(`/admin/applications?q=${encodeURIComponent(q || "")}&form_code=${form || ""}`).then((r) => r.json()),
  adminUsers: () => call("/admin/users").then((r) => r.json()),
  adminReset: (id, new_password) => call(`/admin/users/${id}/reset-password`, json({ new_password })).then((r) => r.json()),
  remove: (id) => call("/applications/" + id, { method: "DELETE" }).then((r) => r.json()),
  download: async (id, fallback, admin = false) => {
    const r = await call(`/${admin ? "admin/" : ""}applications/${id}/download`);
    const cd = r.headers.get("Content-Disposition") || "";
    const name = (cd.match(/filename="?([^";]+)"?/) || [])[1] || fallback;
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  },
};
