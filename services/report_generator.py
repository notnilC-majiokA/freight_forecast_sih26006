"""Export helpers - turn a :class:`ForecastResponse` into CSV text or a PDF.

Used by ``GET /export-csv`` and ``GET /export-pdf`` in ``main.py``.
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
    """Render the scenario, recommended strategy and weekly curve as CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["# SIH26006 - Chartering Strategy Export"])
    writer.writerow(["# DEMO DATA - NOT REAL MARKET DATA"])
    writer.writerow(["# " + response.disclaimer])
    writer.writerow([])

    writer.writerow(["Procurement scenario"])
    req = response.request
    writer.writerow(["cargo_type", req.cargo_type.value])
    writer.writerow(["quantity_tonnes", req.quantity_tonnes])
    writer.writerow(["delivery_deadline_days", int(req.delivery_window_days.value)])
    writer.writerow(["destination_port_east_coast_india", req.destination_port.value])
    writer.writerow(["preferred_origin_region", req.origin_region.value])
    writer.writerow(["generated_at_utc", response.generated_at.isoformat()])
    writer.writerow([])

    writer.writerow(["Recommended chartering strategy"])
    rec = response.recommendation
    writer.writerow(["chartering_week", rec.chartering_week_index + 1])
    writer.writerow(["chartering_week_start", rec.chartering_week_start.isoformat()])
    writer.writerow(
        ["route", f"{rec.origin_region} ({rec.load_port}) -> {rec.destination_port}"]
    )
    writer.writerow(["vessel_type", rec.vessel_type])
    writer.writerow(["vessel_capacity_tonnes", rec.vessel_capacity_tonnes])
    writer.writerow(["number_of_voyages", rec.number_of_voyages])
    writer.writerow(["estimated_delivery_lead_days", rec.estimated_delivery_lead_days])
    writer.writerow(["within_delivery_window", rec.within_delivery_window])
    writer.writerow(
        ["expected_freight_rate_usd_per_tonne", rec.expected_freight_rate_usd_per_tonne]
    )
    writer.writerow(
        ["total_expected_freight_cost_usd", rec.total_expected_freight_cost_usd]
    )
    writer.writerow(
        ["expected_savings_vs_booking_now_usd", rec.expected_savings_vs_booking_now_usd]
    )
    writer.writerow(["forecast_confidence", f"{rec.confidence} ({rec.confidence_score})"])
    writer.writerow(["why_this_strategy", rec.justification])
    for i, note in enumerate(rec.feasibility_notes, start=1):
        writer.writerow([f"feasibility_note_{i}", note])
    writer.writerow([])

    writer.writerow(["Cost comparison"])
    writer.writerow(
        ["option", "rate_usd_per_tonne", "total_freight_cost_usd", "delta_vs_recommended_usd"]
    )
    for row in response.cost_comparison:
        writer.writerow(
            [
                row.label,
                row.freight_rate_usd_per_tonne,
                row.total_freight_cost_usd,
                row.delta_vs_recommended_usd,
            ]
        )
    writer.writerow([])

    writer.writerow(["Weekly freight-rate forecast (DEMO)"])
    writer.writerow(
        [
            "week",
            "week_start",
            "predicted_rate_usd_per_tonne",
            "lower_bound_usd_per_tonne",
            "upper_bound_usd_per_tonne",
        ]
    )
    for p in response.forecast:
        writer.writerow(
            [
                p.week_index + 1,
                p.week_start.isoformat(),
                p.predicted_rate_usd_per_tonne,
                p.lower_bound_usd_per_tonne,
                p.upper_bound_usd_per_tonne,
            ]
        )

    return buf.getvalue()


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def _kv_table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[62 * mm, 108 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _grid_table(rows: list[list[str]]) -> Table:
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d3b66")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f2f6fa")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def forecast_to_pdf(response: ForecastResponse) -> bytes:
    """Render a one/two-page procurement-decision PDF and return it as bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title="SIH26006 Chartering Strategy (DEMO)",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    story: list = []

    story.append(
        Paragraph(
            "Intelligent Freight Forecasting &amp; Vessel Chartering DSS", styles["Title"]
        )
    )
    story.append(
        Paragraph("SIH26006 | Ministry of Steel | Smart India Hackathon 2026", styles["Heading3"])
    )
    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            "<b>DEMO DATA - NOT REAL MARKET DATA.</b> " + response.disclaimer,
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 6 * mm))

    # Scenario summary
    story.append(Paragraph("Procurement scenario", styles["Heading2"]))
    req = response.request
    story.append(
        _kv_table(
            [
                ["Cargo type", req.cargo_type.value],
                ["Quantity (tonnes)", f"{req.quantity_tonnes:,.0f}"],
                ["Delivery deadline (days from today)", str(int(req.delivery_window_days.value))],
                ["Destination port (East Coast India)", req.destination_port.value],
                ["Preferred origin region", req.origin_region.value],
                ["Generated at (UTC)", response.generated_at.strftime("%Y-%m-%d %H:%M")],
            ]
        )
    )
    story.append(Spacer(1, 6 * mm))

    # Recommended strategy
    story.append(Paragraph("Recommended chartering strategy", styles["Heading2"]))
    rec = response.recommendation
    story.append(
        _kv_table(
            [
                [
                    "Charter during",
                    f"Week {rec.chartering_week_index + 1} (starts {rec.chartering_week_start.isoformat()})",
                ],
                ["Origin -> East Coast Indian port", f"{rec.origin_region} / {rec.load_port}  ->  {rec.destination_port}"],
                ["Recommended vessel type", f"{rec.vessel_type} (~{rec.vessel_capacity_tonnes:,} t)"],
                ["Number of voyages", str(rec.number_of_voyages)],
                ["Estimated delivery lead time", f"{rec.estimated_delivery_lead_days:.0f} days"],
                ["Within delivery deadline", "Yes" if rec.within_delivery_window else "No"],
                ["Expected freight rate", f"${rec.expected_freight_rate_usd_per_tonne:,.2f} / tonne"],
                ["Expected freight cost", f"${rec.total_expected_freight_cost_usd:,.2f}"],
                ["Expected savings vs booking now", f"${rec.expected_savings_vs_booking_now_usd:,.2f}"],
                ["Forecast confidence", f"{rec.confidence} ({rec.confidence_score})"],
            ]
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>Why this strategy</b>", styles["Normal"]))
    story.append(Paragraph(rec.justification, styles["Normal"]))
    if rec.feasibility_notes:
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                "Feasibility checks: " + " ".join("- " + n for n in rec.feasibility_notes),
                styles["Normal"],
            )
        )
    story.append(Spacer(1, 6 * mm))

    # Cost comparison
    story.append(Paragraph("Cost comparison", styles["Heading2"]))
    cost_rows = [["Option", "Rate ($/t)", "Total cost ($)", "Delta vs rec ($)"]]
    for row in response.cost_comparison:
        cost_rows.append(
            [
                row.label,
                f"{row.freight_rate_usd_per_tonne:,.2f}",
                f"{row.total_freight_cost_usd:,.2f}",
                f"{row.delta_vs_recommended_usd:,.2f}",
            ]
        )
    story.append(_grid_table(cost_rows))
    story.append(Spacer(1, 6 * mm))

    # Weekly forecast
    story.append(Paragraph("Weekly freight-rate forecast (DEMO)", styles["Heading2"]))
    fc_rows = [["Week", "Starts", "Predicted ($/t)", "Low ($/t)", "High ($/t)"]]
    for p in response.forecast:
        fc_rows.append(
            [
                str(p.week_index + 1),
                p.week_start.isoformat(),
                f"{p.predicted_rate_usd_per_tonne:,.2f}",
                f"{p.lower_bound_usd_per_tonne:,.2f}",
                f"{p.upper_bound_usd_per_tonne:,.2f}",
            ]
        )
    story.append(_grid_table(fc_rows))

    doc.build(story)
    return buf.getvalue()
