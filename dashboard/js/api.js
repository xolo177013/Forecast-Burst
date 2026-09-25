const API_BASE =
  (location.port === "8000" || location.protocol === "file:")
    ? "http://localhost:8000"
    : "";

async function apiGet(path, params = {}) {

  const url = new URL(
    API_BASE + path,
    location.origin
  );

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, value);
    }
  });

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`${path} -> ${response.status}`);
  }

  return response.json();
}