let trendChart;
let regionChart;


const chartText = "#78909c";
const chartGrid = "rgba(55,78,90,0.32)";
const chartBlue = "#70c5dc";


function renderTrendChart(points) {

  const canvas =
    document.getElementById("trendChart");

  if (!canvas) return;

  if (trendChart) {
    trendChart.destroy();
  }


  trendChart = new Chart(canvas, {

    type: "line",

    data: {

      labels:
        points.map(point => "D" + point.x),

      datasets: [{

        data:
          points.map(point => point.y),

        borderColor: chartBlue,

        backgroundColor:
          "rgba(112,197,220,0.08)",

        borderWidth: 1.7,

        pointRadius: 2,

        pointHoverRadius: 4,

        pointBackgroundColor: chartBlue,

        pointBorderWidth: 0,

        fill: true,

        tension: 0.3

      }]

    },

    options: {

      responsive: true,

      maintainAspectRatio: false,

      plugins: {

        legend: {
          display: false
        },

        tooltip: {

          displayColors: false,

          backgroundColor: "#09151d",

          borderColor: "#29414e",

          borderWidth: 1,

          titleFont: {
            family: "JetBrains Mono",
            size: 9
          },

          bodyFont: {
            family: "JetBrains Mono",
            size: 9
          },

          callbacks: {

            label: context => {

              return (
                " confidence: " +
                (context.raw * 100).toFixed(1) +
                "%"
              );

            }

          }

        }

      },

      scales: {

        y: {

          min: 0,

          max: 1,

          border: {
            display: false
          },

          ticks: {

            color: chartText,

            font: {
              family: "JetBrains Mono",
              size: 7
            },

            callback: value =>
              (value * 100) + "%",

            maxTicksLimit: 4

          },

          grid: {
            color: chartGrid
          }

        },

        x: {

          border: {
            display: false
          },

          ticks: {

            color: chartText,

            font: {
              family: "JetBrains Mono",
              size: 7
            }

          },

          grid: {
            display: false
          }

        }

      }

    }

  });
}


function renderRegionChart(rows) {

  const canvas =
    document.getElementById("regionChart");

  if (!canvas) return;

  if (regionChart) {
    regionChart.destroy();
  }


  regionChart = new Chart(canvas, {

    type: "bar",

    data: {

      labels:
        rows.map(row => "D" + row.lead_day),

      datasets: [{

        data:
          rows.map(row =>
            Number(row.mean_bust_probability) || 0
          ),

        backgroundColor:
          rows.map(row => {

            const probability =
              Number(row.mean_bust_probability) || 0;

            if (probability >= 0.55) {
              return "#df716c";
            }

            if (probability >= 0.30) {
              return "#d6aa5f";
            }

            return "#61c492";

          }),

        borderWidth: 0,

        borderRadius: 2,

        barPercentage: 0.58,

        categoryPercentage: 0.75

      }]

    },

    options: {

      responsive: true,

      maintainAspectRatio: false,

      plugins: {

        legend: {
          display: false
        },

        tooltip: {

          displayColors: false,

          backgroundColor: "#09151d",

          borderColor: "#29414e",

          borderWidth: 1,

          titleFont: {
            family: "JetBrains Mono",
            size: 9
          },

          bodyFont: {
            family: "JetBrains Mono",
            size: 9
          },

          callbacks: {

            label: context =>
              " bust probability: " +
              (context.raw * 100).toFixed(1) +
              "%"

          }

        }

      },

      scales: {

        y: {

          min: 0,

          max: 1,

          border: {
            display: false
          },

          ticks: {

            color: chartText,

            font: {
              family: "JetBrains Mono",
              size: 8
            },

            callback: value =>
              (value * 100) + "%"

          },

          grid: {
            color: chartGrid
          }

        },

        x: {

          border: {
            display: false
          },

          ticks: {

            color: chartText,

            font: {
              family: "JetBrains Mono",
              size: 8
            }

          },

          grid: {
            display: false
          }

        }

      }

    }

  });
}