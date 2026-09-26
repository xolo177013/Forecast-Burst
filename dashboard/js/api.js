/* ============================================================
   API CLIENT
   ============================================================ */

const API_BASE =
  (location.port === "8000" || location.protocol === "file:")
    ? "http://localhost:8000"
    : "";

async function apiGet(path, params = {}) {
  const url = new URL(API_BASE + path, location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  });
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}