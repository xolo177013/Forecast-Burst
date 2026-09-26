/* ============================================================
   CHARTS — light theme
   ============================================================ */

Chart.defaults.font.family = "JetBrains Mono, monospace";
Chart.defaults.font.size = 10;
Chart.defaults.color = "#748696";

const GRID_LINE = "rgba(120,145,165,.14)";

let trendChartInstance = null;
let regionChartInstance = null;

/* ---------- trend ------------------------------------------ */
function renderTrendChart(points) {
  const canvas = document.getElementById("trendChart");
  if (!canvas) return;
  if (trendChartInstance) trendChartInstance.destroy();

  trendChartInstance = new Chart(canvas, {
    type: "line",
    data: {
      labels: points.map(p => "D" + String(p.x).padStart(2, "0")),
      datasets: [{
        data: points.map(p => +(p.y * 100).toFixed(1)),
        borderColor: "#0ea5b7",
        backgroundColor: (ctx) => {
          const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 140);
          g.addColorStop(0, "rgba(14,165,183,.22)");
          g.addColorStop(1, "rgba(14,165,183,0)");
          return g;
        },
        fill: true,
        tension: 0.38,
        borderWidth: 1.8,
        pointRadius: 2.6,
        pointHoverRadius: 4.5,
        pointBackgroundColor: "#fff",
        pointBorderColor: "#0ea5b7",
        pointBorderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0a1e2e",
          padding: 10,
          titleFont: { size: 10 },
          bodyFont: { size: 11 },
          displayColors: false,
          callbacks: { label: (c) => `Confidence: ${c.parsed.y}%` },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { display: false },
             ticks: { font: { size: 9 }, color: "#9aa9b6" } },
        y: {
          min: 0, max: 100,
          grid: { color: GRID_LINE },
          border: { display: false },
          ticks: { font: { size: 9 }, color: "#9aa9b6",
                   callback: (v) => v + "%", stepSize: 25 },
        },
      },
    },
  });
}

/* ---------- region profile --------------------------------- */
function renderRegionChart(byLeadDay) {
  const canvas = document.getElementById("regionChart");
  if (!canvas) return;
  if (regionChartInstance) regionChartInstance.destroy();

  const days = byLeadDay.map(r => "Day " + String(r.lead_day).padStart(2, "0"));
  const bust = byLeadDay.map(r => +(Number(r.mean_bust_probability || 0) * 100).toFixed(1));
  const conf = byLeadDay.map(r => +(Number(r.mean_confidence || 0) * 100).toFixed(1));

  regionChartInstance = new Chart(canvas, {
    type: "bar",
    data: {
      labels: days,
      datasets: [
        {
          label: "Bust probability",
          data: bust,
          backgroundColor: (ctx) => {
            const v = ctx.parsed?.y ?? 0;
            if (v >= 60) return "rgba(220,38,38,.72)";
            if (v >= 40) return "rgba(234,88,12,.72)";
            if (v >= 25) return "rgba(234,179,8,.72)";
            return "rgba(14,165,183,.65)";
          },
          borderRadius: 5,
          borderSkipped: false,
          barPercentage: 0.55,
          order: 2,
        },
        {
          label: "Confidence",
          type: "line",
          data: conf,
          borderColor: "#16a34a",
          backgroundColor: "transparent",
          borderWidth: 2,
          borderDash: [5, 4],
          tension: 0.35,
          pointRadius: 3,
          pointBackgroundColor: "#fff",
          pointBorderColor: "#16a34a",
          pointBorderWidth: 2,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top", align: "end",
          labels: {
            color: "#485d70",
            boxWidth: 10, boxHeight: 10,
            padding: 16,
            font: { size: 10.5, family: "Inter" },
            usePointStyle: true, pointStyle: "rectRounded",
          },
        },
        tooltip: {
          backgroundColor: "#0a1e2e",
          padding: 12,
          titleFont: { size: 11 },
          bodyFont: { size: 11 },
          callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y}%` },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { display: false },
             ticks: { font: { size: 10 }, color: "#748696" } },
        y: {
          min: 0, max: 100,
          grid: { color: GRID_LINE },
          border: { display: false },
          ticks: { callback: (v) => v + "%", stepSize: 20, color: "#9aa9b6" },
        },
      },
    },
  });
}