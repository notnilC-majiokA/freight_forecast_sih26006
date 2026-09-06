"""Export helpers - turn a :class:`ForecastResponse` into CSV text or a PDF.

Used by ``GET /export-csv`` and ``GET /export-pdf`` in ``main.py``. Both exports
carry the full decision: scenario, forecast, recommended entry window, vessel,
voyages, contract strategy, expected cost/savings, port feasibility, idle risk,
market risk, forecast confidence and the decision explanation.
"""
from __future__ import annotations

import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from schemas.forecast_schema import ForecastResponse


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def forecast_to_csv(response: ForecastResponse) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    req = response.request
    rec = response.recommendation
    entry = response.recommended_entry

    w.writerow(["# SIH26006 - Chartering Decision Export"])
    w.writerow(["# SYNTHETIC / DEMONSTRATION DATA - NOT REAL MARKET DATA"])
    w.writerow(["# " + response.data_transparency_note])
    w.writerow([])

    w.writerow(["Procurement scenario"])
    w.writerow(["commodity", req.cargo_type.value])
    w.writerow(["quantity_tonnes", req.quantity_tonnes])
    w.writerow(["origin_country", req.origin_country.value])
    w.writerow(["origin_port", response.route_info.load_port])
    w.writerow(["destination_port_east_coast_india", req.destination_port.value])
    w.writerow(["delivery_window_days", int(req.delivery_window_days.value)])
    w.writerow(["vessel_preference", req.vessel_preference.value])
    w.writerow(["contract_preference", req.contract_preference.value])
    w.writerow(["generated_at_utc", response.generated_at.isoformat()])
    w.writerow([])

    w.writerow(["Recommended chartering strategy"])
    w.writerow(["headline", rec.headline])
    w.writerow(["contract_strategy", rec.contract_strategy])
    w.writerow(["recommended_entry_window", rec.entry_week_range])
    w.writerow(["route", f"{rec.origin_country} ({rec.origin_port}) -> {rec.destination_port}"])
    w.writerow(["vessel_type", rec.vessel_type])
    w.writerow(["number_of_voyages", rec.number_of_voyages])
    w.writerow(["expected_freight_rate_usd_per_tonne", rec.expected_freight_rate_usd_per_tonne])
    w.writerow(["expected_total_cost_usd", rec.expected_total_cost_usd])
    w.writerow(["expected_savings_vs_spot_usd", rec.expected_savings_vs_spot_usd])
    w.writerow(["expected_savings_vs_spot_pct", rec.expected_savings_vs_spot_pct])
    w.writerow(["port_feasibility", rec.port_feasibility])
    w.writerow(["delivery_feasible", rec.delivery_feasible])
    w.writerow(["idle_risk", rec.idle_risk])
    w.writerow(["market_risk", rec.market_risk])
    w.writerow(["forecast_confidence", rec.forecast_confidence])
    for i, r in enumerate(rec.reasons, start=1):
        w.writerow([f"why_{i}", r])
    w.writerow([])

    w.writerow(["Freight-rate forecast (weekly, DEMO)"])
    fs = response.forecast
    w.writerow(["method", fs.method])
    w.writerow(["trend", fs.trend, "volatility_pct", fs.volatility_pct,
                "confidence", fs.confidence, "backtest_mape_pct", fs.backtest_mape_pct])
    w.writerow(["week", "week_start", "predicted_usd_per_tonne", "lower", "upper", "uncertainty_pct"])
    for p in fs.forecast:
        w.writerow([p.week_index, p.week_start.isoformat(), p.predicted_rate_usd_per_tonne,
                    p.lower_bound_usd_per_tonne, p.upper_bound_usd_per_tonne, p.uncertainty_pct])
    w.writerow([])

    w.writerow(["Market-entry timing"])
    w.writerow(["window", "week_start", "expected_rate", "expected_total_cost", "cost_per_tonne",
                "uncertainty_pct", "risk", "delivery_feasible", "recommended"])
    for e in response.entry_windows:
        w.writerow([e.label, e.week_start.isoformat(), e.expected_rate_usd_per_tonne,
                    e.expected_total_cost_usd, e.cost_per_tonne_usd, e.forecast_uncertainty_pct,
                    e.risk_level, e.delivery_feasible, e.recommended])
    w.writerow([])

    w.writerow(["Vessel comparison"])
    w.writerow(["vessel", "capacity_t", "voyages", "utilization_pct", "freight_usd_per_tonne",
                "total_cost_usd", "port_feasibility", "delivery_feasible", "operational_risk",
                "verdict"])
    for v in response.vessel_options:
        w.writerow([v.vessel_type, v.capacity_tonnes, v.voyages_required, v.utilization_pct,
                    v.expected_freight_rate_usd_per_tonne, v.expected_total_cost_usd,
                    v.port_feasibility, v.delivery_feasible, v.operational_risk, v.verdict])
    w.writerow([])

    w.writerow(["Contract strategy comparison"])
    w.writerow(["strategy", "duration", "vessel", "voyages", "rate_usd_per_tonne",
                "total_cost_usd", "utilization_pct", "savings_vs_spot_usd",
                "savings_vs_spot_pct", "risk", "feasible", "recommended"])
    for c in response.contract_strategies:
        w.writerow([c.strategy, c.contract_duration, c.vessel_type, c.number_of_voyages,
                    c.expected_freight_rate_usd_per_tonne, c.expected_total_cost_usd,
                    c.expected_utilization_pct, c.savings_vs_spot_usd, c.savings_vs_spot_pct,
                    c.risk_level, c.delivery_feasible, c.recommended])
    w.writerow([])

    idle = response.idle_analysis
    w.writerow(["Idle scenario"])
    w.writerow(["expected_idle_days", idle.expected_idle_days])
    w.writerow(["utilization_pct", idle.utilization_pct])
    w.writerow(["repositioning_required", idle.repositioning_required])
    w.writerow(["ballast_exposure_nm", idle.ballast_exposure_nm])
    w.writerow(["idle_risk", idle.idle_risk])
    w.writerow(["mitigation", idle.mitigation])
    w.writerow([])

    risk = response.risk_analysis
    w.writerow(["Risk analysis"])
    w.writerow(["overall_risk", risk.overall_risk, "overall_score", risk.overall_score])
    w.writerow(["component", "level", "score", "rationale"])
    for comp in risk.components:
        w.writerow([comp.name, comp.level, comp.score, comp.rationale])
    for i, m in enumerate(risk.mitigation, start=1):
        w.writerow([f"mitigation_{i}", m])
    w.writerow([])
    w.writerow(["# " + response.disclaimer])

    return buf.getvalue()


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def _kv(rows: list[list[str]]) -> Table:
    t = Table(rows, colWidths=[62 * mm, 108 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _grid(rows: list[list[str]]) -> Table:
    t = Table(rows, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d3b66")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def forecast_to_pdf(response: ForecastResponse) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title="SIH26006 Chartering Decision (DEMO)",
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    small = styles["Normal"].clone("small")
    small.fontSize = 8
    story: list = []
    req = response.request
    rec = response.recommendation
    fs = response.forecast

    story.append(Paragraph("Intelligent Freight Forecasting &amp; Vessel Chartering DSS", styles["Title"]))
    story.append(Paragraph("SIH26006 | Ministry of Steel | Smart India Hackathon 2026", styles["Heading3"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>SYNTHETIC / DEMONSTRATION DATA - NOT REAL MARKET DATA.</b> "
                           + response.data_transparency_note, small))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Recommended chartering strategy", styles["Heading2"]))
    story.append(Paragraph(rec.headline, styles["Normal"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_kv([
        ["Contract strategy", rec.contract_strategy],
        ["Recommended entry window", rec.entry_week_range],
        ["Route", f"{rec.origin_country} / {rec.origin_port}  ->  {rec.destination_port}"],
        ["Commodity", rec.cargo_type],
        ["Vessel / voyages", f"{rec.vessel_type} x {rec.number_of_voyages}"],
        ["Expected freight rate", f"${rec.expected_freight_rate_usd_per_tonne:,.2f} / tonne"],
        ["Expected total cost", f"${rec.expected_total_cost_usd:,.2f}"],
        ["Expected savings vs repeated spot",
         f"${rec.expected_savings_vs_spot_usd:,.0f}  ({rec.expected_savings_vs_spot_pct:.1f}%)"],
        ["Port feasibility", rec.port_feasibility],
        ["Delivery feasible", "Yes" if rec.delivery_feasible else "No"],
        ["Idle risk / Market risk", f"{rec.idle_risk} / {rec.market_risk}"],
        ["Forecast confidence", rec.forecast_confidence],
    ]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("<b>Why this is recommended</b>", styles["Normal"]))
    for i, r in enumerate(rec.reasons, start=1):
        story.append(Paragraph(f"{i}. {r}", small))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Freight-rate forecast (weekly, DEMO)", styles["Heading2"]))
    story.append(Paragraph(
        f"Method: {fs.method}. Trend: {fs.trend}; volatility {fs.volatility_pct:.1f}%; "
        f"confidence {fs.confidence}; backtest MAPE "
        f"{fs.backtest_mape_pct if fs.backtest_mape_pct is not None else 'n/a'}%.", small))
    fc_rows = [["Week", "Starts", "Predicted ($/t)", "Low", "High", "+/-%"]]
    for p in fs.forecast:
        fc_rows.append([str(p.week_index), p.week_start.isoformat(),
                        f"{p.predicted_rate_usd_per_tonne:,.2f}",
                        f"{p.lower_bound_usd_per_tonne:,.2f}",
                        f"{p.upper_bound_usd_per_tonne:,.2f}",
                        f"{p.uncertainty_pct:.1f}"])
    story.append(_grid(fc_rows))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Market-entry timing", styles["Heading2"]))
    et_rows = [["Window", "Rate ($/t)", "Total ($)", "$/t", "+/-%", "Risk", "Deliv.", "Rec."]]
    for e in response.entry_windows:
        et_rows.append([e.label, f"{e.expected_rate_usd_per_tonne:,.2f}",
                        f"{e.expected_total_cost_usd:,.0f}", f"{e.cost_per_tonne_usd:,.2f}",
                        f"{e.forecast_uncertainty_pct:.1f}", e.risk_level,
                        "Y" if e.delivery_feasible else "N", "*" if e.recommended else ""])
    story.append(_grid(et_rows))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Vessel comparison", styles["Heading2"]))
    v_rows = [["Vessel", "Cap. (t)", "Voy.", "Util.%", "$/t", "Total ($)", "Port feas.",
               "Deliv.", "Op. risk", "Verdict"]]
    for v in response.vessel_options:
        v_rows.append([v.vessel_type, f"{v.capacity_tonnes:,}", str(v.voyages_required),
                       f"{v.utilization_pct:.0f}", f"{v.expected_freight_rate_usd_per_tonne:,.2f}",
                       f"{v.expected_total_cost_usd:,.0f}", v.port_feasibility,
                       "Y" if v.delivery_feasible else "N", v.operational_risk, v.verdict])
    story.append(_grid(v_rows))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Contract strategy comparison", styles["Heading2"]))
    c_rows = [["Strategy", "Duration", "Voy.", "$/t", "Total ($)", "Sav. vs spot", "Risk",
               "Feas.", "Rec."]]
    for c in response.contract_strategies:
        c_rows.append([c.strategy, c.contract_duration, str(c.number_of_voyages),
                       f"{c.expected_freight_rate_usd_per_tonne:,.2f}",
                       f"{c.expected_total_cost_usd:,.0f}",
                       f"{c.savings_vs_spot_pct:.1f}%", c.risk_level,
                       "Y" if c.delivery_feasible else "N", "*" if c.recommended else ""])
    story.append(_grid(c_rows))
    story.append(Spacer(1, 4 * mm))

    idle = response.idle_analysis
    risk = response.risk_analysis
    story.append(Paragraph("Idle scenario &amp; risk", styles["Heading2"]))
    story.append(_kv([
        ["Expected idle days", f"{idle.expected_idle_days:.0f}"],
        ["Utilisation", f"{idle.utilization_pct:.0f}%"],
        ["Repositioning required", "Yes" if idle.repositioning_required else "No"],
        ["Idle risk", idle.idle_risk],
        ["Idle mitigation", idle.mitigation],
        ["Overall market risk", f"{risk.overall_risk} ({risk.overall_score})"],
    ]))
    story.append(Spacer(1, 2 * mm))
    r_rows = [["Risk component", "Level", "Score", "Rationale"]]
    for comp in risk.components:
        r_rows.append([comp.name, comp.level, f"{comp.score:.2f}", comp.rationale])
    story.append(_grid(r_rows))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("<b>Mitigation</b>", styles["Normal"]))
    for m in risk.mitigation:
        story.append(Paragraph("- " + m, small))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(response.disclaimer, small))

    doc.build(story)
    return buf.getvalue()
