const GRID_SIZE = 1.0;

let map;
let gridLayer;

const riskColor = (confidence) => {

  if (confidence >= 0.70) {
    return "#61c492";
  }

  if (confidence >= 0.45) {
    return "#d6aa5f";
  }

  return "#df716c";
};


function initMap() {

  map = L.map("map", {

    zoomControl: false,

    attributionControl: true,

    minZoom: 3,

    maxZoom: 8

  }).setView([22, 80], 4.7);


  L.control.zoom({
    position: "bottomright"
  }).addTo(map);


  L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      subdomains: "abc",

      maxZoom: 8,

      minZoom: 3,

      attribution:
        '&copy; OpenStreetMap contributors'
    }
  ).addTo(map);


  gridLayer = L.layerGroup().addTo(map);
}


function renderMap(regions) {

  if (!gridLayer) return;

  gridLayer.clearLayers();

  const half = GRID_SIZE / 2;


  regions.forEach(region => {

    const confidence =
      Number(region.forecast_confidence) || 0;

    const probability =
      Number(region.bust_probability) || 0;

    const color = riskColor(confidence);


    const bounds = [

      [
        region.lat_center - half,
        region.lon_center - half
      ],

      [
        region.lat_center + half,
        region.lon_center + half
      ]

    ];


    L.rectangle(
      bounds,
      {

        color: color,

        weight: 0.5,

        opacity: 0.35,

        fillColor: color,

        fillOpacity: 0.34,

        interactive: true

      }
    )
      .bindPopup(`
        <div>
          <strong>${region.region_id}</strong>
          <br>
          confidence:
          ${(confidence * 100).toFixed(0)}%
          <br>
          bust probability:
          ${(probability * 100).toFixed(0)}%
        </div>
      `)
      .addTo(gridLayer);

  });
}