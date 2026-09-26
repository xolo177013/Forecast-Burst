/* ============================================================
   APP STATE + BOOT
   ============================================================ */

let currentLeadDay = 5;
let confidenceCache = {};
let allRegionIds = [];

/* ---------- TABS ------------------------------------------- */
function initTabs() {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.onclick = () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
      btn.classList.add("active");
      const target = document.getElementById("view-" + tab);
      if (target) target.classList.add("active");
      setTimeout(() => { if (map) map.invalidateSize(); }, 80);
    };
  });
}

/* ---------- connection chip -------------------------------- */
function setConn(ok, text) {
  const dot = document.getElementById("connDot");
  const label = document.getElementById("connText");
  if (dot) dot.classList.toggle("off", !ok);
  if (label) label.textContent = text;
}

/* ---------- clock ------------------------------------------ */
function startClock() {
  const el = document.getElementById("clock");
  if (!el) return;
  const tick = () => {
    const now = new Date();
    el.textContent = now.toLocaleTimeString("en-IN", { hour12: false }) + " IST";
  };
  tick();
  setInterval(tick, 1000);

  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = d.toLocaleString("en-GB", { month: "short" }).toUpperCase();
  const cyc = document.getElementById("kpiCycle");
  const val = document.getElementById("kpiValid");
  if (cyc) cyc.textContent = "00Z";
  if (val) val.textContent = `${dd} ${mm}`;
}

/* ---------- lead strip ------------------------------------- */
function buildLeadStrip() {
  const strip = document.getElementById("leadStrip");
  if (!strip) return;
  strip.innerHTML = "";
  for (let d = 1; d <= 10; d++) {
    const btn = document.createElement("button");
    btn.className = "leadbtn" + (d === currentLeadDay ? " active" : "");
    btn.textContent = "D" + String(d).padStart(2, "0");
    btn.id = "lead-" + d;
    btn.onclick = () => selectLeadDay(d);
    strip.appendChild(btn);
  }
}

async function selectLeadDay(day) {
  currentLeadDay = day;

  document.querySelectorAll(".leadbtn").forEach(b => b.classList.remove("active"));
  const active = document.getElementById("lead-" + day);
  if (active) active.classList.add("active");

  updateDayLabels(day);

  try {
    const data = await apiGet("/confidence-map", { lead_day: day });
    if (!data.regions || !data.regions.length) {
      console.warn("[app] no regions for day", day);
      return;
    }
    confidenceCache[day] = data.regions;
    renderMap(data.regions);
    updateConfidenceUI(data.regions);

    if (allRegionIds.length === 0) {
      allRegionIds = data.regions.map(r => r.region_id).sort();
      populateRegionSelect();
    }
  } catch (err) {
    console.error("[app] confidence-map failed:", err);
  }
}

function updateDayLabels(day) {
  const v = String(day).padStart(2, "0");
  const set = (id, t) => { const el = document.getElementById(id); if (el) el.textContent = t; };
  set("activeDayLabel", "Day " + v);
  set("kpiLead", v);
  set("sideDay", v);
  set("explainDay", v);
}

/* ---------- KPI update ------------------------------------- */
function updateConfidenceUI(regions) {
  if (!regions?.length) return;

  const avg = regions.reduce((s, r) => s + Number(r.forecast_confidence || 0), 0) / regions.length;
  const highRisk = regions.filter(r => Number(r.bust_probability || 0) > 0.5).length;
  const pct = Math.round(avg * 100);

  const set = (id, t) => { const e = document.getElementById(id); if (e) e.textContent = t; };
  set("kpiRegions", regions.length);
  set("kpiConf", pct + "%");
  set("kpiHigh", highRisk);
  set("sideConfidence", pct + "%");

  let tag = "HIGH CONFIDENCE", cls = "", alertMsg = "";
  if (avg >= 0.7) {
    alertMsg = `<strong>Nominal conditions.</strong> Forecast skill is strong across the domain for this lead.`;
  } else if (avg >= 0.45) {
    tag = "MONITOR"; cls = "medium";
    alertMsg = `<strong>Elevated uncertainty.</strong> ${highRisk} cells exceed the P(bust) > 0.5 threshold — monitor cyclogenesis and moisture flux.`;
  } else {
    tag = "HIGH RISK"; cls = "high";
    alertMsg = `<strong>Critical uncertainty.</strong> ${highRisk} cells show high bust probability. Cross-check with ensemble spread before operational use.`;
  }

  const badge = document.getElementById("confidenceBadge");
  if (badge) { badge.className = "national-badge" + (cls ? " " + cls : ""); badge.textContent = tag; }

  const kpiConfTag = document.getElementById("kpiConfTag");
  if (kpiConfTag) kpiConfTag.textContent = tag;

  const meter = document.getElementById("confidenceMeter");
  if (meter) {
    meter.style.width = pct + "%";
    if (avg >= 0.7)       meter.style.background = "linear-gradient(90deg, #16a34a, #0ea5b7)";
    else if (avg >= 0.45) meter.style.background = "linear-gradient(90deg, #f59e0b, #ea580c)";
    else                  meter.style.background = "linear-gradient(90deg, #dc2626, #b91c1c)";
  }

  const alertBody = document.getElementById("alertBody");
  if (alertBody) alertBody.innerHTML = alertMsg;
}

/* ---------- national trend --------------------------------- */
async function loadNationalTrend() {
  const points = [];
  for (let d = 1; d <= 10; d++) {
    try {
      const data = confidenceCache[d] || (await apiGet("/confidence-map", { lead_day: d })).regions;
      confidenceCache[d] = data;
      if (!data?.length) continue;
      const avg = data.reduce((s, r) => s + Number(r.forecast_confidence || 0), 0) / data.length;
      points.push({ x: d, y: avg });
    } catch (e) { console.warn("trend day failed:", d, e); }
  }
  renderTrendChart(points);
}

/* ---------- region select ---------------------------------- */
function populateRegionSelect() {
  const sel = document.getElementById("regionSelect");
  if (!sel) return;
  sel.innerHTML = "";
  allRegionIds.forEach(id => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  sel.onchange = () => loadRegionDetail(sel.value);
  if (allRegionIds.length) loadRegionDetail(allRegionIds[0]);
}

async function loadRegionDetail(regionId) {
  if (!regionId) return;
  try {
    const trend = await apiGet("/bust-probability", { region_id: regionId });
    renderRegionChart(trend.by_lead_day);
  } catch (e) { console.error("region probability failed:", e); }

  try {
    const exp = await apiGet("/explain", { region_id: regionId, lead_day: currentLeadDay });
    renderExplanation(exp);
  } catch (e) {
    const box = document.getElementById("reasonBox");
    if (box) box.innerHTML = `<div class="exp-empty">No explanation available for this region and lead day.</div>`;
  }
}

/* ---------- explanation panel ------------------------------ */
function renderExplanation(data) {
  const box = document.getElementById("reasonBox");
  if (!box) return;

  const conf = Number(data.forecast_confidence || 0);
  let cls = "lo";
  if (conf >= 0.70) cls = "hi";
  else if (conf >= 0.45) cls = "mid";

  let reasons = data.top_reasons;
  if (typeof reasons === "string") {
    reasons = reasons.split(";").map(s => s.trim()).filter(Boolean);
  } else if (!Array.isArray(reasons)) {
    reasons = [];
  }

  let html = `<span class="exp-badge ${cls}">${(conf * 100).toFixed(0)}% CONFIDENCE</span>`;
  reasons.forEach(r => {
    const i = String(r).indexOf("=");
    let k = String(r), v = "";
    if (i !== -1) { k = String(r).substring(0, i).trim(); v = String(r).substring(i + 1).trim(); }
    html += `
      <div class="exp-item">
        <span class="exp-feat">${k}</span>
        <span class="exp-val">${v}</span>
      </div>`;
  });
  box.innerHTML = html;
}

/* ---------- error-prone table ------------------------------ */
async function loadErrorProneRegions() {
  try {
    const data = await apiGet("/error-prone-regions", { top_n: 25 });
    const tbody = document.getElementById("regionTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    data.regions.forEach((r, i) => {
      const prob   = Number(r.mean_bust_probability || 0);
      const actual = Number(r.actual_bust_rate || 0);

      let tier, tierCls, barColor;
      if (prob >= 0.60)      { tier = "Critical"; tierCls = "critical"; barColor = "#b91c1c"; }
      else if (prob >= 0.45) { tier = "Elevated"; tierCls = "elevated"; barColor = "#ea580c"; }
      else if (prob >= 0.30) { tier = "Watch";    tierCls = "watch";    barColor = "#eab308"; }
      else                   { tier = "Nominal";  tierCls = "nominal";  barColor = "#16a34a"; }

      const lat = r.lat_center != null ? Number(r.lat_center).toFixed(2) + "°" : "—";
      const lon = r.lon_center != null ? Number(r.lon_center).toFixed(2) + "°" : "—";

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${String(i + 1).padStart(2, "0")}</td>
        <td>${r.region_id}</td>
        <td>${lat} / ${lon}</td>
        <td>${(actual * 100).toFixed(1)}%</td>
        <td>
          <div class="prob-cell">
            <span class="prob-val">${(prob * 100).toFixed(1)}%</span>
            <div class="prob-bar"><div class="prob-bar-fill" style="width:${prob*100}%; background:${barColor};"></div></div>
          </div>
        </td>
        <td>${Number(r.mean_pred_error || 0).toFixed(2)}</td>
        <td><span class="risk-chip ${tierCls}">${tier}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) { console.error("error-prone regions failed:", e); }
}

/* ---------- model diagnostics ------------------------------ */
async function loadModelInfo() {
  try {
    const info = await apiGet("/model-info");
    const m = info.metrics || {};

    const pr  = Number(m.pr_auc || 0);
    const roc = Number(m.roc_auc || 0);

    const prSmall = document.getElementById("kpiPRSmall");
    if (prSmall) prSmall.textContent = pr.toFixed(2);

    const grid = document.getElementById("trustGrid");
    if (grid) {
      const items = [
        { v: pr.toFixed(3),  l: "PR-AUC" },
        { v: roc.toFixed(3), l: "ROC-AUC" },
        { v: Number(m.regression_mae || 0).toFixed(3), l: "Error MAE" },
        { v: (Number(m.n_train || 0) / 1e6).toFixed(1) + "M", l: "Training Rows" },
        { v: (Number(m.train_bust_rate || 0) * 100).toFixed(1) + "%", l: "Train Bust Rate" },
        { v: (Number(m.val_bust_rate || 0) * 100).toFixed(1) + "%", l: "Validation Rate" },
      ];
      grid.innerHTML = items.map(x =>
        `<div class="metric-cell"><div class="metric-val">${x.v}</div><div class="metric-lbl">${x.l}</div></div>`
      ).join("");
    }

    const fc = document.getElementById("featureImportance");
    if (!fc) return;
    const feats = (info.feature_importance || []).slice(0, 8);
    if (!feats.length) {
      fc.innerHTML = `<p style="color:var(--text-3);font-size:12px;padding:8px 0">No feature importance data available.</p>`;
      return;
    }
    const max = Math.max(...feats.map(f => Number(f.importance || 0)), 1e-9);
    fc.innerHTML = feats.map(f => {
      const imp = Number(f.importance || 0);
      const w = (imp / max) * 100;
      return `
        <div class="feat-row">
          <div class="feat-name">${f.feature}</div>
          <div class="feat-track"><div class="feat-fill" style="width:${w}%"></div></div>
          <div class="feat-val">${imp.toFixed(3)}</div>
        </div>`;
    }).join("");
  } catch (e) {
    console.error("model info unavailable:", e);
    const grid = document.getElementById("trustGrid");
    if (grid) {
      grid.innerHTML = `<div style="grid-column:1/-1;padding:24px;color:var(--text-3);font-size:12px">
        Model metadata not available.
      </div>`;
    }
  }
}

/* ---------- jump from map to regional tab ------------------ */
function selectRegionTab(regionId) {
  document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));

  const tabBtn = document.querySelector('[data-tab="bust"]');
  if (tabBtn) tabBtn.classList.add("active");
  const view = document.getElementById("view-bust");
  if (view) view.classList.add("active");

  const sel = document.getElementById("regionSelect");
  if (sel) {
    if (!allRegionIds.includes(regionId)) {
      const o = document.createElement("option");
      o.value = regionId; o.textContent = regionId;
      sel.appendChild(o);
      allRegionIds.push(regionId);
    }
    sel.value = regionId;
    loadRegionDetail(regionId);
  }
  setTimeout(() => { if (map) map.invalidateSize(); }, 80);
}

/* ---------- boot ------------------------------------------- */
async function boot() {
  initTabs();
  initMap();
  buildLeadStrip();
  startClock();

  try {
    await apiGet("/health");
    setConn(true, "Live · model available");
  } catch (e) {
    setConn(false, "API unreachable");
    return;
  }

  await selectLeadDay(currentLeadDay);

  await Promise.all([
    loadNationalTrend(),
    loadErrorProneRegions(),
    loadModelInfo(),
  ]);
}

boot();