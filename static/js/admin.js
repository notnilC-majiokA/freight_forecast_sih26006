/* SIH26006 - admin dashboard.
 * Fetches /api/admin/status and fills in the status cards + recent table.
 */
(function () {
  "use strict";

  const errorBox = document.getElementById("adminError");

  function setText(id, value) {
    document.getElementById(id).textContent = value;
  }

  function renderRecent(rows) {
    const body = document.getElementById("recentRequestsBody");
    body.innerHTML = "";
    if (!rows || rows.length === 0) {
      body.innerHTML =
        '<tr><td colspan="7" class="text-muted">No forecast requests recorded yet.</td></tr>';
      return;
    }
    rows.forEach(function (r) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" +
        r.id +
        "</td><td>" +
        String(r.created_at).slice(0, 16).replace("T", " ") +
        "</td><td>" +
        (r.cargo_type || "-") +
        '</td><td class="text-end">' +
        Number(r.quantity_tonnes || 0).toLocaleString("en-US") +
        '</td><td class="text-end">' +
        (r.delivery_window_days || "-") +
        "</td><td>" +
        (r.destination_port || "-") +
        "</td><td>" +
        (r.origin_region || "-") +
        "</td>";
      body.appendChild(tr);
    });
  }

  function renderDatasets(summary) {
    const wrap = document.getElementById("datasetSummary");
    if (!wrap) return;
    const entries = Object.keys(summary);
    if (!entries.length) {
      wrap.innerHTML = '<div class="col-12 text-muted small">No datasets reported.</div>';
      return;
    }
    wrap.innerHTML = entries
      .map(function (k) {
        return (
          '<div class="col-6 col-md-3"><div class="border rounded p-2">' +
          '<div class="text-muted small text-uppercase">' + k.replace(/_/g, " ") + "</div>" +
          '<div class="fw-semibold">' + Number(summary[k]).toLocaleString("en-US") + " rows</div>" +
          "</div></div>"
        );
      })
      .join("");
  }

  async function load() {
    errorBox.classList.add("d-none");
    try {
      const res = await fetch("/api/admin/status");
      if (!res.ok) {
        throw new Error("HTTP " + res.status);
      }
      const data = await res.json();
      setText("dataUpdated", data.data_last_updated
        ? String(data.data_last_updated).slice(0, 16).replace("T", " ") + " UTC"
        : "unknown");
      setText("routeCount", data.route_count);
      setText("requestCount", data.forecast_request_count);
      setText("modeBadge", data.demo_mode ? "DEMO" : "LIVE");
      renderDatasets(data.dataset_summary || {});
      renderRecent(data.recent_forecast_requests);
    } catch (err) {
      errorBox.textContent = "Could not load system status: " + err.message;
      errorBox.classList.remove("d-none");
    }
  }

  document.getElementById("refreshBtn").addEventListener("click", load);
  load();
})();
