/* SIH26006 - results page rendering.
 * Loads the last decision (sessionStorage first, then /api/last-forecast) and
 * fills the 9 dashboard sections + the forecast chart.
 */
(function () {
  "use strict";

  const noDataState = document.getElementById("noDataState");
  const loadError = document.getElementById("loadError");
  const resultContent = document.getElementById("resultContent");
  let chart = null;

  const usd = (n, d) =>
    "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: d ?? 2, maximumFractionDigits: d ?? 2 });
  const usd0 = (n) => "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
  const int = (n) => Number(n).toLocaleString("en-US");
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );

  const levelClass = (lvl) => "lvl-" + String(lvl || "").toLowerCase().replace(/[^a-z]/g, "");

  function cell(label, value) {
    const c = document.createElement("div");
    c.className = "col-6 col-md-4 col-lg-3";
    c.innerHTML =
      '<div class="text-muted small text-uppercase">' + esc(label) + "</div>" +
      '<div class="fw-semibold">' + value + "</div>";
    return c;
  }

  // ---- Section 1: hero -----------------------------------------------------
  function renderHero(rec) {
    document.getElementById("recHeadline").textContent = rec.headline;
    document.getElementById("recAction").textContent = rec.contract_strategy;
    document.getElementById("recEntry").textContent = rec.entry_week_range;
    document.getElementById("recRoute").textContent =
      rec.origin_country + " (" + rec.origin_port + ") → " + rec.destination_port;
    document.getElementById("recVessel").textContent =
      rec.vessel_type + " × " + rec.number_of_voyages;
    document.getElementById("recRate").textContent =
      usd(rec.expected_freight_rate_usd_per_tonne) + " / t";
    document.getElementById("recTotal").textContent = usd0(rec.expected_total_cost_usd);
    document.getElementById("recSavings").textContent =
      usd0(rec.expected_savings_vs_spot_usd) +
      " (" + Number(rec.expected_savings_vs_spot_pct).toFixed(1) + "%)";
    document.getElementById("recRisk").textContent =
      rec.idle_risk + " / " + rec.market_risk + " / " + rec.forecast_confidence;

    const badge = document.getElementById("heroFeasBadge");
    const ok = rec.port_feasibility === "FEASIBLE" && rec.delivery_feasible;
    badge.textContent = ok ? "FEASIBLE" : "REVIEW FLAGS";
    badge.classList.toggle("is-feasible", ok);
    badge.classList.toggle("is-infeasible", !ok);
    document.getElementById("recHero").classList.toggle("hero-warn", !ok);
  }

  // ---- scenario recap ---------------------------------------------------
  function renderScenario(req, route, generatedAt) {
    const wrap = document.getElementById("scenarioSummary");
    wrap.innerHTML = "";
    wrap.appendChild(cell("Commodity", esc(req.cargo_type)));
    wrap.appendChild(cell("Quantity (t)", int(req.quantity_tonnes)));
    wrap.appendChild(cell("Origin", esc(req.origin_country) + " / " + esc(route.load_port)));
    wrap.appendChild(cell("Destination", esc(req.destination_port)));
    wrap.appendChild(cell("Delivery window", "within " + req.delivery_window_days + " days"));
    wrap.appendChild(cell("Vessel preference", esc(req.vessel_preference)));
    wrap.appendChild(cell("Contract preference", esc(req.contract_preference)));
    wrap.appendChild(
      cell("Generated (UTC)", esc(new Date(generatedAt).toISOString().slice(0, 16).replace("T", " ")))
    );
  }

  // ---- Section 2: forecast -------------------------------------------------
  function renderForecast(fs, recEntryIdx) {
    document.getElementById("forecastMeta").textContent =
      "Trend: " + fs.trend + " · confidence " + fs.confidence +
      " · " + fs.history_weeks + "w history";

    const stats = document.getElementById("forecastStats");
    const items = [
      ["Trend", fs.trend + " (" + Number(fs.trend_usd_per_week).toFixed(2) + " $/t/wk)"],
      ["Volatility", Number(fs.volatility_pct).toFixed(1) + "% of mean"],
      ["Confidence", fs.confidence + " (" + fs.confidence_score + ")"],
      ["Backtest MAPE", fs.backtest_mape_pct == null ? "n/a" : fs.backtest_mape_pct + "%"],
    ];
    stats.innerHTML = items
      .map(
        (it) =>
          '<div class="col-6 col-lg-3"><div class="stat-tile"><div class="text-muted small text-uppercase">' +
          esc(it[0]) + '</div><div class="fw-semibold">' + esc(it[1]) + "</div></div></div>"
      )
      .join("");

    const hist = fs.historical || [];
    const fc = fs.forecast || [];
    const labels = hist.map((p) => p.week_start).concat(fc.map((p) => p.week_start));
    const gap = new Array(hist.length).fill(null);
    const histSeries = hist.map((p) => p.rate_usd_per_tonne).concat(new Array(fc.length).fill(null));
    const predSeries = gap.concat(fc.map((p) => p.predicted_rate_usd_per_tonne));
    const lowSeries = gap.concat(fc.map((p) => p.lower_bound_usd_per_tonne));
    const highSeries = gap.concat(fc.map((p) => p.upper_bound_usd_per_tonne));
    // Bridge history -> forecast so the line is continuous.
    if (hist.length && fc.length) predSeries[hist.length - 1] = hist[hist.length - 1].rate_usd_per_tonne;

    const entryPointIdx = hist.length + Math.min(recEntryIdx, Math.max(fc.length - 1, 0));
    const marker = labels.map((_, i) => (i === entryPointIdx ? predSeries[i] : null));

    const ctx = document.getElementById("forecastChart").getContext("2d");
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          { label: "Forecast upper", data: highSeries, borderColor: "rgba(27,152,224,0.25)", backgroundColor: "rgba(27,152,224,0.12)", fill: "+1", pointRadius: 0, borderWidth: 1 },
          { label: "Forecast lower", data: lowSeries, borderColor: "rgba(27,152,224,0.25)", fill: false, pointRadius: 0, borderWidth: 1 },
          { label: "Historical rate ($/t)", data: histSeries, borderColor: "#52606d", backgroundColor: "#52606d", fill: false, tension: 0.2, pointRadius: 2, borderWidth: 2 },
          { label: "Forecast rate ($/t)", data: predSeries, borderColor: "#0d3b66", backgroundColor: "#0d3b66", fill: false, tension: 0.2, pointRadius: 2, borderWidth: 2, borderDash: [6, 3] },
          { label: "Recommended entry", data: marker, borderColor: "#2a9d3c", backgroundColor: "#2a9d3c", pointRadius: 7, pointStyle: "rectRot", showLine: false },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: { title: { display: true, text: "Freight rate (USD / tonne)" } },
          x: { title: { display: true, text: "Week (history + 8-week forecast)" }, ticks: { maxRotation: 60, minRotation: 30, autoSkip: true, maxTicksLimit: 14 } },
        },
        plugins: {
          legend: { position: "bottom" },
          title: { display: true, text: "SYNTHETIC / DEMONSTRATION DATA - NOT REAL MARKET DATA" },
        },
      },
    });
  }

  // ---- Section 3: entry windows ----------------------------------------
  function renderEntry(rows) {
    const b = document.getElementById("entryBody");
    b.innerHTML = rows
      .map(function (e) {
        return (
          '<tr class="' + (e.recommended ? "row-best" : "") + '">' +
          "<td>" + esc(e.label) + (e.recommended ? ' <span class="badge badge-best">ENTER HERE</span>' : "") + "</td>" +
          '<td class="text-end">' + usd(e.expected_rate_usd_per_tonne) + "</td>" +
          '<td class="text-end">' + usd0(e.expected_total_cost_usd) + "</td>" +
          '<td class="text-end">' + usd(e.cost_per_tonne_usd) + "</td>" +
          '<td class="text-end">±' + Number(e.forecast_uncertainty_pct).toFixed(1) + "%</td>" +
          '<td><span class="risk-pill ' + levelClass(e.risk_level) + '">' + esc(e.risk_level) + "</span></td>" +
          "<td>" + (e.delivery_feasible ? '<span class="ok">&#10003;</span>' : '<span class="bad">&#10007;</span>') + "</td>" +
          "<td>" + (e.recommended ? "Recommended" : e.delivery_feasible ? "Feasible" : "Misses deadline") + "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  // ---- Section 4: vessels ---------------------------------------------
  function renderVessels(rows) {
    const b = document.getElementById("vesselBody");
    b.innerHTML = rows
      .map(function (v) {
        const verdictBadge =
          v.verdict === "BEST"
            ? '<span class="badge badge-best">BEST FEASIBLE</span>'
            : v.port_feasibility === "INFEASIBLE"
            ? '<span class="badge badge-infeasible">INFEASIBLE</span>'
            : '<span class="badge badge-feasible">Feasible</span>';
        const reasons = (v.infeasibility_reasons || []).length
          ? '<div class="small text-danger mt-1">' + v.infeasibility_reasons.map(esc).join("<br>") + "</div>"
          : "";
        return (
          '<tr class="' + (v.verdict === "BEST" ? "row-best" : v.port_feasibility === "INFEASIBLE" ? "row-infeasible" : "") + '">' +
          "<td>" + esc(v.vessel_type) + reasons + "</td>" +
          '<td class="text-end">' + int(v.capacity_tonnes) + "</td>" +
          '<td class="text-end">' + v.voyages_required + "</td>" +
          '<td class="text-end">' + Number(v.utilization_pct).toFixed(0) + "%</td>" +
          '<td class="text-end">' + usd(v.expected_freight_rate_usd_per_tonne) + "</td>" +
          '<td class="text-end">' + usd0(v.expected_total_cost_usd) + "</td>" +
          "<td>" + (v.port_feasibility === "FEASIBLE" ? '<span class="ok">FEASIBLE</span>' : '<span class="bad">INFEASIBLE</span>') + "</td>" +
          "<td>" + (v.delivery_feasible ? '<span class="ok">&#10003;</span>' : '<span class="bad">&#10007;</span>') + "</td>" +
          '<td><span class="risk-pill ' + levelClass(v.operational_risk) + '">' + esc(v.operational_risk) + "</span></td>" +
          "<td>" + verdictBadge + "</td>" +
          "</tr>"
        );
      })
      .join("");
    document.getElementById("vesselNote").textContent =
      "The recommended vessel is the lowest expected-cost class that is FEASIBLE at both ports and within the delivery window - not simply the cheapest $/tonne.";
  }

  // ---- Section 5: port feasibility -----------------------------------
  function renderChecks(containerId, chk) {
    const rows = (chk.checks || [])
      .map(
        (c) =>
          "<tr><td>" + esc(c.parameter) + "</td><td>" + esc(c.required) + "</td><td>" +
          esc(c.available) + "</td><td>" +
          (c.passed ? '<span class="ok">&#10003;</span>' : '<span class="bad">&#10007;</span>') +
          "</td></tr>"
      )
      .join("");
    document.getElementById(containerId).innerHTML =
      '<table class="table table-sm feas-table mb-2"><thead><tr><th>Parameter</th><th>Limit</th><th>Vessel</th><th>OK</th></tr></thead><tbody>' +
      rows + "</tbody></table>" +
      '<div class="badge ' + (chk.verdict === "FEASIBLE" ? "badge-feasible" : "badge-infeasible") + '">' +
      esc(chk.verdict) + "</div>" +
      ((chk.reasons || []).length
        ? '<ul class="small text-danger mt-2 mb-0">' + chk.reasons.map((r) => "<li>" + esc(r) + "</li>").join("") + "</ul>"
        : "");
  }
  function renderPortFeasibility(pf) {
    document.getElementById("originPortTitle").textContent =
      "Origin (load): " + pf.origin.port_name;
    document.getElementById("destPortTitle").textContent =
      "Destination (discharge): " + pf.destination.port_name;
    renderChecks("originChecks", pf.origin);
    renderChecks("destChecks", pf.destination);
    const box = document.getElementById("feasibilitySummary");
    box.className =
      "mt-3 p-3 rounded feasibility-summary " + (pf.overall === "FEASIBLE" ? "is-feasible" : "is-infeasible");
    box.innerHTML =
      "<strong>" + esc(pf.vessel_type) + " on this lane: " + esc(pf.overall) + "</strong>" +
      " &mdash; " + pf.number_of_voyages + " voyage(s), ~" + Number(pf.turnaround_days).toFixed(0) +
      "-day turnaround vs " + pf.delivery_deadline_days + "-day deadline " +
      "(load " + Number(pf.loading_days).toFixed(1) + "d, discharge " + Number(pf.discharge_days).toFixed(1) + "d)." +
      '<ul class="mb-0 mt-2 small">' + (pf.reasons || []).map((r) => "<li>" + esc(r) + "</li>").join("") + "</ul>";
  }

  // ---- Section 6: contracts ------------------------------------------
  function renderContracts(rows) {
    const b = document.getElementById("contractBody");
    b.innerHTML = rows
      .map(function (c) {
        return (
          '<tr class="' + (c.recommended ? "row-best" : "") + '">' +
          "<td>" + esc(c.strategy) + (c.recommended ? ' <span class="badge badge-best">RECOMMENDED</span>' : "") + "</td>" +
          "<td>" + esc(c.contract_duration) + "</td>" +
          '<td class="text-end">' + c.number_of_voyages + "</td>" +
          '<td class="text-end">' + usd(c.expected_freight_rate_usd_per_tonne) + "</td>" +
          '<td class="text-end">' + usd0(c.expected_total_cost_usd) + "</td>" +
          '<td class="text-end">' + (c.savings_vs_spot_usd >= 0 ? "" : "−") + usd0(Math.abs(c.savings_vs_spot_usd)) +
          " (" + Number(c.savings_vs_spot_pct).toFixed(1) + "%)</td>" +
          '<td><span class="risk-pill ' + levelClass(c.risk_level) + '">' + esc(c.risk_level) + "</span></td>" +
          "<td>" + (c.delivery_feasible ? '<span class="ok">&#10003;</span>' : '<span class="bad">&#10007;</span>') + "</td>" +
          "<td>" + (c.recommended ? "Recommended" : "Alternative") + "</td>" +
          "</tr>"
        );
      })
      .join("");
    document.getElementById("contractNote").textContent =
      "MVC is not assumed cheaper - each strategy is priced off the same forecast. The recommendation balances expected cost (0.6) and risk (0.4).";
  }

  // ---- Section 7: idle ---------------------------------------------------
  function renderIdle(idle) {
    const m = document.getElementById("idleMetrics");
    m.innerHTML = "";
    [
      ["Expected idle period", Number(idle.expected_idle_days).toFixed(0) + " days"],
      ["Vessel utilisation", Number(idle.utilization_pct).toFixed(0) + "%"],
      ["Next cargo opportunity", "~" + Number(idle.next_cargo_opportunity_days).toFixed(0) + " days"],
      ["Repositioning required", idle.repositioning_required ? "Yes" : "No"],
      ["Ballast exposure", int(idle.ballast_exposure_nm) + " nm"],
      ["Idle risk", '<span class="risk-pill ' + levelClass(idle.idle_risk) + '">' + esc(idle.idle_risk) + "</span>"],
    ].forEach((it) => m.appendChild(cell(it[0], it[1])));
    m.appendChild(cell("Alternative employment", esc(idle.alternative_employment)));
    document.getElementById("idleMitigation").textContent = idle.mitigation;
    document.getElementById("idleNote").textContent = idle.note;
  }

  // ---- Section 8: risk ------------------------------------------------
  function renderRisk(risk) {
    const badge = document.getElementById("overallRiskBadge");
    badge.textContent = "Overall: " + risk.overall_risk + " (" + risk.overall_score + ")";
    badge.className = "badge risk-pill " + levelClass(risk.overall_risk);

    document.getElementById("riskBody").innerHTML = (risk.components || [])
      .map(
        (c) =>
          "<tr><td>" + esc(c.name) + "</td>" +
          '<td><span class="risk-pill ' + levelClass(c.level) + '">' + esc(c.level) + "</span></td>" +
          '<td class="text-end">' + Number(c.score).toFixed(2) + "</td>" +
          "<td>" + esc(c.rationale) + "</td></tr>"
      )
      .join("");
    document.getElementById("riskMitigation").innerHTML = (risk.mitigation || [])
      .map((m) => "<li>" + esc(m) + "</li>")
      .join("");
    document.getElementById("riskNote").textContent = risk.note;
  }

  // ---- Section 9 + model details ---------------------------------------
  function renderExplanation(data) {
    document.getElementById("decisionReasons").innerHTML = (data.recommendation.reasons || [])
      .map((r) => "<li class=\"mb-1\">" + esc(r) + "</li>")
      .join("");
    document.getElementById("mdMethod").textContent = data.forecast.method;
    const rt = data.route_info;
    document.getElementById("mdLane").textContent =
      rt.route_id + ": " + rt.origin_country + " (" + rt.load_port + ") → " +
      rt.destination_port + " · " + rt.cargo_type + " · ~" +
      int(rt.approx_distance_nm) + " nm · " + rt.estimated_transit_days + " d transit · " +
      "ref rate " + usd(rt.reference_rate_usd_per_tonne) + "/t · " + rt.data_class;
    document.getElementById("mdTransparency").textContent = data.data_transparency_note;
    document.getElementById("mdDisclaimer").textContent = data.disclaimer;
  }

  function render(data) {
    // The note already opens with the key sentence; just bold that first sentence.
    var note = String(data.data_transparency_note || "");
    var dot = note.indexOf(". ");
    document.getElementById("disclaimerBanner").innerHTML =
      dot > 0
        ? "<strong>" + esc(note.slice(0, dot + 1)) + "</strong>" + esc(note.slice(dot + 1))
        : "<strong>" + esc(note) + "</strong>";
    renderHero(data.recommendation);
    renderScenario(data.request, data.route_info, data.generated_at);
    renderForecast(data.forecast, data.recommended_entry.week_index);
    renderEntry(data.entry_windows);
    renderVessels(data.vessel_options);
    renderPortFeasibility(data.port_feasibility);
    renderContracts(data.contract_strategies);
    renderIdle(data.idle_analysis);
    renderRisk(data.risk_analysis);
    renderExplanation(data);
    resultContent.classList.remove("d-none");
    noDataState.classList.add("d-none");
    loadError.classList.add("d-none");
  }

  async function load() {
    let raw = null;
    try {
      raw = sessionStorage.getItem("sih26006_forecast");
    } catch (_) {}
    if (raw) {
      try {
        render(JSON.parse(raw));
        return;
      } catch (_) {}
    }
    try {
      const res = await fetch("/api/last-forecast");
      if (res.ok) {
        render(await res.json());
        return;
      }
      if (res.status === 404) {
        noDataState.classList.remove("d-none");
        resultContent.classList.add("d-none");
        return;
      }
      throw new Error("HTTP " + res.status);
    } catch (err) {
      loadError.textContent = "Could not load the last decision: " + err.message;
      loadError.classList.remove("d-none");
      resultContent.classList.add("d-none");
    }
  }

  load();
})();
