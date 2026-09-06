/* SIH26006 - home page form handling.
 * Populates the scenario selects from /api/options, cascades the optional
 * origin-port list by country, POSTs the scenario to /forecast, stashes the
 * JSON in sessionStorage, then navigates to /results.
 */
(function () {
  "use strict";

  const form = document.getElementById("forecastForm");
  const submitBtn = document.getElementById("submitBtn");
  const spinner = document.getElementById("submitSpinner");
  const overlay = document.getElementById("loadingOverlay");
  const formError = document.getElementById("formError");
  let originPortsByCountry = {};

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

  function fillSelect(id, values, { keepPlaceholder = true } = {}) {
    const el = document.getElementById(id);
    if (!el) return;
    const first = keepPlaceholder && el.querySelector("option") ? el.querySelector("option").outerHTML : "";
    el.innerHTML =
      first +
      values.map((v) => '<option value="' + v + '">' + v + "</option>").join("");
  }

  function refreshOriginPorts() {
    const country = document.getElementById("originCountry").value;
    const list = document.getElementById("originPortList");
    const ports = originPortsByCountry[country] || [];
    list.innerHTML = ports.map((p) => '<option value="' + p + '"></option>').join("");
    document.getElementById("originPort").value = "";
  }

  function readForm() {
    const payload = {
      cargo_type: document.getElementById("cargoType").value,
      quantity_tonnes: Number(document.getElementById("quantity").value),
      origin_country: document.getElementById("originCountry").value,
      destination_port: document.getElementById("destinationPort").value,
      delivery_window_days: Number(document.getElementById("deliveryWindow").value),
      vessel_preference: document.getElementById("vesselPreference").value,
      contract_preference: document.getElementById("contractPreference").value,
    };
    const port = document.getElementById("originPort").value.trim();
    if (port) payload.origin_port = port;
    return payload;
  }

  async function loadOptions() {
    const tbody = document.getElementById("feasibleLanes");
    try {
      const res = await fetch("/api/options");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();

      fillSelect("cargoType", d.commodities || []);
      fillSelect("originCountry", d.origin_countries || []);
      fillSelect("destinationPort", d.destination_ports || []);
      fillSelect(
        "deliveryWindow",
        (d.delivery_windows || []).map((n) => String(n))
      );
      document.querySelectorAll("#deliveryWindow option").forEach((o) => {
        if (o.value && !o.disabled) o.textContent = "Within " + o.value + " days";
      });
      fillSelect("vesselPreference", d.vessel_preferences || [], { keepPlaceholder: false });
      document.getElementById("vesselPreference").value = "Optimize";
      fillSelect("contractPreference", d.contract_preferences || [], { keepPlaceholder: false });
      document.getElementById("contractPreference").value = "Compare All";

      originPortsByCountry = d.origin_ports_by_country || {};
      if (d.data_transparency_note) {
        // keep the static banner but ensure it matches the server text
        const notice = document.getElementById("dataNotice");
        if (notice) notice.title = d.data_transparency_note;
      }

      const lanes = d.feasible_lanes || [];
      tbody.innerHTML = lanes.length
        ? lanes
            .map(
              (l) =>
                "<tr><td>" +
                (l.route_id || "-") +
                "</td><td>" +
                l.origin_country +
                "</td><td>" +
                l.load_port +
                "</td><td>" +
                l.destination_port +
                "</td><td>" +
                l.cargo_type +
                '</td><td class="text-end">' +
                Number(l.approx_distance_nm || 0).toLocaleString("en-US") +
                '</td><td class="text-end">' +
                (l.est_transit_days != null ? l.est_transit_days : "-") +
                "</td></tr>"
            )
            .join("")
        : '<tr><td colspan="7" class="text-muted">No route dataset loaded.</td></tr>';
    } catch (err) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="text-danger">Could not load options: ' +
        err.message +
        "</td></tr>";
    }
  }

  document.getElementById("originCountry").addEventListener("change", refreshOriginPorts);

  document.getElementById("demoBtn").addEventListener("click", function () {
    document.getElementById("cargoType").value = "Coking Coal";
    document.getElementById("quantity").value = 120000;
    document.getElementById("originCountry").value = "Australia";
    refreshOriginPorts();
    document.getElementById("originPort").value = "Hay Point";
    document.getElementById("destinationPort").value = "Paradip";
    document.getElementById("deliveryWindow").value = "45";
    document.getElementById("vesselPreference").value = "Optimize";
    document.getElementById("contractPreference").value = "Compare All";
    hideError();
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    event.stopPropagation();
    hideError();
    form.classList.add("was-validated");
    if (!form.checkValidity()) return;

    setLoading(true);
    try {
      const res = await fetch("/forecast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readForm()),
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
        } catch (_) {}
        throw new Error(detail);
      }
      const data = await res.json();
      try {
        sessionStorage.setItem("sih26006_forecast", JSON.stringify(data));
      } catch (_) {}
      window.location.href = "/results";
    } catch (err) {
      setLoading(false);
      showError(err.message || "Something went wrong. Please try again.");
    }
  });

  loadOptions();
})();
