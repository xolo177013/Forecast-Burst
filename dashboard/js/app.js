let currentLeadDay = 5;

let confidenceCache = {};

let allRegionIds = [];


/* ============================================================
   NAVIGATION
   ============================================================ */

function initTabs() {

  document
    .querySelectorAll(".side-link")
    .forEach(button => {

      button.onclick = () => {

        const tab =
          button.dataset.tab;


        document
          .querySelectorAll(".side-link")
          .forEach(item =>
            item.classList.remove("active")
          );


        document
          .querySelectorAll(".view")
          .forEach(view =>
            view.classList.remove("active")
          );


        button.classList.add("active");


        const target =
          document.getElementById("tab-" + tab);


        if (target) {
          target.classList.add("active");
        }


        updatePageHeader(tab);


        setTimeout(() => {

          if (map) {
            map.invalidateSize();
          }

        }, 80);

      };

    });

}


function updatePageHeader(tab) {

  const title =
    document.getElementById("pageTitle");

  const description =
    document.getElementById("pageDescription");


  const pages = {

    map: {

      title:
        "Regional Forecast Confidence",

      description:
        "Spatial assessment of forecast bust probability across the monitored domain."

    },

    bust: {

      title:
        "Regional Risk Analysis",

      description:
        "Inspect the evolution of forecast bust probability for individual regions."

    },

    regions: {

      title:
        "Error-Prone Areas",

      description:
        "Regions showing elevated forecast error and bust behaviour during validation."

    },

    trust: {

      title:
        "Model Diagnostics",

      description:
        "Validation metrics, feature importance and methodology behind the forecast confidence system."

    }

  };


  if (!pages[tab]) return;


  title.textContent =
    pages[tab].title;

  description.textContent =
    pages[tab].description;

}


/* ============================================================
   CONNECTION
   ============================================================ */

function setConn(ok, text) {

  const dot =
    document.getElementById("connDot");

  const label =
    document.getElementById("connText");


  if (dot) {

    dot.className =
      "status-light" + (ok ? "" : " off");

  }


  if (label) {
    label.textContent = text;
  }

}


/* ============================================================
   DAY SELECTOR
   ============================================================ */

function buildLeadStrip() {

  const strip =
    document.getElementById("leadStrip");

  strip.innerHTML = "";


  for (let day = 1; day <= 10; day++) {

    const button =
      document.createElement("button");


    button.className =
      "leadbtn" +
      (day === currentLeadDay
        ? " active"
        : "");


    button.textContent =
      "DAY " +
      String(day).padStart(2, "0");


    button.id =
      "lead-" + day;


    button.onclick = () =>
      selectLeadDay(day);


    strip.appendChild(button);

  }

}


/* ============================================================
   SELECT DAY
   ============================================================ */

async function selectLeadDay(day) {

  currentLeadDay = day;


  document
    .querySelectorAll(".leadbtn")
    .forEach(button =>
      button.classList.remove("active")
    );


  const activeButton =
    document.getElementById("lead-" + day);


  if (activeButton) {
    activeButton.classList.add("active");
  }


  updateDayLabels(day);


  try {

    const data =
      await apiGet(
        "/confidence-map",
        {
          lead_day: day
        }
      );


    confidenceCache[day] =
      data.regions;


    renderMap(data.regions);


    updateConfidenceUI(
      data.regions
    );


    if (allRegionIds.length === 0) {

      allRegionIds =
        data.regions
          .map(region => region.region_id)
          .sort();


      populateRegionSelect();

    }

  } catch (error) {

    console.error(
      "Unable to load confidence map:",
      error
    );

  }

}


/* ============================================================
   DAY LABELS
   ============================================================ */

function updateDayLabels(day) {

  const value =
    String(day).padStart(2, "0");


  const elements = [

    "activeDayLabel",

    "overlayDay",

    "sideDay",

    "explainDay"

  ];


  elements.forEach(id => {

    const element =
      document.getElementById(id);

    if (element) {
      element.textContent = value;
    }

  });

}


/* ============================================================
   CONFIDENCE UI
   ============================================================ */

function updateConfidenceUI(regions) {

  if (!regions || !regions.length) {
    return;
  }


  const average =
    regions.reduce(
      (sum, region) =>
        sum +
        Number(region.forecast_confidence || 0),
      0
    ) / regions.length;


  const highRisk =
    regions.filter(
      region =>
        Number(region.bust_probability || 0) > 0.5
    ).length;


  const percentage =
    Math.round(average * 100);


  const confidence =
    document.getElementById("kpiConf");


  const regionCount =
    document.getElementById("kpiRegions");


  const riskCount =
    document.getElementById("kpiHigh");


  if (confidence) {
    confidence.textContent =
      percentage + "%";
  }


  if (regionCount) {
    regionCount.textContent =
      regions.length;
  }


  if (riskCount) {
    riskCount.textContent =
      highRisk;
  }


  const sideConfidence =
    document.getElementById(
      "sideConfidence"
    );


  if (sideConfidence) {

    sideConfidence.textContent =
      percentage + "%";

  }


  const meter =
    document.getElementById(
      "confidenceMeter"
    );


  if (meter) {

    meter.style.width =
      percentage + "%";


    if (average >= 0.7) {

      meter.style.background =
        "#61c492";

    } else if (average >= 0.45) {

      meter.style.background =
        "#d6aa5f";

    } else {

      meter.style.background =
        "#df716c";

    }

  }


  const badge =
    document.getElementById(
      "confidenceBadge"
    );


  if (badge) {

    badge.className =
      "confidence-badge";


    if (average >= 0.7) {

      badge.textContent =
        "HIGH CONFIDENCE";

    } else if (average >= 0.45) {

      badge.textContent =
        "MONITOR";

      badge.classList.add(
        "medium"
      );

    } else {

      badge.textContent =
        "HIGH RISK";

      badge.classList.add(
        "high"
      );

    }

  }

}


/* ============================================================
   NATIONAL TREND
   ============================================================ */

async function loadNationalTrend() {

  const points = [];


  for (
    let day = 1;
    day <= 10;
    day++
  ) {

    try {

      const data =
        confidenceCache[day] ||
        (
          await apiGet(
            "/confidence-map",
            {
              lead_day: day
            }
          )
        ).regions;


      confidenceCache[day] =
        data;


      if (!data.length) {
        continue;
      }


      const average =
        data.reduce(
          (sum, region) =>
            sum +
            Number(
              region.forecast_confidence || 0
            ),
          0
        ) / data.length;


      points.push({

        x: day,

        y: average

      });


    } catch (error) {

      console.warn(
        "Trend day failed:",
        day,
        error
      );

    }

  }


  renderTrendChart(points);
}


/* ============================================================
   REGION SELECTOR
   ============================================================ */

function populateRegionSelect() {

  const select =
    document.getElementById(
      "regionSelect"
    );


  if (!select) return;


  select.innerHTML = "";


  allRegionIds.forEach(regionId => {

    const option =
      document.createElement("option");


    option.value =
      regionId;


    option.textContent =
      regionId;


    select.appendChild(option);

  });


  select.onchange = () =>
    loadRegionDetail(
      select.value
    );


  if (allRegionIds.length) {

    loadRegionDetail(
      allRegionIds[0]
    );

  }

}


/* ============================================================
   REGION DETAIL
   ============================================================ */

async function loadRegionDetail(regionId) {

  if (!regionId) {
    return;
  }


  try {

    const trend =
      await apiGet(
        "/bust-probability",
        {
          region_id: regionId
        }
      );


    renderRegionChart(
      trend.by_lead_day
    );


  } catch (error) {

    console.error(
      "Region probability failed:",
      error
    );

  }


  try {

    const explanation =
      await apiGet(
        "/explain",
        {
          region_id: regionId,

          lead_day: currentLeadDay
        }
      );


    renderExplanation(
      explanation
    );


  } catch (error) {

    const box =
      document.getElementById(
        "reasonBox"
      );


    if (box) {

      box.textContent =
        "No explanation available for this region and lead day.";

    }

  }

}


/* ============================================================
   EXPLANATION
   ============================================================ */

function renderExplanation(data) {

  const box =
    document.getElementById(
      "reasonBox"
    );


  if (!box) return;


  const confidence =
    Number(
      data.forecast_confidence || 0
    );


  let badgeClass =
    "lo";


  if (confidence < 0.45) {

    badgeClass = "hi";

  } else if (confidence < 0.70) {

    badgeClass = "mid";

  }


  const reasons =
    String(
      data.top_reasons || ""
    )
      .split(";")
      .map(reason => reason.trim())
      .filter(Boolean);


  let html = `

    <div style="margin-bottom:12px;">

      <span class="badge ${badgeClass}">
        ${(confidence * 100).toFixed(0)}% CONFIDENCE
      </span>

    </div>

  `;


  reasons.forEach(reason => {

    const separator =
      reason.indexOf("=");


    let feature =
      reason;


    let value = "";


    if (separator !== -1) {

      feature =
        reason.substring(
          0,
          separator
        ).trim();


      value =
        reason.substring(
          separator + 1
        ).trim();

    }


    html += `

      <div class="reason-item">

        <span class="reason-feat">
          ${feature}
        </span>

        <span>
          ${value}
        </span>

      </div>

    `;

  });


  box.innerHTML =
    html;

}


/* ============================================================
   ERROR-PRONE REGIONS
   ============================================================ */

async function loadErrorProneRegions() {

  try {

    const data =
      await apiGet(
        "/error-prone-regions",
        {
          top_n: 20
        }
      );


    const tbody =
      document.getElementById(
        "regionTableBody"
      );


    if (!tbody) return;


    tbody.innerHTML = "";


    data.regions.forEach(region => {

      const tr =
        document.createElement("tr");


      const probability =
        Number(
          region.mean_bust_probability || 0
        );


      tr.innerHTML = `

        <td>
          ${region.region_id}
        </td>

        <td>
          ${(Number(region.actual_bust_rate || 0) * 100).toFixed(1)}%
        </td>

        <td>

          ${(probability * 100).toFixed(1)}%

          <div class="bar-track">

            <div
              class="bar-fill"
              style="width:${probability * 100}%"
            ></div>

          </div>

        </td>

        <td>
          ${Number(region.mean_pred_error || 0).toFixed(2)}
        </td>

      `;


      tbody.appendChild(tr);

    });


  } catch (error) {

    console.error(
      "Error-prone regions failed:",
      error
    );

  }

}


/* ============================================================
   MODEL INFORMATION
   ============================================================ */

async function loadModelInfo() {

  try {

    const info =
      await apiGet(
        "/model-info"
      );


    const metrics =
      info.metrics;


    if (!metrics) {
      return;
    }


    const pr =
      Number(metrics.pr_auc || 0);


    const roc =
      Number(metrics.roc_auc || 0);


    const prElement =
      document.getElementById(
        "kpiPR"
      );


    const rocElement =
      document.getElementById(
        "kpiROC"
      );


    if (prElement) {
      prElement.textContent =
        pr.toFixed(2);
    }


    if (rocElement) {
      rocElement.textContent =
        roc.toFixed(2);
    }


    const trustGrid =
      document.getElementById(
        "trustGrid"
      );


    if (trustGrid) {

      trustGrid.innerHTML = `

        <div class="trust-item">
          <div class="val">
            ${pr.toFixed(3)}
          </div>
          <div class="lbl">
            PR-AUC
          </div>
        </div>

        <div class="trust-item">
          <div class="val">
            ${roc.toFixed(3)}
          </div>
          <div class="lbl">
            ROC-AUC
          </div>
        </div>

        <div class="trust-item">
          <div class="val">
            ${Number(metrics.regression_mae || 0).toFixed(3)}
          </div>
          <div class="lbl">
            ERROR MAE
          </div>
        </div>

        <div class="trust-item">
          <div class="val">
            ${(Number(metrics.n_train || 0) / 1e6).toFixed(1)}M
          </div>
          <div class="lbl">
            TRAINING ROWS
          </div>
        </div>

        <div class="trust-item">
          <div class="val">
            ${(Number(metrics.train_bust_rate || 0) * 100).toFixed(1)}%
          </div>
          <div class="lbl">
            TRAIN BUST RATE
          </div>
        </div>

        <div class="trust-item">
          <div class="val">
            ${(Number(metrics.val_bust_rate || 0) * 100).toFixed(1)}%
          </div>
          <div class="lbl">
            VALIDATION RATE
          </div>
        </div>

      `;

    }


    const featureContainer =
      document.getElementById(
        "featureImportance"
      );


    if (!featureContainer) {
      return;
    }


    const features =
      (info.feature_importance || [])
        .slice(0, 8);


    if (!features.length) {

      featureContainer.innerHTML =
        `<p class="sub">No feature importance data available.</p>`;

      return;

    }


    const maximum =
      Math.max(
        ...features.map(
          feature =>
            Number(feature.importance || 0)
        ),
        1
      );


    featureContainer.innerHTML =
      features.map(feature => {

        const importance =
          Number(
            feature.importance || 0
          );


        const width =
          (importance / maximum) * 100;


        return `

          <div class="feat-row">

            <div class="feat-name">
              ${feature.feature}
            </div>

            <div class="feat-track">

              <div
                class="feat-fill"
                style="width:${width}%"
              ></div>

            </div>

          </div>

        `;

      }).join("");


  } catch (error) {

    console.error(
      "Model information unavailable:",
      error
    );

    const trustGrid =
      document.getElementById(
        "trustGrid"
      );


    if (trustGrid) {

      trustGrid.innerHTML = `

        <div style="
          grid-column:1/-1;
          padding:20px;
          color:#70838e;
          font-size:10px;
        ">
          Model metadata not available.
          Run Step 2 to generate model_metadata.json.
        </div>

      `;

    }

  }

}


/* ============================================================
   BOOT
   ============================================================ */

async function boot() {

  initTabs();

  initMap();

  buildLeadStrip();


  try {

    await apiGet("/health");

    setConn(
      true,
      "Connected · backtest output"
    );


  } catch (error) {

    setConn(
      false,
      "API unreachable"
    );

    return;

  }


  await selectLeadDay(
    currentLeadDay
  );


  await Promise.all([

    loadNationalTrend(),

    loadErrorProneRegions(),

    loadModelInfo()

  ]);

}


boot();