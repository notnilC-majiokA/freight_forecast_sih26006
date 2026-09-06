/* SIH26006 - home page form handling.
 * Validates the scenario form, POSTs it to /forecast, stashes the JSON
 * response in sessionStorage, then navigates to /results.
 */
(function () {
  "use strict";

  const form = document.getElementById("forecastForm");
  const submitBtn = document.getElementById("submitBtn");
  const spinner = document.getElementById("submitSpinner");
  const overlay = document.getElementById("loadingOverlay");
  const formError = document.getElementById("formError");

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    spinner.classList.toggle("d-none", !isLoading);
    overlay.classList.toggle("d-none", !isLoading);
  }

  function showError(message) {
    formError.textContent = message;
    formError.classList.remove("d-none");
  }

  function hideError() {
    formError.classList.add("d-none");
    formError.textContent = "";
  }

  function readForm() {
    return {
      cargo_type: document.getElementById("cargoType").value,
      quantity_tonnes: Number(document.getElementById("quantity").value),
      delivery_window_days: Number(document.getElementById("deliveryWindow").value),
      destination_port: document.getElementById("destinationPort").value,
      origin_region: document.getElementById("originRegion").value,
    };
  }

  // Populate the "feasible trade lanes" table from the route dataset.
  async function loadLanes() {
    const tbody = document.getElementById("feasibleLanes");
    if (!tbody) return;
    try {
      const res = await fetch("/api/options");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const lanes = data.feasible_lanes || [];
      if (lanes.length === 0) {
        tbody.innerHTML =
          '<tr><td colspan="8" class="text-muted">No route dataset loaded.</td></tr>';
        return;
      }
      tbody.innerHTML = lanes
        .map(function (l) {
          return (
            "<tr><td>" +
            (l.route_id || "-") +
            "</td><td>" +
            l.origin_region +
            "</td><td>" +
            l.load_port +
            "</td><td>" +
            l.destination_port +
            "</td><td>" +
            l.cargo_type +
            "</td><td>" +
            l.vessel_type +
            '</td><td class="text-end">' +
            Number(l.vessel_capacity_tonnes || 0).toLocaleString("en-US") +
            '</td><td class="text-end">' +
            (l.est_transit_days != null ? l.est_transit_days : "-") +
            "</td></tr>"
          );
        })
        .join("");
    } catch (err) {
      tbody.innerHTML =
        '<tr><td colspan="8" class="text-danger">Could not load trade lanes: ' +
        err.message +
        "</td></tr>";
    }
  }
  loadLanes();

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    event.stopPropagation();
    hideError();

    // Bootstrap-style client validation.
    form.classList.add("was-validated");
    if (!form.checkValidity()) {
      return;
    }

    const payload = readForm();
    setLoading(true);
    try {
      const res = await fetch("/forecast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let detail = "Request failed (HTTP " + res.status + ").";
        try {
          const errBody = await res.json();
          if (errBody && errBody.detail) {
            detail =
              typeof errBody.detail === "string"
                ? errBody.detail
                : JSON.stringify(errBody.detail);
          }
        } catch (_) {
          /* ignore body parse errors */
        }
        throw new Error(detail);
      }

      const data = await res.json();
      try {
        sessionStorage.setItem("sih26006_forecast", JSON.stringify(data));
      } catch (_) {
        /* sessionStorage may be unavailable; results page falls back to API */
      }
      window.location.href = "/results";
    } catch (err) {
      setLoading(false);
      showError(err.message || "Something went wrong. Please try again.");
    }
  });
})();
