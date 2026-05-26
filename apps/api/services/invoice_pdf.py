from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from db import SessionLocal
from models import Factory


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

    # Fetch Factory details from database
    factory_name = "Munshi AI Factory"
    factory_gst = ""
    factory_address = ""
    factory_place = ""
    
    if factory_id:
        db = SessionLocal()
        try:
            factory = db.query(Factory).filter(Factory.id == int(factory_id)).first()
            if factory:
                factory_name = factory.factory_name or factory.name
                factory_gst = factory.gst_number or ""
                factory_address = factory.address or ""
                factory_place = factory.address_place or ""
        except Exception as e:
            print(f"Error fetching factory details in PDF build: {e}")
        finally:
            db.close()

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    # Dynamic Title
    invoice_type = invoice.get("invoice_type") or payload.get("legal_invoice_type") or "bill_of_supply"
    title_text = "TAX INVOICE" if invoice_type == "tax_invoice" else "BILL OF SUPPLY"

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
    total_val_num = float(invoice.get("bill_total") or payload.get("bill_total") or total_taxable_amount)
    amount_in_words = number_to_words_in_words(total_val_num)

    summary_rows = [
        ["Total Taxable Amount", _money(total_val_num)],
        ["Amount Paid / Advance", _money(invoice.get("amount_paid") or payload.get("amount_paid") or 0)],
        ["Balance Due Amount", _money(invoice.get("customer_total_due") or payload.get("customer_total_due") or 0)],
    ]
    summary = Table(summary_rows, colWidths=[160, 100], hAlign="RIGHT")
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
    
    story.extend([bottom_table, Spacer(1, 35)])
    
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
        Spacer(1, 40),
        Paragraph("Authorized Signatory", sig_style),
    ]
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
        except Exception as e:
            print(f"Error fetching factory details in summary PDF: {e}")
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
        Paragraph(f"<b>Start Invoice Number:</b> #{summary_data['starting_invoice_number'] or 'N/A'}", company_text_style),
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
