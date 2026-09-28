/* Load AFTER app.js. Adds: date-driven dashboard + live verification + manual input. */
let availableDates = [];

// Every date-aware endpoint automatically gets the selected date
(function(){ const orig = apiGet;
  apiGet = (p, params = {}) => {
    if (currentDate && ["/confidence-map","/bust-probability","/explain","/error-prone-regions"].includes(p) && !params.init_date)
      params = { ...params, init_date: currentDate };
    return orig(p, params);
  };
})();

async function refreshForDate() {
  confidenceCache = {};
  await selectLeadDay(currentLeadDay);
  loadNationalTrend(); loadErrorProneRegions();
  const s = document.getElementById("regionSelect"); if (s && s.value) loadRegionDetail(s.value);
  const v = document.getElementById("kpiValid"); if (v) v.textContent = currentDate;
}

async function initDates() {
  const inp = document.getElementById("dateInput"), note = document.getElementById("dateNote");
  try {
    const d = await apiGet("/forecast-dates"); availableDates = d.dates;
    inp.min = availableDates[0]; inp.max = availableDates[availableDates.length - 1];
    inp.value = currentDate = d.latest;
    note.textContent = `${availableDates.length} held-out dates available (${inp.min} → ${inp.max}). Everything below reflects this date.`;
    const li = document.getElementById("liveDateInput"); if (li) { li.value = d.latest; li.min = "2016-01-01"; li.max = "2022-12-31"; }
  } catch (e) { note.textContent = "Could not load dates."; return; }
  inp.onchange = () => {
    let v = inp.value;
    if (!availableDates.includes(v)) {   // snap to nearest date that has data
      const t = new Date(v).getTime();
      v = availableDates.reduce((b, x) => Math.abs(new Date(x) - t) < Math.abs(new Date(b) - t) ? x : b);
      inp.value = v; note.textContent = `No data for that day — showing nearest available: ${v}`;
    }
    currentDate = v; 
    refreshForDate();
  };
}

/* ---- Mode A: verify a date ---- */
document.getElementById("liveRunBtn").onclick = async () => {
  const date = document.getElementById("liveDateInput").value, tb = document.getElementById("liveTableBody"), note = document.getElementById("liveNote");
  if (!date) return;
  tb.innerHTML = `<tr><td colspan="5" style="padding:24px">Fetching real forecast + ensemble data and running the model… (30–90 s)</td></tr>`;
  try {
    const [d, info] = await Promise.all([apiGet("/live-verify", { init_date: date }), apiGet("/model-info")]);
    const thr = d.operating_threshold ?? 0.8, R = d.results;
    note.innerHTML = d.training_period_warning
      ? `<b style="color:#b45309">⚠ ${d.init_date} lies inside the training period — the model has seen this period, so this is not an unbiased test. Use dates on/after ${d.held_out_starts}.</b>`
      : d.held_out ? `<b style="color:#16a34a">✔ Held-out date — the model never saw this period. Outcomes below are real.</b>`
                   : `Outcome labels not available for this date (no verified truth yet), so only predictions are shown.`;
    tb.innerHTML = "";
    for (let ld = 1; ld <= 10; ld++) {
      const r = R.filter(x => x.lead_day === ld); if (!r.length) continue;
      const mp = r.reduce((s, x) => s + x.predicted_bust_probability, 0) / r.length;
      const flagged = r.filter(x => x.predicted_bust_probability >= thr), ver = r.filter(x => x.actual_available);
      const ab = ver.length ? ver.reduce((s, x) => s + x.actual_bust, 0) / ver.length : null;
      const hit = flagged.filter(x => x.actual_available);
      const prec = hit.length ? hit.reduce((s, x) => s + x.actual_bust, 0) / hit.length : null;
      tb.innerHTML += `<tr><td>Day ${ld}</td><td>${(mp*100).toFixed(1)}%</td><td>${flagged.length} / ${r.length}</td>
        <td>${ab === null ? "pending" : (ab*100).toFixed(1) + "%"}</td>
        <td>${prec === null ? "—" : (prec*100).toFixed(1) + "%"}</td></tr>`;
    }
  } catch (e) { tb.innerHTML = `<tr><td colspan="5" style="color:#dc2626;padding:20px">${e.message}</td></tr>`; }
};

/* ---- Mode B: manual input (friendly units -> model units) ---- */
const FIELDS = [
  ["init_date","Forecast date","date",""], ["precip_mm","Rain forecast (mm/24h)","number",5], ["mslp_hpa","Sea-level pressure (hPa)","number",1005],
  ["t2m_c","2 m temperature (°C)","number",30], ["u10","10 m wind U (m/s)","number",4], ["v10","10 m wind V (m/s)","number",1],
  ["shear","Wind shear 850–500 hPa (m/s)","number",12], ["ws500","Wind speed 500 hPa (m/s)","number",10],
  ["spread_mm","Ensemble rain spread (mm)","number",2], ["hist","Historical error index (optional)","number",""]];
const mf = document.getElementById("manualForm");
mf.innerHTML = FIELDS.map(([id, l, t, v]) => `<div><label style="display:block;font-size:10.5px;color:var(--text-3);margin-bottom:4px">${l}</label>
  <input id="m_${id}" type="${t}" step="any" value="${id==='init_date'?new Date().toISOString().slice(0,10):v}"
  style="width:100%;height:36px;padding:0 8px;border:1px solid var(--border-strong);border-radius:8px;font-family:var(--mono)"></div>`).join("");
document.getElementById("manualRunBtn").onclick = async () => {
  const g = id => document.getElementById("m_" + id).value, n = id => parseFloat(g(id));
  const f = { init_date: g("init_date"), forecast_precip: n("precip_mm")/1000, forecast_mslp: n("mslp_hpa")*100, forecast_t2m: n("t2m_c")+273.15,
    forecast_u10: n("u10"), forecast_v10: n("v10"), wind_shear_850_500hpa: n("shear"), wind_speed_500hpa: n("ws500"), ensemble_spread_precip: n("spread_mm")/1000 };
  if (g("hist") !== "") f.hist_error_climatology = n("hist");
  const tb = document.getElementById("manualBody"); tb.innerHTML = `<tr><td colspan="5" style="padding:16px">Running model…</td></tr>`;
  try {
    const res = await fetch(API_BASE + "/predict-manual", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ features: f }) });
    if (!res.ok) throw new Error((await res.json()).detail);
    const d = await res.json(); tb.innerHTML = "";
    d.days.forEach(r => tb.innerHTML += `<tr><td>Day ${r.lead_day}</td><td>${(r.bust_probability*100).toFixed(1)}%</td>
      <td>${(r.confidence*100).toFixed(1)}%</td><td>${r.expected_error.toFixed(2)}</td>
      <td><span class="risk-chip ${r.risk==='High'?'critical':r.risk==='Moderate'?'watch':'nominal'}">${r.risk}</span></td></tr>`);
  } catch (e) { tb.innerHTML = `<tr><td colspan="5" style="color:#dc2626;padding:16px">${e.message}</td></tr>`; }
};

initDates();