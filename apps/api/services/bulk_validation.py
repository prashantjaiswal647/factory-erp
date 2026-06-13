"""
bulk_validation.py
==================
Shared service for generating detailed, row-by-row Excel validation reports.

Provides:
  - ValidationSeverity   – FATAL | WARNING | INFO
  - ValidationIssue      – single row/field problem with suggested_correction
  - BulkValidationReport – aggregated report with fatal/warnings/success counts

Public helpers:
  - classify_pydantic_error()   – parse a pydantic ValidationError into Issues
  - classify_row_error()        – parse a raw error string into an Issue
  - make_report()               – build the final serialisable dict
  - enrich_failed_rows()        – convert raw failed_rows list → Issues
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from fastapi.encoders import jsonable_encoder


# ─────────────────────────── severity ──────────────────────────────────────


class ValidationSeverity(str, Enum):
    FATAL = "fatal"      # row is rejected and NOT imported
    WARNING = "warning"  # row is imported with a default / correction applied
    INFO = "info"        # informational, import proceeds normally


# ─────────────────────────── issue dataclass ────────────────────────────────


@dataclass
class ValidationIssue:
    row: int | None         # 1-based spreadsheet row number (None = file-level)
    field: str              # column / field name that caused the problem
    error: str              # human-readable error message
    severity: ValidationSeverity
    suggested_correction: str | None = None
    sheet: str | None = None
    raw_value: Any = None   # the value that caused the problem (truncated)
    section: str | None = None
    action_type: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        # Truncate raw_value so it is always JSON-safe
        if self.raw_value is not None:
            d["raw_value"] = str(self.raw_value)[:120]
        return jsonable_encoder(d)


# ─────────────────────────── report dataclass ───────────────────────────────


@dataclass
class BulkValidationReport:
    fatal_issues: list[ValidationIssue] = field(default_factory=list)
    warning_issues: list[ValidationIssue] = field(default_factory=list)
    info_issues: list[ValidationIssue] = field(default_factory=list)
    successful_rows: int = 0
    total_rows_attempted: int = 0

    @property
    def has_fatal(self) -> bool:
        return bool(self.fatal_issues)

    def add(self, issue: ValidationIssue) -> None:
        if issue.severity == ValidationSeverity.FATAL:
            self.fatal_issues.append(issue)
        elif issue.severity == ValidationSeverity.WARNING:
            self.warning_issues.append(issue)
        else:
            self.info_issues.append(issue)

    def to_dict(self) -> dict:
        return jsonable_encoder({
            "fatal_count": len(self.fatal_issues),
            "warning_count": len(self.warning_issues),
            "info_count": len(self.info_issues),
            "successful_rows": self.successful_rows,
            "total_rows_attempted": self.total_rows_attempted,
            "fatal_errors": [i.to_dict() for i in self.fatal_issues],
            "warnings": [i.to_dict() for i in self.warning_issues],
            "info": [i.to_dict() for i in self.info_issues],
        })


# ─────────────────────────── field-level hints ──────────────────────────────

# Maps field names → (error_keyword_patterns → suggestion template)
_FIELD_SUGGESTIONS: dict[str, list[tuple[list[str], str]]] = {
    "name": [
        (["missing", "empty", "min_length", "required"], "Provide the worker's full name (e.g. 'Ravi Kumar')"),
    ],
    "mobile_number": [
        (["missing", "invalid", "10"], "Enter a 10-digit Indian mobile number (e.g. '9876543210')"),
    ],
    "machine_name": [
        (["missing", "empty", "min_length", "required"], "Provide a unique machine name (e.g. 'Hi-Speed Machine 1')"),
    ],
    "daily_wages": [
        (["negative", "ge=0", "less than"], "Enter a non-negative wage amount (e.g. 400)"),
        (["type", "decimal", "float"], "Enter a numeric wage (e.g. 400 or 400.50)"),
    ],
    "duty_hours": [
        (["negative", "ge=0", "less than"], "Enter positive duty hours (e.g. 8)"),
        (["type"], "Enter a numeric value for hours (e.g. 8)"),
    ],
    "mould_size_ml": [
        (["gt=0", "less than", "negative"], "Enter a positive integer for cup mould size in ml (e.g. 210)"),
        (["type", "integer"], "Enter a whole number for mould_size_ml (e.g. 210)"),
    ],
    "bottom_size_mm": [
        (["gt=0", "less than", "negative"], "Enter a positive integer for bottom size in mm (e.g. 65)"),
        (["type", "integer"], "Enter a whole number for bottom_size_mm (e.g. 65)"),
    ],
    "default_operating_speed": [
        (["negative", "ge=0", "less than"], "Enter a non-negative speed in cups/minute (e.g. 120)"),
    ],
    "target_output_per_shift": [
        (["negative", "ge=0"], "Enter a non-negative target output (e.g. 55000)"),
    ],
    "size_ml": [
        (["gt=0", "less than"], "Enter a positive integer for cup blank size in ml (e.g. 210)"),
        (["type", "integer"], "Enter a whole number (e.g. 210)"),
    ],
    "bottom_size_mm": [
        (["gt=0", "less than"], "Enter a positive bottom size in mm (e.g. 65)"),
    ],
    "used_for_cup_size_ml": [
        (["gt=0", "less than"], "Enter a positive cup size in ml (e.g. 210)"),
        (["integer", "comma"], "Use comma-separated integers for multiple sizes (e.g. '55,65,210')"),
    ],
    "product_size_ml": [
        (["gt=0", "less than"], "Enter a positive integer cup size in ml (e.g. 210)"),
    ],
    "box_type": [
        (["missing", "empty", "min_length", "required"], "Enter a box description (e.g. '210ml Box')"),
    ],
    "plastic_size_type": [
        (["missing", "empty", "min_length", "required"], "Enter a plastic size label (e.g. 'PP 210ml Sleeve')"),
    ],
    "material_name": [
        (["missing", "empty", "min_length", "required"], "Enter a material name (e.g. 'Cup Blank')"),
    ],
    "factory_name": [
        (["missing", "empty", "min_length", "required"], "Enter your factory name (e.g. 'Munshi Paper Cups')"),
    ],
    "gstin": [
        (["format", "length", "invalid"], "Enter a valid 15-character GSTIN (e.g. '07ABCDE1234F1Z5') or leave blank"),
    ],
    "pcs_per_packet": [
        (["gt=0", "less than", "zero"], "Enter a positive integer (e.g. 100). Minimum is 1."),
    ],
    "packets_per_box": [
        (["gt=0", "less than", "zero"], "Enter a positive integer (e.g. 10). Minimum is 1."),
    ],
}

# Header-level errors
_HEADER_SUGGESTIONS = {
    "missing_headers": "Download the latest template from the Download button and re-enter your data",
    "header mismatch": "Your column headers don't match the expected template. Download the template again.",
    "required worksheet is missing": "The workbook must contain all required sheets: Company Profile, Workers, Machines, Raw Materials, Finished Goods",
    "instruction row is required": "Row 1 must contain the instruction line (do not delete it)",
    "header row is missing": "Row 2 must contain column headers (do not delete them)",
    "missing section marker": "The Raw Materials sheet must include section labels (CUP BLANK, BOTTOM REEL, BOX PACKAGING, PP PLASTIC)",
}

_DUPLICATE_HINTS = {
    "worker": "Duplicate worker name – the existing worker will be updated instead of creating a new one",
    "machine": "Duplicate machine name – the existing machine will be updated",
    "customer": "Duplicate phone number – this customer already exists and will be skipped",
    "blank_stock": "Duplicate blank stock entry – existing stock record will be updated",
    "bottom_reel": "Duplicate bottom reel entry – existing stock record will be updated",
    "box_stock": "Duplicate box stock entry – existing record will be updated",
    "plastic_stock": "Duplicate plastic stock entry – existing record will be updated",
    "finished_goods": "Duplicate product/packaging profile – existing profile will be updated",
}


def _find_suggestion(field_name: str, error_text: str) -> str | None:
    """Lookup the suggestion for a given field + error combination."""
    error_lower = error_text.lower()
    for patterns, suggestion in _FIELD_SUGGESTIONS.get(field_name, []):
        if any(kw in error_lower for kw in patterns):
            return suggestion
    return None


def _severity_from_error(error_text: str) -> ValidationSeverity:
    """Classify a plain error string as FATAL or WARNING."""
    lower = error_text.lower()
    # Warnings: things we recover from automatically
    if any(kw in lower for kw in ["duplicate", "already exists", "updated", "skipped", "defaulted", "default applied"]):
        return ValidationSeverity.WARNING
    # Header problems are always fatal
    if any(kw in lower for kw in ["header", "worksheet", "instruction row", "section marker", "sheet"]):
        return ValidationSeverity.FATAL
    return ValidationSeverity.FATAL


# ─────────────────────────── pydantic error classifier ──────────────────────


def classify_pydantic_error(
    pydantic_error_str: str,
    row: int | None,
    sheet: str | None,
    row_values: dict | None = None,
) -> list[ValidationIssue]:
    """
    Convert the string representation of a pydantic ValidationError into
    one ValidationIssue per failing field.
    """
    issues: list[ValidationIssue] = []
    # Pydantic v2 error strings look like:
    # "1 validation error for WorkerBulkRow\nname\n  Field required [type=missing, ...]"
    # We parse them line-by-line.
    lines = pydantic_error_str.strip().splitlines()
    i = 0
    current_field = "unknown"
    while i < len(lines):
        line = lines[i].strip()
        # First line: "N validation error(s) for ModelName"
        if "validation error" in line.lower():
            i += 1
            continue
        # Second pattern: bare field name (no indentation)
        if line and not line.startswith(" ") and not line.startswith("[") and not line.startswith("Value"):
            current_field = line.split("\n")[0].strip().split(".")[0]
            i += 1
            continue
        # Third pattern: indented error message
        if line.startswith(" ") or line.lower().startswith("value"):
            error_text = line.strip().split(" [type=")[0].strip()
            if "valid integer" in error_text.lower() or "unable to parse" in error_text.lower():
                error_text = "Enter a whole number, for example 210 or 210 ml. / पूरा नंबर लिखें, जैसे 210 या 210 ml।"
            elif "field required" in error_text.lower():
                error_text = "This value is required. / यह जानकारी भरना जरूरी है।"
            elif "greater than" in error_text.lower():
                error_text = "Enter a value greater than zero. / शून्य से बड़ा नंबर लिखें।"
            raw_val = row_values.get(current_field) if row_values else None
            suggestion = _find_suggestion(current_field, error_text)
            issues.append(ValidationIssue(
                row=row,
                field=current_field,
                error=error_text,
                severity=ValidationSeverity.FATAL,
                suggested_correction=suggestion,
                sheet=sheet,
                raw_value=raw_val,
            ))
        i += 1

    if not issues:
        # Fallback: treat entire string as a single unknown-field error
        issues.append(ValidationIssue(
            row=row,
            field="unknown",
            error=(
                "Some values have an invalid type or are incomplete. / "
                "इस पंक्ति की कुछ जानकारी गलत प्रकार की या अधूरी है।"
            ),
            severity=ValidationSeverity.FATAL,
            suggested_correction="Check the row values match the template column types",
            sheet=sheet,
        ))
    return issues


# ─────────────────────────── raw error classifier ───────────────────────────


def classify_row_error(
    raw_error: dict,
    entity_type: str | None = None,
) -> list[ValidationIssue]:
    """
    Convert a raw failed_row dict (from validate_bulk_frame / read_standard_sheet)
    into one or more ValidationIssue objects.
    """
    sheet = raw_error.get("sheet")
    row = raw_error.get("row")
    error_text = str(raw_error.get("error", "Unknown error"))
    row_values = raw_error.get("values") or {}
    missing_headers = raw_error.get("missing_headers")
    explicit_severity = raw_error.get("severity")
    if explicit_severity in {severity.value for severity in ValidationSeverity}:
        return [ValidationIssue(
            row=row,
            field=str(raw_error.get("field") or "row"),
            error=error_text,
            severity=ValidationSeverity(explicit_severity),
            suggested_correction=raw_error.get("suggested_correction"),
            sheet=sheet,
            action_type=raw_error.get("action_type"),
        )]

    # ── header / file-level errors ──────────────────────────────────────────
    if missing_headers:
        suggestion = _HEADER_SUGGESTIONS["missing_headers"]
        return [ValidationIssue(
            row=row,
            field="headers",
            error=f"Missing required columns: {', '.join(missing_headers)}",
            severity=ValidationSeverity.FATAL,
            suggested_correction=suggestion,
            sheet=sheet,
        )]

    # ── check for well-known header messages ────────────────────────────────
    for keyword, suggestion in _HEADER_SUGGESTIONS.items():
        if keyword in error_text.lower():
            return [ValidationIssue(
                row=row,
                field="headers" if "header" in keyword else "sheet",
                error=error_text,
                severity=ValidationSeverity.FATAL,
                suggested_correction=suggestion,
                sheet=sheet,
            )]

    # ── pydantic-style multi-field error ────────────────────────────────────
    if "validation error" in error_text.lower():
        return classify_pydantic_error(error_text, row, sheet, row_values)

    # ── duplicate / warning ─────────────────────────────────────────────────
    severity = _severity_from_error(error_text)
    suggestion: str | None = None
    if severity == ValidationSeverity.WARNING and entity_type:
        suggestion = _DUPLICATE_HINTS.get(entity_type)

    # ── try to guess field from simple "FieldName: ..." pattern ─────────────
    guessed_field = "row"
    for col_name in _FIELD_SUGGESTIONS:
        if col_name.lower() in error_text.lower():
            guessed_field = col_name
            suggestion = suggestion or _find_suggestion(col_name, error_text)
            break

    return [ValidationIssue(
        row=row,
        field=guessed_field,
        error=error_text,
        severity=severity,
        suggested_correction=suggestion,
        sheet=sheet,
        raw_value=row_values.get(guessed_field) if guessed_field != "row" else None,
    )]


# ─────────────────────────── enrich helper ──────────────────────────────────


def enrich_failed_rows(
    failed_rows: list[dict],
    entity_type: str | None = None,
) -> list[ValidationIssue]:
    """
    Convert the existing `failed_rows` list (from validate_bulk_frame /
    read_standard_sheet) into a list of ValidationIssue objects.
    """
    issues: list[ValidationIssue] = []
    for raw_error in failed_rows:
        issues.extend(classify_row_error(raw_error, entity_type))
    return issues


# ─────────────────────────── report builder ─────────────────────────────────


def make_report(
    issues: list[ValidationIssue],
    successful_rows: int,
    total_rows_attempted: int,
) -> BulkValidationReport:
    """Aggregate issues into a BulkValidationReport."""
    report = BulkValidationReport(
        successful_rows=successful_rows,
        total_rows_attempted=total_rows_attempted,
    )
    for issue in issues:
        report.add(issue)
    return report


def make_customer_validation_issues(
    row_index: int,
    row_data: dict,
    reason: str,
) -> ValidationIssue:
    """
    Create a ValidationIssue for a skipped customer upload row.
    row_index is 0-based (we add 2 for header + 1-based offset).
    """
    spreadsheet_row = row_index + 2  # row 1 = header
    name_val = row_data.get("name") or row_data.get("customer_name") or row_data.get("customer name") or ""
    phone_val = (
        row_data.get("phone") or row_data.get("mobile") or
        row_data.get("phone_number") or row_data.get("phone number") or ""
    )

    if reason == "missing_name":
        return ValidationIssue(
            row=spreadsheet_row,
            field="name",
            error="Customer name is missing or empty",
            severity=ValidationSeverity.FATAL,
            suggested_correction="Fill in the customer's name (e.g. 'Ravi Traders')",
            sheet="Customers",
            raw_value=name_val or None,
        )
    if reason == "missing_phone":
        return ValidationIssue(
            row=spreadsheet_row,
            field="phone",
            error="Phone number is missing or empty",
            severity=ValidationSeverity.FATAL,
            suggested_correction="Enter a 10-digit mobile number (e.g. '9876543210')",
            sheet="Customers",
            raw_value=phone_val or None,
        )
    if reason == "invalid_phone":
        return ValidationIssue(
            row=spreadsheet_row,
            field="phone",
            error=f"Invalid phone number '{phone_val}' – could not extract 10 digits",
            severity=ValidationSeverity.FATAL,
            suggested_correction="Use a 10-digit Indian mobile number (e.g. '9876543210'). Country code prefix is fine.",
            sheet="Customers",
            raw_value=phone_val or None,
        )
    if reason == "duplicate":
        return ValidationIssue(
            row=spreadsheet_row,
            field="phone",
            error=f"Customer with phone '{phone_val}' already exists",
            severity=ValidationSeverity.WARNING,
            suggested_correction="This row will be skipped. To update the customer, edit them directly in the app.",
            sheet="Customers",
            raw_value=phone_val or None,
        )
    return ValidationIssue(
        row=spreadsheet_row,
        field="row",
        error=reason,
        severity=ValidationSeverity.FATAL,
        suggested_correction=None,
        sheet="Customers",
    )
