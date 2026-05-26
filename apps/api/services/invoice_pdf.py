from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _money(value: Any) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"Rs {amount}"


def _date_text(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value or "")


def build_invoice_pdf_bytes(payload: dict[str, Any]) -> bytes:
    invoice = payload.get("invoice") or {}
    items = payload.get("items") or []
    factory_id = payload.get("factory_id") or invoice.get("factory_id") or ""

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    invoice_number = invoice.get("invoice_id") or payload.get("invoice_number") or ""
    customer_name = invoice.get("customer_name") or payload.get("customer_name") or "-"
    customer_phone = invoice.get("customer_phone") or payload.get("customer_phone") or "-"
    payment_method = invoice.get("payment_method") or payload.get("payment_method") or "Cash"

    story = [
        Paragraph("Invoice", styles["Title"]),
        Spacer(1, 10),
        Paragraph(f"<b>Invoice No:</b> {invoice_number}", styles["Normal"]),
        Paragraph(f"<b>Date:</b> {_date_text(invoice.get('invoice_date') or payload.get('invoice_date'))}", styles["Normal"]),
        Paragraph(f"<b>Factory ID:</b> {factory_id}", styles["Normal"]),
        Spacer(1, 12),
        Paragraph(f"<b>Customer:</b> {customer_name}", styles["Normal"]),
        Paragraph(f"<b>Phone:</b> {customer_phone}", styles["Normal"]),
        Paragraph(f"<b>Payment Method:</b> {payment_method}", styles["Normal"]),
        Spacer(1, 16),
    ]

    rows = [["#", "Item", "Packaging", "Boxes", "Loose", "Rate/Box", "Total"]]
    for index, item in enumerate(items, start=1):
        product = f"{item.get('product_size_ml') or ''}ml {item.get('variety') or ''}".strip() or item.get("product_name") or f"Item {index}"
        rows.append(
            [
                str(index),
                str(product),
                str(item.get("packaging_size_name") or item.get("packaging") or ""),
                str(item.get("boxes_sold") or item.get("quantity") or 0),
                str(item.get("loose_packets_sold") or 0),
                _money(item.get("rate_per_box") or item.get("rate") or 0),
                _money(item.get("line_total") or item.get("total") or 0),
            ]
        )

    table = Table(rows, colWidths=[24, 120, 95, 50, 45, 75, 75])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    )
    story.extend([table, Spacer(1, 16)])

    summary_rows = [
        ["Bill Total", _money(invoice.get("bill_total") or payload.get("bill_total"))],
        ["Paid Amount", _money(invoice.get("amount_paid") or payload.get("amount_paid"))],
        ["Total Due", _money(invoice.get("customer_total_due") or payload.get("customer_total_due"))],
    ]
    summary = Table(summary_rows, colWidths=[160, 120], hAlign="RIGHT")
    summary.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary)

    document.build(story)
    return buffer.getvalue()
