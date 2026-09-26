/* ============================================================
   GRID MAP — OpenStreetMap tiles + colored 1°×1° rectangles
   ============================================================ */

const GRID_SIZE = 1.0;

let map;
let gridLayer;

/* ---------- colours ---------------------------------------- */
function confidenceColor(c) {
  if (c >= 0.75) return "#1b7a3e";
  if (c >= 0.60) return "#7cb342";
  if (c >= 0.45) return "#fdd835";
  if (c >= 0.30) return "#f57c00";
  return "#c62828";
}

/* ---------- init ------------------------------------------- */
function initMap() {
  map = L.map("map", {
    zoomControl: false,
    attributionControl: true,
    minZoom: 3,
    maxZoom: 8,
  }).setView([22, 80], 4.7);

  L.control.zoom({ position: "bottomright" }).addTo(map);

  // Primary: OpenStreetMap (most reliable, no key)
  const osm = L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      subdomains: "abc",
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }
  );

  // Backup: Esri Light Gray Canvas (subtler)
  const esri = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 16,
      attribution: "Tiles &copy; Esri",
    }
  );

  osm.addTo(map);

  // If OSM fails after 3 tiles, swap to Esri
  let osmErrors = 0;
  osm.on("tileerror", () => {
    osmErrors++;
    if (osmErrors === 3 && !map.hasLayer(esri)) {
      console.warn("[map] OSM failed — switching to Esri");
      map.removeLayer(osm);
      esri.addTo(map);
    }
  });

  gridLayer = L.layerGroup().addTo(map);

  // Clear the loading overlay as soon as tiles start arriving
  map.whenReady(() => {
    const el = document.getElementById("mapLoading");
    if (el) el.classList.remove("on");
  });
  // Also force-clear after 800ms in case the event fires before we attach
  setTimeout(() => {
    const el = document.getElementById("mapLoading");
    if (el) el.classList.remove("on");
  }, 800);
}

/* ---------- render ----------------------------------------- */
function renderMap(regions) {
  if (!gridLayer) return;
  gridLayer.clearLayers();
  if (!regions || !regions.length) return;

  const half = GRID_SIZE / 2;

  regions.forEach(region => {
    const confidence  = Number(region.forecast_confidence) || 0;
    const probability = Number(region.bust_probability) || 0;
    const color = confidenceColor(confidence);

    const bounds = [
      [region.lat_center - half, region.lon_center - half],
      [region.lat_center + half, region.lon_center + half],
    ];

    const rect = L.rectangle(bounds, {
      color: color,
      weight: 0.5,
      opacity: 0.35,
      fillColor: color,
      fillOpacity: 0.5,
      interactive: true,
    });

    rect.bindPopup(`
      <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.65;">
        <strong style="font-size:12px;">${region.region_id}</strong><br>
        <span style="color:#748696;">Lat / Lon&nbsp;</span>
        ${Number(region.lat_center).toFixed(2)}° / ${Number(region.lon_center).toFixed(2)}°<br>
        <span style="color:#748696;">Confidence&nbsp;</span>
        <strong>${(confidence * 100).toFixed(0)}%</strong><br>
        <span style="color:#748696;">P(bust)&nbsp;</span>
        <strong>${(probability * 100).toFixed(0)}%</strong>
      </div>
    `);

    rect.on("mouseover", function () {
      this.setStyle({ weight: 1.8, opacity: 1, fillOpacity: 0.8 });
    });
    rect.on("mouseout", function () {
      this.setStyle({ weight: 0.5, opacity: 0.55, fillOpacity: 0.55 });
    });
    rect.on("click", () => {
      if (typeof selectRegionTab === "function") {
        selectRegionTab(region.region_id);
      }
    });

    rect.addTo(gridLayer);
  });

  console.log(`[map] rendered ${regions.length} cells`);
}