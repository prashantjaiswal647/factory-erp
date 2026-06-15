from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import logging
import os
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from db import SessionLocal
from models import Factory, FactoryAuthorizedSignature

logger = logging.getLogger(__name__)
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "volumes/media"))
AUTHORIZED_SIGNATURE_ROOT = Path(
    os.getenv("AUTHORIZED_SIGNATURE_ROOT", str(MEDIA_ROOT / "factory_signatures"))
)
LEGACY_SIGNATURE_ROOT = Path(
    os.getenv("LEGACY_SIGNATURE_ROOT", str(MEDIA_ROOT / "signatures"))
)


def _normalized_role(role: str | None) -> str:
    value = (role or "owner").strip().lower().replace("-", "_").replace(" ", "_")
    return value if value in {"owner", "sub_owner", "supervisor"} else "owner"


def _safe_existing_signature_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    raw = str(value).strip().replace("\\", "/")
    if not raw:
        return None
    if raw.startswith("/media/"):
        candidate = MEDIA_ROOT / raw.removeprefix("/media/")
    else:
        stored = Path(raw)
        if stored.is_absolute():
            candidate = stored
        elif raw.startswith("volumes/media/"):
            candidate = Path(raw)
        elif raw.startswith("factory_signatures/") or raw.startswith("signatures/"):
            candidate = MEDIA_ROOT / raw
        else:
            candidate = AUTHORIZED_SIGNATURE_ROOT / raw

    try:
        resolved = candidate.resolve(strict=False)
        allowed_roots = (
            AUTHORIZED_SIGNATURE_ROOT.resolve(strict=False),
            LEGACY_SIGNATURE_ROOT.resolve(strict=False),
        )
        if not any(resolved.is_relative_to(root) for root in allowed_roots):
            return None
        return resolved if resolved.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None


def resolve_authorized_signature_path(
    db_or_factory,
    factory_id: int | None = None,
    generated_by_role: str | None = None,
) -> Path | None:
    """Resolve a role signature safely, with owner and legacy-field fallback."""
    if hasattr(db_or_factory, "query"):
        db = db_or_factory
        if factory_id is None:
            return None
        role = _normalized_role(generated_by_role)
        roles = [role] if role == "owner" else [role, "owner"]
        rows = (
            db.query(FactoryAuthorizedSignature)
            .filter(
                FactoryAuthorizedSignature.factory_id == int(factory_id),
                FactoryAuthorizedSignature.role.in_(roles),
            )
            .all()
        )
        by_role = {row.role: row for row in rows}
        for candidate_role in roles:
            row = by_role.get(candidate_role)
            path = _safe_existing_signature_path(row.file_path if row else None)
            if path is not None:
                logger.info(
                    "Invoice signature resolved: role=%s path=%s",
                    candidate_role,
                    path,
                )
                return path
            if row is not None:
                logger.warning(
                    "Invoice signature file missing: role=%s factory_id=%s stored_path=%s",
                    candidate_role,
                    factory_id,
                    row.file_path,
                )
        factory = db.query(Factory).filter(Factory.id == int(factory_id)).first()
    else:
        factory = db_or_factory

    if factory is None:
        return None
    for field in (
        "authorized_signature_path",
        "signature_path",
        "invoice_signature_path",
        "digital_signature_url",
    ):
        path = _safe_existing_signature_path(getattr(factory, field, None))
        if path is not None:
            logger.info("Invoice signature resolved: role=owner path=%s", path)
            return path
    logger.warning(
        "Invoice signature not available: role=%s factory_id=%s",
        _normalized_role(generated_by_role),
        factory_id,
    )
    return None


def number_to_words_in_words(num: float) -> str:
    """Converts a floating-point number into Indian Rupee format words."""
    num_str = f"{num:.2f}"
    parts = num_str.split(".")
    rupees = int(parts[0])
    paise = int(parts[1]) if len(parts) > 1 else 0
    
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    def convert_below_hundred(n: int) -> str:
        if n < 20:
            return ones[n]
        digit = n % 10
        return tens[n // 10] + (" " + ones[digit] if digit else "")
        
    def convert_below_thousand(n: int) -> str:
        if n < 100:
            return convert_below_hundred(n)
        h = n // 100
        rem = n % 100
        return ones[h] + " Hundred" + (" and " + convert_below_hundred(rem) if rem else "")
        
    def convert_to_words(n: int) -> str:
        if n == 0:
            return ""
        word = ""
        if n >= 10000000:
            word += convert_to_words(n // 10000000) + " Crore "
            n %= 10000000
        if n >= 100000:
            word += convert_to_words(n // 100000) + " Lakh "
            n %= 100000
        if n >= 1000:
            word += convert_below_thousand(n // 1000) + " Thousand "
            n %= 1000
        if n > 0:
            word += convert_below_thousand(n)
        return word.strip()
        
    if rupees == 0:
        word = "Zero Rupees"
    else:
        word = convert_to_words(rupees) + " Rupees"
        
    if paise > 0:
        word += " and " + convert_below_hundred(paise) + " Paise"
        
    return word + " Only"


def _money(value: Any) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"Rs {amount:,}"


def _date_text(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value or "")


def build_invoice_pdf_bytes(payload: dict[str, Any]) -> bytes:
    invoice = payload.get("invoice") or {}
    items = payload.get("items") or []
    factory_id = payload.get("factory_id") or invoice.get("factory_id") or ""
    payments_history = payload.get("payment_history") or []

    # Fetch Factory details from database
    factory_name = "Munshi AI Factory"
    factory_gst = ""
    factory_address = ""
    factory_place = ""
    signature_path: Path | None = None
    
    if factory_id:
        db = SessionLocal()
        try:
            factory = db.query(Factory).filter(Factory.id == int(factory_id)).first()
            if factory:
                factory_name = factory.factory_name or factory.name
                factory_gst = factory.gst_number or ""
                factory_address = factory.address or ""
                factory_place = factory.address_place or ""
                generated_by_role = (
                    invoice.get("generated_by_role")
                    or payload.get("generated_by_role")
                    or "Owner"
                )
                signature_path = resolve_authorized_signature_path(
                    db, int(factory_id), generated_by_role
                )
        except Exception:
            logger.warning("Error fetching factory details in PDF build", exc_info=True)
        finally:
            db.close()

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    # Dynamic Title
    invoice_type = invoice.get("invoice_type") or payload.get("legal_invoice_type") or "bill_of_supply"
    title_text = "TAX INVOICE" if invoice_type == "tax_invoice" else "BILL OF SUPPLY"
    is_cancelled = str(invoice.get("status") or "").lower() == "cancelled" or str(payload.get("status") or "").lower() == "cancelled"
    if is_cancelled:
        title_text = f"CANCELLED - {title_text}"

    # Premium styles
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#4C1D95"),  # Munshi AI premium purple
        alignment=1, # Center
    )
    
    meta_label_style = ParagraphStyle(
        "MetaLabel",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#374151")
    )
    
    meta_val_style = ParagraphStyle(
        "MetaVal",
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#1F2937")
    )

    company_title_style = ParagraphStyle(
        "CompanyTitle",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#111827")
    )

    company_text_style = ParagraphStyle(
        "CompanyText",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#4B5563")
    )

    invoice_number = invoice.get("invoice_id") or payload.get("invoice_number") or payload.get("document_policy", {}).get("legal_invoice_number") or ""
    customer_name = invoice.get("customer_name") or payload.get("customer_name") or "-"
    customer_phone = invoice.get("customer_phone") or payload.get("customer_phone") or "-"
    customer_place = invoice.get("customer_place") or "-"
    payment_method = invoice.get("payment_method") or payload.get("payment_method") or "Cash"

    story = [
        Paragraph(title_text, title_style),
        Spacer(1, 15),
    ]

    # Two column header: Left (Company Details), Right (Invoice Metadata)
    company_p = [
        Paragraph(f"<b>{factory_name}</b>", company_title_style),
        Spacer(1, 4),
        Paragraph(f"Address: {factory_address or 'Not Entered'}", company_text_style),
        Paragraph(f"Place: {factory_place or 'Not Entered'}", company_text_style),
        Paragraph(f"GSTIN: <b>{factory_gst or 'Not Entered'}</b>", company_text_style),
    ]
    
    invoice_date_val = _date_text(invoice.get('invoice_date') or payload.get('invoice_date'))
    meta_p = [
        Paragraph(f"<b>Invoice No:</b> #{invoice_number}", meta_label_style),
        Paragraph(f"<b>Date:</b> {invoice_date_val}", meta_val_style),
        Paragraph(f"<b>Payment Mode:</b> {payment_method}", meta_val_style),
        Spacer(1, 8),
        Paragraph("<b>Billed To:</b>", meta_label_style),
        Paragraph(f"{customer_name}", meta_val_style),
        Paragraph(f"Phone: {customer_phone}", meta_val_style),
        Paragraph(f"Place: {customer_place}", meta_val_style),
    ]

    header_table = Table([[company_p, meta_p]], colWidths=[270, 250])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([header_table, Spacer(1, 15)])

    # Items table columns
    rows = [["S.No.", "Description of Goods", "HSN Code", "Quantity", "Rate", "Total Amount"]]
    
    total_taxable_amount = Decimal("0.00")
    for index, item in enumerate(items, start=1):
        product_name = item.get("description") or item.get("product_name") or ""
        if not product_name:
            product_name = f"{item.get('product_size_ml') or ''}ml {item.get('variety') or ''}".strip()
            if item.get("packaging_size_name"):
                product_name += f" ({item.get('packaging_size_name')})"
        if not product_name:
            product_name = f"Goods Item {index}"

        hsn = item.get("hsn_code") or "4823" # Default HSN for Paper Cups
        qty = Decimal(str(item.get("boxes_sold") or item.get("quantity") or 0))
        rate = Decimal(str(item.get("rate_per_box") or item.get("rate") or 0))
        line_total = Decimal(str(item.get("line_total") or item.get("total") or (qty * rate)))
        total_taxable_amount += line_total

        rows.append(
            [
                str(index),
                str(product_name),
                str(hsn),
                f"{qty:g}",
                _money(rate),
                _money(line_total),
            ]
        )

    table = Table(rows, colWidths=[35, 230, 65, 55, 65, 70])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4C1D95")), # Premium purple
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (3, -1), "CENTER"),
                ("ALIGN", (4, 0), (5, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([table, Spacer(1, 15)])

    # Summary table + Words calculation
    # Summary table + Words calculation
    taxable_value = Decimal(str(payload.get("total_taxable_value") or total_taxable_amount))
    total_cgst = Decimal(str(payload.get("total_cgst") or 0))
    total_sgst = Decimal(str(payload.get("total_sgst") or 0))
    total_igst = Decimal(str(payload.get("total_igst") or 0))
    total_val_num = float(invoice.get("bill_total") or payload.get("bill_total") or (taxable_value + total_cgst + total_sgst + total_igst))

    # Check if we have opening/advance adjustment data in invoice
    has_opening_or_advance = (
        invoice.get("previous_due") is not None or
        invoice.get("advance_available") is not None or
        invoice.get("advance_adjusted") is not None
    )

    invoice_total = Decimal(str(
        payload.get("invoice_total")
        or invoice.get("bill_total")
        or payload.get("bill_total")
        or total_val_num
    )).quantize(Decimal("0.01"))
    total_paid_against_invoice = Decimal(str(
        payload.get("total_paid_against_invoice")
        if payload.get("total_paid_against_invoice") is not None
        else invoice.get("amount_paid") or payload.get("amount_paid") or 0
    )).quantize(Decimal("0.01"))
    remaining_balance = Decimal(str(
        payload.get("remaining_balance")
        if payload.get("remaining_balance") is not None
        else invoice.get("customer_total_due") or payload.get("customer_total_due") or 0
    )).quantize(Decimal("0.01"))
    if remaining_balance <= 0:
        payment_status = "Paid"
    elif total_paid_against_invoice > 0:
        payment_status = "Partial Paid"
    else:
        payment_status = "Unpaid"

    if has_opening_or_advance:
        rem_payable_val = float(invoice.get("remaining_payable") or total_val_num)
        amount_in_words = number_to_words_in_words(rem_payable_val)
    else:
        amount_in_words = number_to_words_in_words(total_val_num)

    summary_rows = [
        ["Subtotal / Taxable Value", _money(taxable_value)],
    ]
    if total_cgst > 0:
        summary_rows.append(["CGST", _money(total_cgst)])
    if total_sgst > 0:
        summary_rows.append(["SGST", _money(total_sgst)])
    if total_igst > 0:
        summary_rows.append(["IGST", _money(total_igst)])
    
    summary_rows.append(["Current Bill Amount", _money(total_val_num)])
    
    if has_opening_or_advance:
        prev_due = Decimal(str(invoice.get("previous_due") or 0))
        adv_avail = Decimal(str(invoice.get("advance_available") or 0))
        adv_adj = Decimal(str(invoice.get("advance_adjusted") or 0))
        tot_before = Decimal(str(invoice.get("total_before_advance") or (Decimal(total_val_num) + prev_due)))
        rem_pay = Decimal(str(invoice.get("remaining_payable") or (tot_before - adv_adj)))
        adv_rem = Decimal(str(invoice.get("advance_balance_remaining") or (adv_avail - adv_adj)))
        
        if prev_due > 0:
            summary_rows.append(["Previous Due", _money(prev_due)])
        if prev_due > 0 or adv_avail > 0:
            summary_rows.append(["Total Before Advance", _money(tot_before)])
        if adv_avail > 0:
            summary_rows.append(["Advance Available", _money(adv_avail)])
        if adv_adj > 0:
            summary_rows.append(["Advance Adjusted", _money(adv_adj)])
        
        summary_rows.append(["Remaining Payable", _money(rem_pay)])
        if adv_rem > 0:
            summary_rows.append(["Advance Balance Remaining", _money(adv_rem)])

    summary_rows.extend([
        ["Invoice Total", _money(invoice_total)],
        ["Total Paid Against This Invoice", _money(total_paid_against_invoice)],
        ["Remaining Balance", _money(remaining_balance)],
        ["Payment Status", payment_status],
    ])

    summary = Table(summary_rows, colWidths=[165, 95], hAlign="RIGHT")
    summary.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    
    # Left: Total in words, Right: Numeric Summary
    words_style = ParagraphStyle(
        "TotalInWords",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1F2937")
    )
    words_p = [
        Paragraph("<b>Total Amount in Words:</b>", words_style),
        Spacer(1, 4),
        Paragraph(amount_in_words, company_text_style),
        Spacer(1, 10),
        Paragraph("<b>Declaration:</b>", company_title_style),
        Paragraph("We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.", company_text_style)
    ]
    
    bottom_table = Table([[words_p, summary]], colWidths=[250, 270])
    bottom_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    
    story.extend([bottom_table, Spacer(1, 15)])

    notes = str(payload.get("notes") or "").strip()
    if notes:
        story.extend([
            Paragraph("<b>Notes</b>", company_title_style),
            Paragraph(notes, company_text_style),
            Spacer(1, 12),
        ])

    history_header = ParagraphStyle(
        "HistoryHeader",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#4C1D95")
    )
    story.append(Paragraph("<b>Payment History / Receipts</b>", history_header))
    story.append(Spacer(1, 4))

    if payments_history:
        history_rows = [[
            "Date", "Amount Paid", "Payment Mode", "Received By",
            "Note / Reference", "Remaining After Payment",
        ]]
        for payment in payments_history:
            history_rows.append([
                _date_text(payment.get("date")),
                _money(payment.get("amount_paid")),
                str(payment.get("payment_mode") or "-"),
                str(payment.get("received_by") or "-"),
                str(payment.get("note_reference") or "-"),
                _money(payment.get("remaining_after_payment")),
            ])

        history_table = Table(history_rows, colWidths=[62, 72, 68, 92, 130, 96], repeatRows=1)
        history_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#374151")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("PADDING", (0, 0), (-1, -1), 5),
                    ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                    ("ALIGN", (5, 1), (5, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(history_table)
        story.append(Spacer(1, 15))
    else:
        story.extend([
            Paragraph("No payment received against this invoice yet.", company_text_style),
            Spacer(1, 15),
        ])
    
    # Signatory line
    sig_style = ParagraphStyle(
        "SigText",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#374151"),
        alignment=2 # Right
    )
    sig_block = [
        Paragraph(f"For <b>{factory_name}</b>", sig_style),
        Paragraph("Digitally authorized" if signature_path else "", sig_style),
    ]
    if signature_path is not None:
        sig_block.extend([Spacer(1, 4), Image(str(signature_path), width=90, height=40, kind="proportional")])
    sig_block.extend([Spacer(1, 8 if signature_path else 30), Paragraph("Authorized Signatory", sig_style)])
    sig_table = Table([["", sig_block]], colWidths=[320, 200])
    sig_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("PADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(sig_table)

    document.build(story)
    return buffer.getvalue()


def build_accountant_summary_pdf(month: int, year: int, summary_data: dict[str, Any], invoices: list[Any]) -> bytes:
    """Generates a professional accountant-style monthly invoice ledger summary PDF."""
    
    factory_id = invoices[0].factory_id if invoices else ""
    factory_name = "Munshi AI Factory"
    factory_gst = ""
    factory_address = ""
    
    if factory_id:
        db = SessionLocal()
        try:
            factory = db.query(Factory).filter(Factory.id == int(factory_id)).first()
            if factory:
                factory_name = factory.factory_name or factory.name
                factory_gst = factory.gst_number or ""
                factory_address = factory.address or ""
        except Exception:
            logger.warning("Error fetching factory details in summary PDF", exc_info=True)
        finally:
            db.close()

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    month_name = datetime(year, month, 1).strftime("%B %Y")

    title_style = ParagraphStyle(
        "SummaryTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1E3A8A"), # Dark corporate blue
        alignment=1,
    )

    company_title_style = ParagraphStyle(
        "CompanyTitle",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=colors.HexColor("#111827")
    )

    company_text_style = ParagraphStyle(
        "CompanyText",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#4B5563")
    )

    story = [
        Paragraph("MONTHLY SALES INVOICE REGISTER", title_style),
        Paragraph(f"<b>Statement Period:</b> {month_name}", ParagraphStyle("SubText", alignment=1, fontSize=10, textColor=colors.HexColor("#4B5563"))),
        Spacer(1, 15),
    ]

    # Company & Summary Header Table
    company_block = [
        Paragraph(f"<b>{factory_name}</b>", company_title_style),
        Paragraph(f"Address: {factory_address or 'N/A'}", company_text_style),
        Paragraph(f"GSTIN: <b>{factory_gst or 'N/A'}</b>", company_text_style),
    ]
    
    summary_block = [
        Paragraph(f"<b>Total Invoices:</b> {summary_data['total_invoices']}", company_text_style),
        Paragraph(f"<b>Start Invoice Number:</b> #{summary_data.get('first_invoice_number') or 'N/A'}", company_text_style),
        Paragraph(f"<b>End Invoice Number:</b> #{summary_data['ending_invoice_number'] or 'N/A'}", company_text_style),
    ]

    header_table = Table([[company_block, summary_block]], colWidths=[320, 200])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([header_table, Spacer(1, 10)])

    # Ledger Columns
    rows = [["Invoice #", "Date", "Customer Name", "Billed Total", "Amount Paid", "Balance Due", "Status"]]
    
    total_billed = Decimal("0.00")
    total_paid = Decimal("0.00")
    total_due = Decimal("0.00")
    
    for inv in invoices:
        billed = Decimal(str(inv.bill_total or 0))
        paid = Decimal(str(inv.amount_paid or 0))
        due = Decimal(str(inv.customer_total_due or 0))
        
        total_billed += billed
        total_paid += paid
        total_due += due
        
        rows.append(
            [
                f"#{inv.invoice_number}",
                _date_text(inv.invoice_date),
                str(inv.customer_name),
                _money(billed),
                _money(paid),
                _money(due),
                str(inv.status or "created").upper(),
            ]
        )
        
    # Add Totals row
    rows.append(
        [
            "TOTALS",
            "",
            "",
            _money(total_billed),
            _money(total_paid),
            _money(total_due),
            "",
        ]
    )

    table = Table(rows, colWidths=[65, 60, 150, 70, 70, 70, 35])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")), # Deep Blue
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (1, -1), "CENTER"),
                ("ALIGN", (3, 0), (5, -1), "RIGHT"),
                ("ALIGN", (6, 0), (6, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e2e8f0")), # Totals row gray
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    
    story.extend([table, Spacer(1, 20)])
    
    # Signatures
    sig_style = ParagraphStyle(
        "SummarySig",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#4B5563")
    )
    sig_table = Table(
        [
            [Paragraph("Prepared By: ____________________", sig_style), Paragraph("Approved By: ____________________", sig_style)]
        ],
        colWidths=[260, 260]
    )
    sig_table.setStyle(
        TableStyle(
            [
                ("PADDING", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(sig_table)

    document.build(story)
    return buffer.getvalue()
