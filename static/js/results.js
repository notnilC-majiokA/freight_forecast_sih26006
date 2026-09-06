/* SIH26006 - results page rendering.
 * Loads the last recommendation (sessionStorage first, then
 * /api/last-forecast), fills every section and draws the Chart.js chart.
 */
(function () {
  "use strict";

  const noDataState = document.getElementById("noDataState");
  const resultContent = document.getElementById("resultContent");
  let chart = null;

  const fmtUsd = (n) =>
    "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtUsd0 = (n) =>
    "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
  const fmtInt = (n) => Number(n).toLocaleString("en-US");

  function cell(label, value) {
    const col = document.createElement("div");
    col.className = "col-6 col-md-4 col-lg-2";
    col.innerHTML =
      '<div class="text-muted small text-uppercase">' +
      label +
      '</div><div class="fw-semibold">' +
      value +
      "</div>";
    return col;
  }

  function renderScenario(req, generatedAt) {
    const wrap = document.getElementById("scenarioSummary");
    wrap.innerHTML = "";
    wrap.appendChild(cell("Cargo type", req.cargo_type));
    wrap.appendChild(cell("Quantity (t)", fmtInt(req.quantity_tonnes)));
    wrap.appendChild(cell("Delivery deadline", "within " + req.delivery_window_days + " days"));
    wrap.appendChild(cell("East Coast port", req.destination_port));
    wrap.appendChild(cell("Preferred origin", req.origin_region));
    wrap.appendChild(
      cell("Generated (UTC)", new Date(generatedAt).toISOString().slice(0, 16).replace("T", " "))
    );
  }

  function renderRecommendation(rec) {
    document.getElementById("recWeek").textContent =
      "Week " + (rec.chartering_week_index + 1) + " (" + rec.chartering_week_start + ")";
    document.getElementById("recRoute").textContent =
      rec.origin_region + " / " + rec.load_port + " → " + rec.destination_port;
    document.getElementById("recVessel").textContent =
      rec.vessel_type + " (~" + fmtInt(rec.vessel_capacity_tonnes) + " t)";
    document.getElementById("recVoyages").textContent = rec.number_of_voyages;
    document.getElementById("recRate").textContent =
      fmtUsd(rec.expected_freight_rate_usd_per_tonne) + " / t";
    document.getElementById("recTotalCost").textContent =
      fmtUsd0(rec.total_expected_freight_cost_usd);
    document.getElementById("recSavings").textContent =
      fmtUsd0(rec.expected_savings_vs_booking_now_usd);

    const lead = Math.round(rec.estimated_delivery_lead_days);
    const ok = rec.within_delivery_window ? "✓ within deadline" : "✗ exceeds deadline";
    document.getElementById("recLead").textContent =
      lead + " d / " + rec.delivery_deadline_days + " d  (" + ok + ")";

    document.getElementById("confidenceBadge").textContent =
      "Forecast confidence: " + rec.confidence + " (" + rec.confidence_score + ")";

    document.getElementById("recJustification").textContent = rec.justification || "";
    const notes = document.getElementById("recNotes");
    notes.innerHTML = (rec.feasibility_notes || [])
      .map((n) => "<li>" + n + "</li>")
      .join("");
  }

  function renderCostComparison(rows) {
    const body = document.getElementById("costComparisonBody");
    body.innerHTML = "";
    rows.forEach(function (r) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" +
        r.label +
        '</td><td class="text-end">' +
        Number(r.freight_rate_usd_per_tonne).toFixed(2) +
        '</td><td class="text-end">' +
        fmtUsd0(r.total_freight_cost_usd) +
        '</td><td class="text-end">' +
        fmtUsd0(r.delta_vs_recommended_usd) +
        "</td>";
      body.appendChild(tr);
    });
  }

  function renderRouteInfo(info) {
    const dl = document.getElementById("routeInfo");
    const pairs = [
      ["Lane id", info.route_id],
      ["Origin region", info.origin_region],
      ["Load port", info.load_port],
      ["East Coast port", info.destination_port],
      ["Cargo", info.cargo_type],
      ["Vessel type", info.vessel_type],
      ["Vessel capacity", fmtInt(info.vessel_capacity_tonnes) + " t"],
      ["Approx. distance", fmtInt(info.approx_distance_nm) + " nm"],
      ["Est. sea transit", info.estimated_transit_days + " days"],
    ];
    dl.innerHTML = pairs
      .map(
        (p) =>
          '<dt class="col-6 text-muted fw-normal">' +
          p[0] +
          '</dt><dd class="col-6 fw-semibold">' +
          p[1] +
          "</dd>"
      )
      .join("");
  }

  function renderChart(forecast) {
    const labels = forecast.map((p) => "W" + (p.week_index + 1) + " " + p.week_start);
    const predicted = forecast.map((p) => p.predicted_rate_usd_per_tonne);
    const lower = forecast.map((p) => p.lower_bound_usd_per_tonne);
    const upper = forecast.map((p) => p.upper_bound_usd_per_tonne);

    const ctx = document.getElementById("forecastChart").getContext("2d");
    if (chart) {
      chart.destroy();
    }
    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Upper bound",
            data: upper,
            borderColor: "rgba(27,152,224,0.3)",
            backgroundColor: "rgba(27,152,224,0.12)",
            fill: "+1",
            pointRadius: 0,
            borderWidth: 1,
          },
          {
            label: "Lower bound",
            data: lower,
            borderColor: "rgba(27,152,224,0.3)",
            backgroundColor: "rgba(27,152,224,0.12)",
            fill: false,
            pointRadius: 0,
            borderWidth: 1,
          },
          {
            label: "Predicted rate ($/t) - DEMO",
            data: predicted,
            borderColor: "#0d3b66",
            backgroundColor: "#0d3b66",
            fill: false,
            tension: 0.25,
            pointRadius: 3,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: { title: { display: true, text: "Freight rate (USD / tonne)" } },
          x: {
            title: { display: true, text: "Forecast week" },
            ticks: { maxRotation: 60, minRotation: 30 },
          },
        },
        plugins: {
          legend: { position: "bottom" },
          title: {
            display: true,
            text: "DEMO DATA - NOT REAL MARKET DATA",
          },
        },
      },
    });
  }

  function render(data) {
    document.getElementById("disclaimerBanner").innerHTML =
      "<strong>DEMO DATA &mdash; NOT REAL MARKET DATA.</strong> " + data.disclaimer;
    renderScenario(data.request, data.generated_at);
    renderRecommendation(data.recommendation);
    renderCostComparison(data.cost_comparison);
    renderRouteInfo(data.route_info);
    renderChart(data.forecast);
    resultContent.classList.remove("d-none");
    noDataState.classList.add("d-none");
  }

  async function load() {
    // 1) Try the copy the home page stored for this browser session.
    let raw = null;
    try {
      raw = sessionStorage.getItem("sih26006_forecast");
    } catch (_) {
      /* ignore */
    }
    if (raw) {
      try {
        render(JSON.parse(raw));
        return;
      } catch (_) {
        /* fall through to API */
      }
    }

    // 2) Fall back to the server's most recent recommendation.
    try {
      const res = await fetch("/api/last-forecast");
      if (res.ok) {
        render(await res.json());
        return;
      }
    } catch (_) {
      /* ignore */
    }

    // 3) Nothing available.
    noDataState.classList.remove("d-none");
    resultContent.classList.add("d-none");
  }

  load();
})();
