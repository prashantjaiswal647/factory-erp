import logging
import re
from pathlib import Path
from uuid import uuid4
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, status, BackgroundTasks, UploadFile
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.responses import StreamingResponse
from sqlalchemy import func as sql_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import assert_owner_delete_permission, normalize_phone_number, require_owner, require_owner_delete
from dependencies import FACTORY_VIEW_ROLES, OWNER_ROLES, check_permissions
from db import get_db
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    CostingMaster,
    Customer,
    Factory,
    FactorySettings,
    FinalProductStock,
    FinishedGoodsStock,
    Inventory,
    Machine,
    MaterialYield,
    PackagingProfile,
    RawMaterial,
    RawMaterialMetrics,
    PackagingMetrics,
    PlasticStock,
    User,
    Worker,
    WorkerOpeningAttendance,
    OutstandingBill,
)
from schemas import (
    CustomerPayload,
    MachinePayload,
    MaterialYieldPayload,
    OnboardingCompleteRequest,
    OnboardingCompleteResponse,
    PackagingProfilePayload,
    RawMaterialPayload,
    Step1Request,
    Step1Response,
    Step2MachineItem,
    Step2Request,
    Step2Response,
    Step3PackagingMetricItem,
    Step3RawMaterialMetricItem,
    Step3Request,
    Step3Response,
    BoxStockCreate,
    PlasticStockCreate,
    WorkerCreate,
    WorkerPayload,
    FactoryProfileUpdate,
    FactoryProfileResponse,
    WorkerResponse,
)
from routers.operations import log_factory_operation
from services.activity_logger import log_activity
from services.n8n_sync import sync_data_to_n8n_bg
from services.bulk_validation import (
    BulkValidationReport,
    ValidationIssue,
    ValidationSeverity,
    enrich_failed_rows,
    make_report,
)
from services.accounting import create_outstanding_bill
from subscription_limits import check_machine_limit, get_machine_limit_usage

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
v1_router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)

BULK_TEMPLATE_COLUMNS = {
    "company_profile": ["row_type", "factory_name", "gstin", "factory_address", "invoice_prefix", "advance_upi_discount", "bill_of_supply_start_seq", "tax_invoice_start_seq", "bill_of_supply_simple_start_seq"],
    "worker": ["row_type", "name", "mobile_number", "daily_wages", "duty_hours", "previous_attendance_details"],
    "customer": ["row_type", "name", "firm_name", "contact_number", "phone_number", "place", "address", "gst_number", "previous_due", "advance_balance"],
    "machine": ["row_type", "machine_name", "default_operating_speed", "target_output_per_shift", "mould_size_ml", "bottom_size_mm"],
    "blank_stock": ["row_type", "material_name", "size_ml", "kg_per_sack", "total_boras_sacks"],
    "bottom_reel": ["row_type", "bottom_size_mm", "total_individual_rolls", "total_weight_kg"],
    "box_stock": ["row_type", "box_type", "box_quantity_pieces", "price_per_box_rs"],
    "plastic_stock": ["row_type", "plastic_size_type", "used_for_cup_size_ml", "total_boras_sacks", "weight_per_bora_kg", "price_per_kg_rs"],
    "finished_goods": ["row_type", "product_size_ml", "variety_design", "packaging_size_name", "pcs_per_packet", "packets_per_box", "initial_stock_boxes"],
}

BULK_MASTER_SHEETS = {
    "Company Profile": "company_profile",
    "Workers": "worker",
    "Customers": "customer",
    "Machines": "machine",
    "Raw Materials": "raw_materials",
    "Finished Goods": "finished_goods",
}

RAW_MATERIAL_SECTIONS = {
    "blank_stock": {"label_row": 1, "header_row": 2, "data_start": 3, "data_end": 15, "title": "SECTION A: CUP BLANK MATERIAL", "marker": "CUP BLANK"},
    "bottom_reel": {"label_row": 17, "header_row": 18, "data_start": 19, "data_end": 35, "title": "SECTION B: BOTTOM REEL MATERIAL", "marker": "BOTTOM REEL"},
    "box_stock": {"label_row": 37, "header_row": 38, "data_start": 39, "data_end": 55, "title": "SECTION C: BOX PACKAGING STOCK", "marker": "BOX PACKAGING"},
    "plastic_stock": {"label_row": 57, "header_row": 58, "data_start": 59, "data_end": 80, "title": "SECTION D: PP PLASTIC PACKAGING STOCK", "marker": "PP PLASTIC"},
}

MASTER_ONBOARDING_FILENAME = "master_onboarding_bulk_upload.xlsx"
TEXT_BULK_COLUMNS = {
    "row_type",
    "factory_name",
    "gstin",
    "factory_address",
    "invoice_prefix",
    "name",
    "mobile_number",
    "firm_name",
    "contact_number",
    "phone_number",
    "place",
    "address",
    "gst_number",
    "machine_name",
    "material_name",
    "box_type",
    "plastic_size_type",
    "variety_design",
    "packaging_size_name",
}

HEADER_ALIASES = {
    "customer_name": "name",
    "phone": "phone_number",
    "total_weight": "total_weight_automatic_calculation",
    "total_weight_kg_automatic_calculation": "total_weight_kg",
    "total_weight_kg=": "total_weight_kg",
    "total_weight=": "total_weight_automatic_calculation",
    "kg_per_sack=": "kg_per_sack",
    "quantity_of_total_bora": "total_boras_sacks",
    "quantity of total bora": "total_boras_sacks",
    "total_plastic_kg": "total_plastic_kg_automatic_calculation",
    "total_plastic_kg=": "total_plastic_kg_automatic_calculation",
}

OPTIONAL_BULK_HEADERS = {
    "customer": {
        "firm_name",
        "contact_number",
        "place",
        "gst_number",
        "previous_due",
        "advance_balance",
    },
    "blank_stock": {"total_boras_sacks"},
}

BULK_NUMERIC_DEFAULTS = {
    "worker": {
        "daily_wages": Decimal("0"),
        "duty_hours": Decimal("8"),
        "previous_attendance_details": Decimal("0"),
    },
    "customer": {
        "previous_due": Decimal("0"),
        "advance_balance": Decimal("0"),
    },
    "blank_stock": {
        "kg_per_sack": Decimal("0"),
        "total_boras_sacks": Decimal("0"),
    },
    "bottom_reel": {
        "total_individual_rolls": Decimal("0"),
        "total_weight_kg": Decimal("0"),
    },
    "box_stock": {
        "box_quantity_pieces": Decimal("0"),
        "price_per_box_rs": Decimal("0"),
    },
    "plastic_stock": {
        "total_boras_sacks": Decimal("0"),
        "weight_per_bora_kg": Decimal("0"),
        "price_per_kg_rs": Decimal("0"),
    },
    "finished_goods": {
        "pcs_per_packet": Decimal("1"),
        "packets_per_box": Decimal("1"),
        "initial_stock_boxes": Decimal("0"),
    },
}

SAMPLE_BULK_ROWS = {
    "company_profile": ["SAMPLE", "Munshi Demo Factory", "07ABCDE1234F1Z5", "Wazirpur Industrial Area, Delhi", "INV-", 2, 1, 1, 1],
    "worker": ["SAMPLE", "Akash Kumar", "82858117277", 400, 8, 0],
    "customer": ["SAMPLE", "Rajesh Kumar", "Rajesh Traders", "9876543210", "9876543210", "Delhi", "Wazirpur Industrial Area, Delhi", "07ABCDE1234F1Z5", 1500],
    "machine": ["SAMPLE", "Hi-Speed Cup Machine X", 120, 55000, 210, 68],
    "blank_stock": ["SAMPLE", "Cup Blank", 210, 20, 25],
    "bottom_reel": ["SAMPLE", 68, 1200, 180],
    "box_stock": ["SAMPLE", "210ml Box", 500, 18],
    "plastic_stock": ["SAMPLE", "PP 210ml Sleeve", 210, 25, 20, 145],
    "finished_goods": ["SAMPLE", 210, "Standard/White", "", 100, 10, 50],
}


class CompanyProfileBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    factory_name: str = Field(..., min_length=1, max_length=255)
    gstin: Optional[str] = Field(default=None, max_length=50)
    factory_address: Optional[str] = Field(default=None, max_length=500)
    invoice_prefix: Optional[str] = Field(default="INV-", max_length=50)
    advance_upi_discount: Decimal = Field(default=Decimal("2.00"), ge=0, le=100)
    bill_of_supply_start_seq: int = Field(default=1, ge=1)
    tax_invoice_start_seq: int = Field(default=1, ge=1)
    bill_of_supply_simple_start_seq: int = Field(default=1, ge=1)


class WorkerBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    name: str = Field(..., min_length=1, max_length=255)
    mobile_number: Optional[str] = Field(default=None, max_length=50)
    daily_wages: Decimal = Field(default=Decimal("0"), ge=0)
    duty_hours: Decimal = Field(default=Decimal("8"), ge=0)
    previous_attendance_details: Decimal = Field(default=Decimal("0"), ge=0)


class CustomerBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    name: str = Field(..., min_length=1, max_length=255)
    firm_name: Optional[str] = Field(default=None, max_length=255)
    contact_number: Optional[str] = Field(default=None, max_length=50)
    phone_number: Optional[str] = Field(default=None, max_length=50)
    place: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    gst_number: Optional[str] = Field(default=None, max_length=50)
    previous_due: Decimal = Field(default=Decimal("0"))
    advance_balance: Decimal = Field(default=Decimal("0"))

    @model_validator(mode="before")
    @classmethod
    def validate_customer_bulk(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Check previous_due
            pd = data.get("previous_due")
            if pd == "" or pd is None:
                data["previous_due"] = Decimal("0")
            else:
                try:
                    pd_val = Decimal(str(pd))
                    if pd_val < 0:
                        raise ValueError("Opening outstanding cannot be negative.")
                except (ValueError, TypeError):
                    raise ValueError("Opening outstanding cannot be negative.")
            # Check advance_balance
            ab = data.get("advance_balance")
            if ab == "" or ab is None:
                data["advance_balance"] = Decimal("0")
            else:
                try:
                    ab_val = Decimal(str(ab))
                    if ab_val < 0:
                        raise ValueError("Advance balance cannot be negative.")
                except (ValueError, TypeError):
                    raise ValueError("Advance balance cannot be negative.")
        return data


class MachineBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    machine_name: str = Field(..., min_length=1, max_length=255)
    default_operating_speed: int = Field(default=0, ge=0)
    target_output_per_shift: int = Field(default=0, ge=0)
    mould_size_ml: Optional[int] = Field(default=None, gt=0)
    bottom_size_mm: Optional[int] = Field(default=None, gt=0)


class BlankStockBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    material_name: str = Field(..., min_length=1, max_length=255)
    size_ml: int = Field(..., gt=0)
    kg_per_sack: Decimal = Field(default=Decimal("0"), ge=0)
    total_boras_sacks: Decimal = Field(default=Decimal("0"), ge=0)


class BottomReelBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    bottom_size_mm: int = Field(..., gt=0)
    total_individual_rolls: int = Field(default=0, ge=0)
    total_weight_kg: Decimal = Field(default=Decimal("0"), ge=0)


class BoxStockBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    box_type: str = Field(..., min_length=1, max_length=100)
    box_quantity_pieces: int = Field(default=0, ge=0)
    price_per_box_rs: float = Field(default=0, ge=0)


class PlasticStockBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    plastic_size_type: str = Field(..., min_length=1, max_length=100)
    used_for_cup_size_ml: int = Field(..., gt=0)
    total_boras_sacks: int = Field(default=0, ge=0)
    weight_per_bora_kg: float = Field(default=0, ge=0)
    price_per_kg_rs: float = Field(default=0, ge=0)


class FinishedGoodsBulkRow(BaseModel):
    row_type: str = Field(..., max_length=20)
    product_size_ml: int = Field(..., gt=0)
    variety_design: str = Field(default="Standard/White", max_length=100)
    packaging_size_name: Optional[str] = Field(default=None, max_length=100)
    pcs_per_packet: int = Field(default=1, gt=0)
    packets_per_box: int = Field(default=1, gt=0)
    initial_stock_boxes: int = Field(default=0, ge=0)


BULK_ROW_MODELS = {
    "company_profile": CompanyProfileBulkRow,
    "worker": WorkerBulkRow,
    "customer": CustomerBulkRow,
    "machine": MachineBulkRow,
    "blank_stock": BlankStockBulkRow,
    "bottom_reel": BottomReelBulkRow,
    "box_stock": BoxStockBulkRow,
    "plastic_stock": PlasticStockBulkRow,
    "finished_goods": FinishedGoodsBulkRow,
}


def get_or_create_factory_settings(db: Session, factory_id: int) -> FactorySettings:
    settings = (
        db.query(FactorySettings)
        .filter(FactorySettings.factory_id == int(factory_id))
        .with_for_update()
        .first()
    )
    if settings is None:
        settings = FactorySettings(factory_id=int(factory_id))
        db.add(settings)
        db.flush()
    return settings


def normalize_bulk_value(value):
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def bulk_str(value) -> str:
    value = normalize_bulk_value(value)
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_bulk_cell(key: str, value):
    value = normalize_bulk_value(value)
    if key in TEXT_BULK_COLUMNS:
        return bulk_str(value)
    return value


def is_blank_bulk_value(value) -> bool:
    value = normalize_bulk_value(value)
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def apply_bulk_numeric_defaults(sub_tab_type: str, row: dict) -> dict:
    for key, default_value in BULK_NUMERIC_DEFAULTS.get(sub_tab_type, {}).items():
        if is_blank_bulk_value(row.get(key)):
            row[key] = default_value
    return row


def coerce_excel_int_token(value) -> int:
    value = normalize_bulk_value(value)
    if value is None:
        raise ValueError("empty integer value")
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = bulk_str(value)
    if not text:
        raise ValueError("empty integer value")
    decimal_value = Decimal(text)
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError(f"{text} is not a whole number")
    return int(decimal_value)


def split_bulk_int_values(value) -> list[int]:
    value = normalize_bulk_value(value)
    if value is None:
        return []
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return [coerce_excel_int_token(value)]
    tokens = [token.strip() for token in re.split(r"[,;/|]+", bulk_str(value)) if token.strip()]
    return [coerce_excel_int_token(token) for token in tokens]


def expand_bulk_row_variants(sub_tab_type: str, row: dict) -> list[dict]:
    if sub_tab_type != "plastic_stock":
        return [row]
    cup_sizes = split_bulk_int_values(row.get("used_for_cup_size_ml"))
    if not cup_sizes:
        return [row]
    return [{**row, "used_for_cup_size_ml": cup_size} for cup_size in cup_sizes]


def canonical_bulk_header(value) -> str:
    header = bulk_str(value).lower()
    header = header.replace("\n", " ").replace("\r", " ").strip()
    header = " ".join(header.split())
    header = header.replace(" ", "_").replace("-", "_")
    header = header.rstrip("=:")
    return HEADER_ALIASES.get(header, header)


def canonicalize_bulk_frame(frame):
    canonical_columns: list[str] = []
    seen: set[str] = set()
    keep_indices: list[int] = []
    for index, column in enumerate(frame.columns.tolist()):
        canonical = canonical_bulk_header(column)
        if not canonical or canonical in seen:
            continue
        canonical_columns.append(canonical)
        seen.add(canonical)
        keep_indices.append(index)
    canonical_frame = frame.iloc[:, keep_indices].copy()
    canonical_frame.columns = canonical_columns
    return canonical_frame


def actual_rows_only(frame):
    row_type = frame.get("row_type")
    if row_type is None:
        return frame.iloc[0:0]
    mask = row_type.fillna("").astype(str).str.strip().str.upper() == "ACTUAL"
    return frame[mask]


def validate_bulk_frame(frame, sub_tab_type: str, sheet_name: str | None = None, row_offset: int = 2) -> tuple[list[dict], list[dict]]:
    expected = BULK_TEMPLATE_COLUMNS[sub_tab_type]
    frame = canonicalize_bulk_frame(frame)
    headers = [str(column).strip() for column in frame.columns.tolist()]
    optional_headers = OPTIONAL_BULK_HEADERS.get(sub_tab_type, set())
    missing_headers = [column for column in expected if column not in headers and column not in optional_headers]
    if missing_headers:
        return [], [{
            "sheet": sheet_name or sub_tab_type,
            "row": row_offset,
            "error": "Header mismatch",
            "expected_headers": expected,
            "received_headers": headers,
            "missing_headers": missing_headers,
        }]

    model = BULK_ROW_MODELS[sub_tab_type]
    valid_rows: list[dict] = []
    failed_rows: list[dict] = []
    if sub_tab_type == "worker" and "previous_attendance_details" in frame.columns:
        frame["previous_attendance_details"] = frame["previous_attendance_details"].fillna(0)
        frame.loc[frame["previous_attendance_details"].astype(str).str.strip() == "", "previous_attendance_details"] = 0
    actual_frame = actual_rows_only(frame)
    for index, raw_row in actual_frame.iterrows():
        row = apply_bulk_numeric_defaults(
            sub_tab_type,
            {key: normalize_bulk_cell(key, raw_row.get(key)) for key in expected},
        )
        try:
            for row_variant in expand_bulk_row_variants(sub_tab_type, row):
                validated_row = model.model_validate(row_variant).model_dump()
                if sub_tab_type == "blank_stock" and "total_boras_sacks" not in headers:
                    validated_row.pop("total_boras_sacks", None)
                validated_row["_row_number"] = int(index) + 1
                valid_rows.append(validated_row)
        except Exception as exc:
            failed_rows.append({"sheet": sheet_name or sub_tab_type, "row": int(index) + 1, "error": str(exc), "values": row})
    return valid_rows, failed_rows


def bulk_unique_key(sub_tab_type: str, row: dict) -> tuple:
    if sub_tab_type == "company_profile":
        return ("company_profile",)
    if sub_tab_type == "worker":
        return (bulk_str(row.get("name")).lower(),)
    if sub_tab_type == "customer":
        return (bulk_str(row.get("name")).lower(),)
    if sub_tab_type == "machine":
        return (bulk_str(row.get("machine_name")).lower(),)
    if sub_tab_type == "blank_stock":
        return (int(row["size_ml"]), bulk_str(row.get("material_name") or "Plain White").lower())
    if sub_tab_type == "bottom_reel":
        return (int(row["bottom_size_mm"]), "plain white")
    if sub_tab_type == "box_stock":
        return (bulk_str(row.get("box_type")).lower(),)
    if sub_tab_type == "plastic_stock":
        return (bulk_str(row.get("plastic_size_type")).lower(), int(row["used_for_cup_size_ml"]))
    if sub_tab_type == "finished_goods":
        product_size_ml = int(row["product_size_ml"])
        variety = bulk_str(row.get("variety_design") or "Standard/White").lower() or "standard/white"
        packaging_size_name = bulk_str(row.get("packaging_size_name"))
        if not packaging_size_name:
            packaging_size_name = f"{product_size_ml}ML - {row.get('variety_design') or 'Standard/White'}"
        return (product_size_ml, variety, packaging_size_name.lower())
    return tuple(sorted((key, str(value)) for key, value in row.items() if not key.startswith("_")))


def dedupe_valid_bulk_rows(valid_by_type: dict[str, list[dict]]) -> tuple[dict[str, list[dict]], list[ValidationIssue]]:
    deduped: dict[str, list[dict]] = {key: [] for key in valid_by_type}
    warnings: list[ValidationIssue] = []
    sheet_names = {sub_tab_type: sheet_name for sheet_name, sub_tab_type in BULK_MASTER_SHEETS.items()}
    sheet_names.update({
        "blank_stock": "Raw Materials",
        "bottom_reel": "Raw Materials",
        "box_stock": "Raw Materials",
        "plastic_stock": "Raw Materials",
    })

    for sub_tab_type, rows in valid_by_type.items():
        by_key: dict[tuple, dict] = {}
        for row in rows:
            key = bulk_unique_key(sub_tab_type, row)
            if key in by_key:
                previous_row = by_key[key]
                warnings.append(
                    ValidationIssue(
                        row=row.get("_row_number"),
                        field="row_type",
                        error="Duplicate row in uploaded workbook; the last matching ACTUAL row was used.",
                        severity=ValidationSeverity.WARNING,
                        suggested_correction="Keep only one ACTUAL row per unique item if you do not intend to override values.",
                        sheet=sheet_names.get(sub_tab_type, sub_tab_type),
                        raw_value=f"previous row {previous_row.get('_row_number')}",
                    )
                )
            by_key[key] = row
        deduped[sub_tab_type] = list(by_key.values())
    return deduped, warnings


def increment_bulk_stat(stats: dict[str, int] | None, key: str, value: int = 1) -> None:
    if stats is None:
        return
    stats[key] = int(stats.get(key, 0)) + value


def read_standard_sheet(workbook: dict, sheet_name: str, sub_tab_type: str) -> tuple[list[dict], list[dict]]:
    if sheet_name not in workbook:
        return [], [{"sheet": sheet_name, "row": None, "error": "Required worksheet is missing"}]
    raw_frame = workbook[sheet_name]
    instruction = bulk_str(raw_frame.iat[0, 0]) if not raw_frame.empty else ""
    if not instruction:
        return [], [{"sheet": sheet_name, "row": 1, "error": "Instruction row is required"}]
    if len(raw_frame.index) < 2:
        return [], [{"sheet": sheet_name, "row": 2, "error": "Header row is missing"}]
    headers = [canonical_bulk_header(value) for value in raw_frame.iloc[1].tolist()]
    frame = raw_frame.iloc[2:].copy()
    frame.columns = headers
    frame = frame.loc[:, [column for column in frame.columns if column]]
    return validate_bulk_frame(frame, sub_tab_type, sheet_name, row_offset=2)


def find_raw_section_label_rows(raw_frame) -> dict[str, int]:
    label_rows: dict[str, int] = {}
    for row_index in range(len(raw_frame.index)):
        row_text = " ".join(bulk_str(value) for value in raw_frame.iloc[row_index].tolist()).upper()
        if not row_text:
            continue
        for sub_tab_type, section in RAW_MATERIAL_SECTIONS.items():
            marker = str(section["marker"]).upper()
            if sub_tab_type not in label_rows and marker in row_text:
                label_rows[sub_tab_type] = row_index
    return label_rows


def read_raw_material_section(raw_frame, sub_tab_type: str) -> tuple[list[dict], list[dict]]:
    section = RAW_MATERIAL_SECTIONS[sub_tab_type]
    label_rows = find_raw_section_label_rows(raw_frame)
    if sub_tab_type not in label_rows:
        return [], [{"sheet": "Raw Materials", "row": None, "error": f"Missing section marker containing: {section['marker']}"}]

    sorted_label_rows = sorted(label_rows.values())
    label_index = label_rows[sub_tab_type]
    next_label_index = next((row for row in sorted_label_rows if row > label_index), len(raw_frame.index))
    header_index = label_index + 1
    start_index = header_index + 1
    end_index = next_label_index

    if len(raw_frame.index) <= header_index:
        return [], [{"sheet": "Raw Materials", "row": label_index + 2, "error": "Header row is missing"}]

    headers = [canonical_bulk_header(value) for value in raw_frame.iloc[header_index].tolist()]
    frame = raw_frame.iloc[start_index:end_index].copy()
    frame.columns = headers
    frame = frame.loc[:, [column for column in frame.columns if column]]
    return validate_bulk_frame(frame, sub_tab_type, "Raw Materials", row_offset=start_index)


def read_master_bulk_excel(file_bytes: bytes) -> tuple[dict[str, list[dict]], list[dict]]:
    try:
        import pandas as pd
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Excel parser dependencies are not installed") from exc

    try:
        workbook = pd.read_excel(BytesIO(file_bytes), sheet_name=None, header=None, dtype=object)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read Excel file: {exc}") from exc

    valid_by_type: dict[str, list[dict]] = {key: [] for key in BULK_ROW_MODELS}
    failed_rows: list[dict] = []

    for sheet_name, sub_tab_type in BULK_MASTER_SHEETS.items():
        if sub_tab_type == "raw_materials":
            if sheet_name not in workbook:
                failed_rows.append({"sheet": sheet_name, "row": None, "error": "Required worksheet is missing"})
                continue
            for raw_sub_type in RAW_MATERIAL_SECTIONS:
                valid_rows, sheet_errors = read_raw_material_section(workbook[sheet_name], raw_sub_type)
                valid_by_type[raw_sub_type] = valid_rows
                failed_rows.extend(sheet_errors)
            continue

        valid_rows, sheet_errors = read_standard_sheet(workbook, sheet_name, sub_tab_type)
        valid_by_type[sub_tab_type] = valid_rows
        failed_rows.extend(sheet_errors)
    return valid_by_type, failed_rows


def inspect_finished_goods_sheet(file_bytes: bytes) -> dict:
    import pandas as pd

    debug_info = {
        "sheet_name": None,
        "normalized_headers": [],
        "rows_read": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "skip_reasons": [],
        "created_finished_goods_stock_ids": [],
        "created_final_product_stock_ids": [],
        "matched_existing_final_product_stock_ids": [],
    }
    workbook = pd.read_excel(BytesIO(file_bytes), sheet_name=None, header=None, dtype=object)
    sheet_name = next(
        (name for name in workbook if canonical_bulk_header(name) == "finished_goods"),
        None,
    )
    if sheet_name is None:
        available = ", ".join(str(name) for name in workbook) or "none"
        debug_info["skip_reasons"].append(
            f"Finished Goods sheet not imported because the worksheet was not found. Available sheets: {available}"
        )
        return debug_info

    debug_info["sheet_name"] = sheet_name
    frame = workbook[sheet_name]
    if len(frame.index) < 2:
        debug_info["skip_reasons"].append(
            "Finished Goods sheet not imported because the header row is missing"
        )
        return debug_info

    debug_info["normalized_headers"] = [
        header for header in (canonical_bulk_header(value) for value in frame.iloc[1].tolist()) if header
    ]
    return debug_info


def build_master_onboarding_workbook() -> BytesIO:
    import pandas as pd
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, sub_tab_type in BULK_MASTER_SHEETS.items():
            if sub_tab_type == "raw_materials":
                pd.DataFrame().to_excel(writer, index=False, header=False, sheet_name=sheet_name)
                continue
            frame = pd.DataFrame(
                [
                    [f"Instruction: keep row_type as SAMPLE for examples and ACTUAL for rows to import."],
                    BULK_TEMPLATE_COLUMNS[sub_tab_type],
                    SAMPLE_BULK_ROWS[sub_tab_type],
                    *[[None] * len(BULK_TEMPLATE_COLUMNS[sub_tab_type]) for _ in range(10)],
                ]
            )
            frame.to_excel(writer, index=False, header=False, sheet_name=sheet_name)

        workbook = writer.book
        header_fill = PatternFill("solid", fgColor="EDE9FE")
        section_fill = PatternFill("solid", fgColor="DCFCE7")
        section_font = Font(bold=True, color="14532D")
        header_font = Font(bold=True, color="111827")

        for sheet_name, sub_tab_type in BULK_MASTER_SHEETS.items():
            worksheet = workbook[sheet_name]
            if sub_tab_type == "raw_materials":
                for raw_sub_type, section in RAW_MATERIAL_SECTIONS.items():
                    label_row = int(section["label_row"])
                    header_row = int(section["header_row"])
                    data_start = int(section["data_start"])
                    worksheet.cell(row=label_row, column=1, value=section["title"])
                    worksheet.cell(row=label_row, column=1).fill = section_fill
                    worksheet.cell(row=label_row, column=1).font = section_font
                    for column_index, header in enumerate(BULK_TEMPLATE_COLUMNS[raw_sub_type], start=1):
                        cell = worksheet.cell(row=header_row, column=column_index, value=header)
                        cell.fill = header_fill
                        cell.font = header_font
                    for column_index, value in enumerate(SAMPLE_BULK_ROWS[raw_sub_type], start=1):
                        worksheet.cell(row=data_start, column=column_index, value=value)
                for column_index in range(1, 9):
                    worksheet.column_dimensions[get_column_letter(column_index)].width = 24
                continue

            worksheet.cell(row=1, column=1).fill = section_fill
            worksheet.cell(row=1, column=1).font = section_font
            for column_index in range(1, len(BULK_TEMPLATE_COLUMNS[sub_tab_type]) + 1):
                worksheet.cell(row=2, column=column_index).fill = header_fill
                worksheet.cell(row=2, column=column_index).font = header_font
                worksheet.column_dimensions[get_column_letter(column_index)].width = 24
    output.seek(0)
    return output


def log_bulk_upload(background_tasks: BackgroundTasks, db: Session, current_user: User, sub_tab_type: str, row_count: int) -> None:
    background_tasks.add_task(
        log_activity,
        db,
        int(current_user.factory_id),
        current_user.id,
        current_user.full_name or current_user.username,
        current_user.role,
        "BULK_UPLOAD_COMPLETED",
        f"System: {current_user.role} completed bulk upload of {row_count} entries in {sub_tab_type}",
        sub_tab_type,
        None,
        {"row_count": row_count, "sub_tab_type": sub_tab_type},
    )


def log_bulk_inventory_uploads(
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
    inserted_counts: dict[str, int],
) -> None:
    log_specs = {
        "blank_stock": (
            "RAW_MATERIAL_ADDED",
            "Raw material bulk upload completed - {count} blank stock entries",
            "raw_material",
        ),
        "bottom_reel": (
            "RAW_MATERIAL_ADDED",
            "Raw material bulk upload completed - {count} bottom reel entries",
            "raw_material",
        ),
        "box_stock": (
            "PACKAGING_MATERIAL_ADDED",
            "Packaging material bulk upload completed - {count} box stock entries",
            "packaging_material",
        ),
        "plastic_stock": (
            "PACKAGING_MATERIAL_ADDED",
            "Packaging material bulk upload completed - {count} plastic stock entries",
            "packaging_material",
        ),
        "finished_goods": (
            "FINISHED_GOODS_STOCK_SAVED",
            "Finished goods bulk upload completed - {count} stock entries",
            "finished_goods_stock",
        ),
    }
    for sub_tab_type, (action_type, summary_template, entity_type) in log_specs.items():
        row_count = int(inserted_counts.get(sub_tab_type) or 0)
        if row_count <= 0:
            continue
        background_tasks.add_task(
            log_activity,
            db,
            int(current_user.factory_id),
            current_user.id,
            current_user.full_name or current_user.username,
            current_user.role,
            action_type,
            summary_template.format(count=row_count),
            entity_type,
            None,
            {"row_count": row_count, "sub_tab_type": sub_tab_type},
        )


def sync_finished_goods_to_final_product_stock(
    db: Session,
    factory_id: int,
    stock: FinishedGoodsStock,
    fg_debug_info: dict | None = None,
) -> FinalProductStock:
    profile = (
        db.query(PackagingProfile)
        .filter(
            PackagingProfile.factory_id == factory_id,
            PackagingProfile.id == stock.packaging_profile_id,
        )
        .first()
    )
    if profile is None:
        raise ValueError(
            f"Finished Goods sheet not imported because packaging profile {stock.packaging_profile_id} "
            f"does not belong to factory {factory_id}"
        )

    variety = (stock.variant_name or "Standard/White").strip() or "Standard/White"
    packaging_size_name = profile.profile_name.strip()
    final_stock = (
        db.query(FinalProductStock)
        .filter(
            FinalProductStock.factory_id == factory_id,
            FinalProductStock.product_size_ml == stock.cup_size_ml,
            sql_func.lower(FinalProductStock.variety) == variety.lower(),
            sql_func.lower(FinalProductStock.packaging_size_name) == packaging_size_name.lower(),
        )
        .with_for_update()
        .first()
    )
    if final_stock is None:
        final_stock = FinalProductStock(
            factory_id=factory_id,
            product_size_ml=stock.cup_size_ml,
            variety=variety,
            packaging_size_name=packaging_size_name,
            pieces_per_packet=profile.cups_per_poly or 1,
            packets_per_box_limit=profile.polys_per_box or 1,
            current_quantity=stock.boxes_available or 0,
            total_boxes=stock.boxes_available or 0,
            loose_packets=0,
        )
        db.add(final_stock)
        db.flush()
        if fg_debug_info is not None:
            fg_debug_info["created_final_product_stock_ids"].append(final_stock.id)
    else:
        final_stock.pieces_per_packet = profile.cups_per_poly or 1
        final_stock.packets_per_box_limit = profile.polys_per_box or 1
        final_stock.current_quantity = stock.boxes_available or 0
        final_stock.total_boxes = stock.boxes_available or 0
        db.flush()
        if fg_debug_info is not None:
            fg_debug_info["matched_existing_final_product_stock_ids"].append(final_stock.id)
    return final_stock


def apply_bulk_rows(db: Session, current_user: User, sub_tab_type: str, valid_rows: list[dict], stats: dict[str, int] | None = None, fg_debug_info: dict | None = None) -> int:
    factory_id = int(current_user.factory_id)
    if not valid_rows:
        return 0

    if sub_tab_type == "company_profile":
        row = valid_rows[0]
        factory = db.query(Factory).filter(Factory.id == factory_id).with_for_update().first()
        if factory is None:
            raise HTTPException(status_code=404, detail="Factory not found")
        settings = get_or_create_factory_settings(db, factory_id)
        factory.factory_name = row["factory_name"].strip()
        factory.name = factory.name or row["factory_name"].strip()
        factory.gst_number = (row.get("gstin") or "").strip() or None
        factory.address = (row.get("factory_address") or "").strip() or None
        factory.invoice_prefix = (row.get("invoice_prefix") or "INV-").strip() or "INV-"
        factory.advance_payment_discount_percentage = row.get("advance_upi_discount") or Decimal("2.00")
        settings.bill_of_supply_start_seq = row["bill_of_supply_start_seq"]
        settings.tax_invoice_start_seq = row["tax_invoice_start_seq"]
        settings.bill_of_supply_simple_start_seq = row["bill_of_supply_simple_start_seq"]
        factory.next_bill_of_supply_number = row["bill_of_supply_start_seq"]
        factory.next_tax_invoice_number = row["tax_invoice_start_seq"]
        factory.next_bill_of_supply_simple_number = row["bill_of_supply_simple_start_seq"]
        increment_bulk_stat(stats, "updated")
        return 1

    if sub_tab_type == "worker":
        worker_names = [row["name"].strip() for row in valid_rows if row.get("name") and row["name"].strip()]
        existing_workers = {
            worker.name.strip().lower(): worker
            for worker in db.query(Worker)
            .filter(Worker.factory_id == factory_id, Worker.name.in_(worker_names))
            .with_for_update()
            .all()
        }
        worker_rows: list[tuple[Worker, dict]] = []
        for row in valid_rows:
            worker_name = row["name"].strip()
            if not worker_name:
                increment_bulk_stat(stats, "skipped")
                continue
            worker_key = worker_name.lower()
            phone, _ = normalize_phone_number(str(row["mobile_number"])) if row.get("mobile_number") else (None, None)
            worker = existing_workers.get(worker_key)
            if worker is None:
                worker = Worker(factory_id=factory_id, name=worker_name)
                db.add(worker)
                existing_workers[worker_key] = worker
                increment_bulk_stat(stats, "inserted")
            else:
                increment_bulk_stat(stats, "updated")
            worker.phone = phone
            worker.daily_wage_rate = row["daily_wages"]
            worker.daily_wages = row["daily_wages"]
            worker.duty_hours = row["duty_hours"]
            worker.salary = worker.salary or 0
            worker.daily_salary = row["daily_wages"]
            worker.shift_hours = row["duty_hours"]
            worker.shift_type = worker.shift_type or "worker"
            worker.is_active = True
            worker_rows.append((worker, row))
        db.flush()

        for worker, row in worker_rows:
            if row["previous_attendance_details"] <= 0 or not worker.id:
                continue
            opening_attendance = (
                db.query(WorkerOpeningAttendance)
                .filter(
                    WorkerOpeningAttendance.factory_id == factory_id,
                    WorkerOpeningAttendance.worker_id == worker.id,
                )
                .with_for_update()
                .first()
            )
            if opening_attendance is None:
                opening_attendance = WorkerOpeningAttendance(
                    factory_id=factory_id,
                    worker_id=worker.id,
                    created_by_user_id=current_user.id,
                )
                db.add(opening_attendance)
            opening_attendance.period_start = date.today()
            opening_attendance.period_end = date.today()
            opening_attendance.present_days = row["previous_attendance_details"]
            opening_attendance.half_days = 0
            opening_attendance.absent_days = 0
            opening_attendance.paid_leave_days = 0
            opening_attendance.overtime_hours = 0
            opening_attendance.advance_paid = 0
            opening_attendance.deductions = 0
            opening_attendance.notes = "Opening attendance imported by bulk upload"
        return len(worker_rows)

    if sub_tab_type == "customer":
        customer_names = [row["name"].strip().lower() for row in valid_rows if row.get("name") and row["name"].strip()]
        existing_customers = {
            customer.name.strip().lower(): customer
            for customer in db.query(Customer)
            .filter(
                Customer.factory_id == factory_id,
                sql_func.lower(Customer.name).in_(customer_names),
            )
            .with_for_update()
            .all()
        }
        saved_count = 0
        for row in valid_rows:
            customer_name = row["name"].strip()
            if not customer_name:
                increment_bulk_stat(stats, "skipped")
                continue
            customer_key = customer_name.lower()
            customer = existing_customers.get(customer_key)
            if customer is None:
                customer = Customer(factory_id=factory_id, name=customer_name)
                db.add(customer)
                existing_customers[customer_key] = customer
                increment_bulk_stat(stats, "inserted")
            else:
                increment_bulk_stat(stats, "updated")

            contact_number = (row.get("contact_number") or "").strip() or None
            phone_number = (row.get("phone_number") or "").strip() or None
            previous_due = Decimal(str(row.get("previous_due") or "0"))
            advance_balance = Decimal(str(row.get("advance_balance") or "0"))
            customer.name = customer_name
            customer.firm_name = (row.get("firm_name") or "").strip() or None
            customer.contact_number = contact_number
            customer.phone_number = phone_number
            customer.phone = phone_number or contact_number
            customer.place = (row.get("place") or "").strip() or None
            customer.address = (row.get("address") or "").strip() or None
            customer.gst_number = (row.get("gst_number") or "").strip() or None
            customer.previous_due = previous_due
            customer.advance_balance = advance_balance
            customer.total_due = previous_due
            customer.pending_dues = float(previous_due)
            customer.pending_balance = previous_due
            customer.balance_amount = previous_due
            
            db.flush()
            if previous_due > 0:
                open_bill = (
                    db.query(OutstandingBill)
                    .filter(OutstandingBill.factory_id == factory_id)
                    .filter(OutstandingBill.customer_id == customer.id)
                    .filter(OutstandingBill.source_type.in_(("opening_balance", "opening_outstanding")))
                    .first()
                )
                if not open_bill:
                    create_outstanding_bill(
                        db,
                        factory_id=factory_id,
                        customer_id=customer.id,
                        source_type="opening_outstanding",
                        tracking_number=f"OPEN-{customer.id}",
                        bill_date=date.today(),
                        bill_amount=previous_due,
                        amount_paid=Decimal("0.00"),
                    )
            saved_count += 1
        db.flush()
        return saved_count

    if sub_tab_type == "machine":
        saved_count = 0
        for row in valid_rows:
            machine_name = row["machine_name"].strip()
            if not machine_name:
                increment_bulk_stat(stats, "skipped")
                continue
            machine = (
                db.query(Machine)
                .filter(
                    Machine.factory_id == factory_id,
                    sql_func.lower(Machine.name) == machine_name.lower(),
                )
                .with_for_update()
                .first()
            )
            if machine is None:
                machine = Machine(factory_id=factory_id, name=machine_name)
                db.add(machine)
                increment_bulk_stat(stats, "inserted")
            else:
                increment_bulk_stat(stats, "updated")
            machine.name = machine_name
            machine.machine_name = machine_name
            machine.machine_type = machine_name
            machine.mould_size_ml = row.get("mould_size_ml")
            machine.bottom_size_mm = row.get("bottom_size_mm")
            machine.speed_per_minute = row["default_operating_speed"]
            machine.speed_bpm = row["default_operating_speed"]
            machine.speed_cups_per_minute = row["default_operating_speed"]
            machine.default_speed = row["default_operating_speed"]
            machine.target_output_per_shift = row["target_output_per_shift"]
            machine.raw_materials_mapped = ["blank_stock", "bottom_reel"]
            machine.is_active = True
            saved_count += 1
        db.flush()
        return saved_count

    if sub_tab_type == "blank_stock":
        # total_boras_sacks is optional so existing customer workbooks remain
        # valid. Missing values preserve the legacy zero-quantity behavior.
        saved_count = 0
        for row in valid_rows:
            blank_size_ml = int(row["size_ml"])
            variety = row["material_name"].strip() or "Plain White"
            stock = (
                db.query(BlankStock)
                .filter(
                    BlankStock.factory_id == factory_id,
                    BlankStock.blank_size_ml == blank_size_ml,
                    sql_func.lower(BlankStock.variety) == variety.lower(),
                )
                .with_for_update()
                .first()
            )
            if stock is None:
                stock = BlankStock(factory_id=factory_id, blank_size_ml=blank_size_ml, variety=variety)
                db.add(stock)
                increment_bulk_stat(stats, "inserted")
            else:
                increment_bulk_stat(stats, "updated")
            stock.linked_bottom_size_mm = blank_size_ml
            stock.weight_per_bora_kg = row["kg_per_sack"]
            if "total_boras_sacks" in row:
                total_boras = row.get("total_boras_sacks") or Decimal("0")
                stock.total_boras = total_boras
                stock.total_qty_kg = total_boras * row["kg_per_sack"]
            else:
                stock.total_boras = stock.total_boras or 0
                stock.total_qty_kg = stock.total_qty_kg or 0
            saved_count += 1
        db.flush()
        return saved_count

    if sub_tab_type == "bottom_reel":
        saved_count = 0
        for row in valid_rows:
            bottom_size_mm = int(row["bottom_size_mm"])
            variety = "Plain White"
            stock = (
                db.query(BottomStock)
                .filter(
                    BottomStock.factory_id == factory_id,
                    BottomStock.bottom_size_mm == bottom_size_mm,
                    sql_func.lower(BottomStock.variety) == variety.lower(),
                )
                .with_for_update()
                .first()
            )
            if stock is None:
                stock = BottomStock(factory_id=factory_id, bottom_size_mm=bottom_size_mm, variety=variety)
                db.add(stock)
                increment_bulk_stat(stats, "inserted")
            else:
                increment_bulk_stat(stats, "updated")
            stock.total_rolls = row["total_individual_rolls"]
            stock.total_weight_kg = row["total_weight_kg"]
            stock.total_qty_kg = row["total_weight_kg"]
            saved_count += 1
        db.flush()
        return saved_count

    if sub_tab_type == "box_stock":
        saved_count = 0
        for row in valid_rows:
            packaging_size_name = row["box_type"].strip()
            stock = (
                db.query(BoxStock)
                .filter(
                    BoxStock.factory_id == factory_id,
                    sql_func.lower(BoxStock.packaging_size_name) == packaging_size_name.lower(),
                )
                .with_for_update()
                .first()
            )
            if stock is None:
                stock = BoxStock(factory_id=factory_id, packaging_size_name=packaging_size_name)
                db.add(stock)
                increment_bulk_stat(stats, "inserted")
            else:
                increment_bulk_stat(stats, "updated")
            stock.box_type = packaging_size_name
            stock.quantity = row["box_quantity_pieces"]
            stock.total_boxes = row["box_quantity_pieces"]
            stock.price_per_box = row["price_per_box_rs"]
            saved_count += 1
        db.flush()
        return saved_count

    if sub_tab_type == "plastic_stock":
        saved_count = 0
        for row in valid_rows:
            plastic_size_name = row["plastic_size_type"].strip()
            cup_size_ml = int(row["used_for_cup_size_ml"])
            stock = (
                db.query(PlasticStock)
                .filter(
                    PlasticStock.factory_id == factory_id,
                    sql_func.lower(PlasticStock.plastic_size_name) == plastic_size_name.lower(),
                    PlasticStock.cup_size_ml == cup_size_ml,
                )
                .with_for_update()
                .first()
            )
            if stock is None:
                stock = PlasticStock(factory_id=factory_id, plastic_size_name=plastic_size_name, cup_size_ml=cup_size_ml)
                db.add(stock)
                increment_bulk_stat(stats, "inserted")
            else:
                increment_bulk_stat(stats, "updated")
            stock.total_boras = row["total_boras_sacks"]
            stock.weight_per_bora_kg = row["weight_per_bora_kg"]
            stock.price_per_kg = row["price_per_kg_rs"]
            saved_count += 1
        db.flush()
        return saved_count

    if sub_tab_type == "finished_goods":
        saved_count = 0
        if fg_debug_info is not None:
            fg_debug_info["rows_read"] = len(valid_rows)
        for row in valid_rows:
            product_size_ml = int(row["product_size_ml"])
            variety = (row.get("variety_design") or "Standard/White").strip() or "Standard/White"
            packaging_size_name = (row.get("packaging_size_name") or "").strip()
            if not packaging_size_name:
                packaging_size_name = f"{product_size_ml}ML - {variety}"
            pieces_per_packet = max(int(row["pcs_per_packet"]), 1)
            packets_per_box = max(int(row["packets_per_box"]), 1)
            initial_stock_boxes = max(int(row["initial_stock_boxes"]), 0)

            box_inventory = get_or_create_inventory(db, factory_id, packaging_size_name, "Packaging", "pieces")
            poly_inventory = get_or_create_inventory(db, factory_id, f"{product_size_ml}ml Polybag", "Packaging", "pieces")
            profile = (
                db.query(PackagingProfile)
                .filter(PackagingProfile.factory_id == factory_id)
                .filter(sql_func.lower(PackagingProfile.profile_name) == packaging_size_name.lower())
                .with_for_update()
                .first()
            )
            if profile is None:
                profile = PackagingProfile(
                    factory_id=factory_id,
                    profile_name=packaging_size_name,
                    product_name=f"{product_size_ml}ml Paper Cup",
                    product_name_ml=product_size_ml,
                    cup_size_ml=product_size_ml,
                    print_design_name=variety,
                    polybag_capacity=pieces_per_packet,
                    box_capacity=pieces_per_packet * packets_per_box,
                    box_size_name=packaging_size_name,
                    cups_per_poly=pieces_per_packet,
                    cups_per_polybag=pieces_per_packet,
                    polys_per_box=packets_per_box,
                    polybags_per_box=packets_per_box,
                    box_inventory_id=box_inventory.id,
                    poly_inventory_id=poly_inventory.id,
                )
                db.add(profile)
                db.flush()
            else:
                profile.print_design_name = variety
                profile.cup_size_ml = product_size_ml
                profile.product_name_ml = product_size_ml
                profile.polybag_capacity = pieces_per_packet
                profile.box_capacity = pieces_per_packet * packets_per_box
                profile.cups_per_poly = pieces_per_packet
                profile.cups_per_polybag = pieces_per_packet
                profile.polys_per_box = packets_per_box
                profile.polybags_per_box = packets_per_box
                profile.box_inventory_id = box_inventory.id
                profile.poly_inventory_id = poly_inventory.id
                db.flush()

            # Update FinishedGoodsStock
            stock = (
                db.query(FinishedGoodsStock)
                .filter(FinishedGoodsStock.factory_id == factory_id)
                .filter(FinishedGoodsStock.packaging_profile_id == profile.id)
                .with_for_update()
                .first()
            )
            is_new_stock = stock is None
            if is_new_stock:
                stock = FinishedGoodsStock(
                    factory_id=factory_id,
                    cup_size_ml=product_size_ml,
                    packaging_profile_id=profile.id,
                    boxes_available=initial_stock_boxes,
                    category="CUP_FINISHED",
                    variant_name=variety,
                )
                db.add(stock)
                increment_bulk_stat(stats, "inserted")
            else:
                stock.cup_size_ml = product_size_ml
                stock.boxes_available = initial_stock_boxes
                stock.category = "CUP_FINISHED"
                stock.variant_name = variety
                increment_bulk_stat(stats, "updated")

            db.flush()
            if fg_debug_info is not None:
                if is_new_stock:
                    fg_debug_info["rows_inserted"] += 1
                else:
                    fg_debug_info["rows_updated"] += 1
                fg_debug_info["created_finished_goods_stock_ids"].append(stock.id)

            sync_finished_goods_to_final_product_stock(db, factory_id, stock, fg_debug_info)

            saved_count += 1
        return saved_count

    return 0


def _log_onboarding_change(db: Session, factory_id: int, action: str, subject: str) -> None:
    try:
        log_factory_operation(
            db,
            factory_id=int(factory_id),
            event_type="machine_telemetry",
            description=f"👥 Onboarding Change: {action} {subject} in system configs",
        )
    except Exception as log_error:
        logger.exception("Suppressed activity log failure for onboarding change: %s", log_error)


@v1_router.get("/template/master")
def download_master_onboarding_template(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
):
    return StreamingResponse(
        build_master_onboarding_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{MASTER_ONBOARDING_FILENAME}"'},
    )


@v1_router.post("/bulk-upload/master/validate")
async def validate_master_onboarding(
    file: UploadFile = File(...),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
):
    """
    Dry-run validation: parse the Excel workbook and return a detailed row-by-row
    validation report WITHOUT committing anything to the database.
    """
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Only .xlsx master onboarding files are supported")

    valid_by_type, failed_rows = read_master_bulk_excel(await file.read())
    valid_by_type, duplicate_warnings = dedupe_valid_bulk_rows(valid_by_type)

    # Count total ACTUAL rows across all sheets
    total_attempted = sum(len(rows) for rows in valid_by_type.values())
    successful_rows = total_attempted  # in dry-run all valid rows are "would succeed"

    issues = enrich_failed_rows(failed_rows) + duplicate_warnings
    report = make_report(issues, successful_rows=successful_rows, total_rows_attempted=total_attempted + len(failed_rows))

    return {
        "dry_run": True,
        "message": "Validation complete. No data was imported.",
        "overall_status": "failed" if report.has_fatal else ("partial" if report.warning_issues else "ok"),
        "validation_report": report.to_dict(),
        "would_import_counts": {k: len(v) for k, v in valid_by_type.items() if v},
    }


@v1_router.post("/bulk-upload/master")
async def bulk_upload_master_onboarding(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Only .xlsx master onboarding files are supported")

    file_bytes = await file.read()
    fg_debug_info = inspect_finished_goods_sheet(file_bytes)
    valid_by_type, failed_rows = read_master_bulk_excel(file_bytes)

    valid_by_type, duplicate_warnings = dedupe_valid_bulk_rows(valid_by_type)

    # Build enriched validation report
    total_attempted = sum(len(rows) for rows in valid_by_type.values()) + len(failed_rows)
    issues = enrich_failed_rows(failed_rows) + duplicate_warnings

    # Extract any failures or skip reasons for Finished Goods
    fg_errors = [err for err in failed_rows if err.get("sheet") == "Finished Goods"]
    if fg_errors:
        for err in fg_errors:
            reason = err.get("error") or "unknown validation error"
            missing = err.get("missing_headers")
            if missing:
                reason = f"{reason}; missing headers: {', '.join(missing)}"
            fg_debug_info["skip_reasons"].append(
                f"Finished Goods sheet not imported because {reason}"
            )
            fg_debug_info["rows_skipped"] += 1
    elif fg_debug_info["sheet_name"] and not valid_by_type.get("finished_goods"):
        fg_debug_info["skip_reasons"].append("Finished Goods sheet not imported because no ACTUAL rows were found or sheet is empty")

    # Fatal errors block the entire import
    fatal_issues = [i for i in issues if i.severity == ValidationSeverity.FATAL]
    if fatal_issues:
        report = make_report(issues, successful_rows=0, total_rows_attempted=total_attempted)
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Import rejected due to validation errors. Fix the highlighted rows and upload again.",
                "overall_status": "failed",
                "validation_report": report.to_dict(),
                "failed_rows": failed_rows,
                "fg_debug_info": fg_debug_info,
            },
        )

    if not any(valid_by_type.values()):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No importable rows found. Mark data rows with row_type = ACTUAL.",
                "overall_status": "failed",
                "validation_report": make_report([], 0, 0).to_dict(),
                "failed_rows": [{"sheet": "Workbook", "row": None, "error": "No valid rows found"}],
                "fg_debug_info": fg_debug_info,
            },
        )

    inserted_counts: dict[str, int] = {}
    operation_counts: dict[str, int] = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "warnings": len([issue for issue in issues if issue.severity == ValidationSeverity.WARNING]),
    }
    try:
        for sub_tab_type in BULK_TEMPLATE_COLUMNS:
            inserted_counts[sub_tab_type] = apply_bulk_rows(
                db,
                current_user,
                sub_tab_type,
                valid_by_type.get(sub_tab_type, []),
                operation_counts,
                fg_debug_info=fg_debug_info if sub_tab_type == "finished_goods" else None
            )
        db.commit()
        total_rows = sum(inserted_counts.values())
        log_bulk_upload(background_tasks, db, current_user, "master_onboarding", total_rows)
        log_bulk_inventory_uploads(background_tasks, db, current_user, inserted_counts)

        report = make_report(issues, successful_rows=total_rows, total_rows_attempted=total_attempted)
        overall_status = "partial" if report.warning_issues else "success"

        # Calculate dynamic summary status counts for response
        summary_payload = {
            "finished_goods": {
                "read": fg_debug_info["rows_read"],
                "inserted": fg_debug_info["rows_inserted"],
                "updated": fg_debug_info["rows_updated"],
                "skipped": fg_debug_info["rows_skipped"],
            },
            "workers": {
                "read": len(valid_by_type.get("worker", [])),
                "inserted": len(valid_by_type.get("worker", [])),
                "updated": 0,
                "skipped": 0,
            },
            "customers": {
                "read": len(valid_by_type.get("customer", [])),
                "inserted": len(valid_by_type.get("customer", [])),
                "updated": 0,
                "skipped": 0,
            },
            "raw_materials": {
                "read": len(valid_by_type.get("blank_stock", [])) + len(valid_by_type.get("bottom_reel", [])),
                "inserted": len(valid_by_type.get("blank_stock", [])) + len(valid_by_type.get("bottom_reel", [])),
                "updated": 0,
                "skipped": 0,
            },
            "machines": {
                "read": len(valid_by_type.get("machine", [])),
                "inserted": len(valid_by_type.get("machine", [])),
                "updated": 0,
                "skipped": 0,
            }
        }

        return {
            "message": "Master onboarding bulk upload completed",
            "overall_status": overall_status,
            "rows_inserted": total_rows,
            "inserted_counts": inserted_counts,
            "operation_counts": operation_counts,
            "validation_report": report.to_dict(),
            "summary": summary_payload,
            "fg_debug_info": fg_debug_info,
            "errors": [err for err in failed_rows],
            # kept for backward compatibility
            "failed_rows": [],
        }
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        db_issues = enrich_failed_rows([{"sheet": "Database", "row": None, "error": str(exc.orig)}])
        report = make_report(db_issues, successful_rows=0, total_rows_attempted=total_attempted)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Database integrity error. A duplicate or conflicting record may already exist. Review the validation report and upload again.",
                "overall_status": "failed",
                "validation_report": report.to_dict(),
                "failed_rows": [{"sheet": "Database", "row": None, "error": str(exc.orig)}],
            },
        ) from exc
    except Exception as exc:
        db.rollback()
        db_issues = enrich_failed_rows([{"sheet": "Database", "row": None, "error": str(exc)}])
        report = make_report(db_issues, successful_rows=0, total_rows_attempted=total_attempted)
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Unexpected server error during import.",
                "overall_status": "failed",
                "validation_report": report.to_dict(),
                "failed_rows": [{"sheet": "Database", "row": None, "error": str(exc)}],
            },
        ) from exc


class OnboardingWorkerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    daily_wages: Decimal
    duty_hours: float
    previous_attendance: int = 0


class OnboardingMachineSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_type: str
    machine_number: Optional[str] = None
    mould_size_ml: Optional[int] = None
    bottom_size_mm: Optional[int] = None
    speed_per_minute: int
    machine_name: Optional[str] = None
    default_speed: float = 0
    target_output_per_shift: int = 0
    raw_materials_mapped: List[str] = Field(default_factory=list)
    is_active: bool = True


class OnboardingRawMetricSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_type: str
    size_ml_or_mm: int
    weight_per_sack_kg: Decimal
    pieces_per_sack: int


class OnboardingPackagingMetricSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cup_size_ml: int
    kg_per_box: Decimal
    cups_per_box: int
    variety: Optional[str] = "Standard/White"


class OnboardingOverviewResponse(BaseModel):
    workers: List[OnboardingWorkerSummary]
    machines: List[OnboardingMachineSummary]
    raw_material_metrics: List[OnboardingRawMetricSummary]
    packaging_metrics: List[OnboardingPackagingMetricSummary]


class MachineLimitResponse(BaseModel):
    used: int
    limit: int
    plan: str
    nearing_limit: bool
    limit_reached: bool


class OnboardingCustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str] = None
    total_due: Decimal


def _worker_summary(worker: Worker, previous_attendance: int = 0) -> dict:
    return {
        "id": worker.id,
        "name": worker.name or "Unnamed Worker",
        "daily_wages": Decimal(worker.daily_wages or worker.daily_salary or worker.salary or 0),
        "duty_hours": float(worker.duty_hours or worker.shift_hours or 8.0),
        "previous_attendance": int(previous_attendance or 0),
    }


def _machine_summary(machine: Machine) -> dict:
    machine_number = machine.machine_number or machine.machine_sequence_number or machine.name or f"M-{machine.id}"
    return {
        "id": machine.id,
        "machine_type": machine.machine_type or machine.machine_name or machine.name or "Custom Machine",
        "machine_number": machine_number,
        "mould_size_ml": machine.mould_size_ml or machine.cup_size_ml or machine.current_mould_size,
        "bottom_size_mm": machine.bottom_size_mm or machine.bottom_size or machine.current_bottom_size,
        "speed_per_minute": int(machine.speed_per_minute or machine.speed_cups_per_minute or machine.speed_bpm or 0),
        "machine_name": machine.machine_name or machine.machine_type or machine.name,
        "default_speed": float(machine.default_speed or machine.speed_per_minute or machine.speed_cups_per_minute or machine.speed_bpm or 0),
        "target_output_per_shift": int(machine.target_output_per_shift or 0),
        "raw_materials_mapped": machine.raw_materials_mapped or [],
        "is_active": bool(machine.is_active),
    }


def _raw_metric_summary(metric: RawMaterialMetrics) -> dict:
    return {
        "id": metric.id,
        "material_type": metric.material_type or "Blank",
        "size_ml_or_mm": int(metric.size_ml_or_mm or 1),
        "weight_per_sack_kg": Decimal(metric.weight_per_sack_kg or 0),
        "pieces_per_sack": int(metric.pieces_per_sack or 1),
    }


def _packaging_metric_summary(metric: PackagingMetrics) -> dict:
    return {
        "id": metric.id,
        "cup_size_ml": int(metric.cup_size_ml or 1),
        "kg_per_box": Decimal(metric.kg_per_box or 0),
        "cups_per_box": int(metric.cups_per_box or 1),
        "variety": getattr(metric, "variant_name", None) or "Standard/White",
    }


class FinalProductOpeningStockRequest(BaseModel):
    product_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: Optional[int] = Field(default=None, gt=0)
    variety: str = Field(default="Standard/White", max_length=100)
    packaging_size: Optional[str] = Field(default=None, max_length=100)
    packaging_size_name: Optional[str] = Field(default=None, max_length=100)
    initial_quantity: int = Field(default=0, ge=0)
    current_quantity: Optional[int] = Field(default=None, ge=0)
    total_boxes: Optional[int] = Field(default=None, ge=0)
    loose_packets: int = Field(default=0, ge=0)
    pieces_per_packet: int = Field(default=1, gt=0)
    packets_per_box: Optional[int] = Field(default=None, gt=0)
    packets_per_box_limit: Optional[int] = Field(default=None, gt=0)
    category: Optional[str] = None


class FinalProductOpeningStockResponse(BaseModel):
    id: int
    factory_id: str
    product_size_ml: Optional[int] = None
    variety: Optional[str] = None
    packaging_size: Optional[str] = None
    packaging_size_name: Optional[str] = None
    pieces_per_packet: Optional[int] = None
    packets_per_box: Optional[int] = None
    current_quantity: Optional[int] = None
    total_boxes: Optional[int] = None
    loose_packets: Optional[int] = None
    packets_per_box_limit: Optional[int] = None


class BottomStockCreate(BaseModel):
    bottom_size_mm: int = Field(..., gt=0)
    bag_weight_kg: Optional[Decimal] = Field(default=None, ge=0)
    rolls_per_bag: Optional[int] = Field(default=None, ge=0)
    total_bags: Optional[int] = Field(default=None, ge=0)
    total_rolls: Optional[int] = Field(default=None, ge=0)
    total_weight_kg: Optional[Decimal] = Field(default=None, ge=0)


class BlankStockCreate(BaseModel):
    material_name: str = Field(default="Blank", max_length=100)
    size_ml: int = Field(..., gt=0)
    kg_per_sack: Decimal = Field(..., gt=0)
    total_sacks: Decimal = Field(..., ge=0)


@router.get("/factory-profile", response_model=FactoryProfileResponse)
def get_factory_profile(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db)
):
    if not current_user.factory_id:
        raise HTTPException(status_code=404, detail="No factory linked to this user")
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
    if not factory:
        raise HTTPException(status_code=404, detail="Factory not found")
    settings = (
        db.query(FactorySettings)
        .filter(FactorySettings.factory_id == int(factory.id))
        .first()
    )
    return FactoryProfileResponse(
        id=factory.id,
        factory_name=factory.factory_name or factory.name,
        address=factory.address,
        gst_number=getattr(factory, "gst_number", None),
        invoice_prefix=getattr(factory, "invoice_prefix", "INV-") or "INV-",
        advance_payment_discount_percentage=getattr(factory, "advance_payment_discount_percentage", Decimal("2.00")) or Decimal("2.00"),
        digital_signature_url=getattr(factory, "digital_signature_url", None),
        bill_of_supply_start_seq=(settings.bill_of_supply_start_seq if settings else getattr(factory, "next_bill_of_supply_number", 1)) or 1,
        tax_invoice_start_seq=(settings.tax_invoice_start_seq if settings else getattr(factory, "next_tax_invoice_number", 1)) or 1,
        bill_of_supply_simple_start_seq=(settings.bill_of_supply_simple_start_seq if settings else getattr(factory, "next_bill_of_supply_simple_number", 1)) or 1,
        next_tax_invoice_number=getattr(factory, "next_tax_invoice_number", 1) or 1,
        next_bill_of_supply_number=getattr(factory, "next_bill_of_supply_number", 1) or 1,
        next_bill_of_supply_simple_number=getattr(factory, "next_bill_of_supply_simple_number", 1) or 1,
    )

@router.post("/factory-profile", response_model=FactoryProfileResponse)
def update_factory_profile(
    payload: FactoryProfileUpdate,
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db)
):
    if not current_user.factory_id:
        raise HTTPException(status_code=404, detail="No factory linked to this user")
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).with_for_update().first()
    if not factory:
        raise HTTPException(status_code=404, detail="Factory not found")
    settings = get_or_create_factory_settings(db, factory.id)
    
    factory.factory_name = payload.factory_name.strip()
    factory.address = payload.address.strip() if payload.address else None
    factory.gst_number = payload.gst_number.strip() if payload.gst_number else None

    if payload.bill_of_supply_start_seq is not None:
        settings.bill_of_supply_start_seq = int(payload.bill_of_supply_start_seq)
        factory.next_bill_of_supply_number = int(payload.bill_of_supply_start_seq)
    if payload.tax_invoice_start_seq is not None:
        settings.tax_invoice_start_seq = int(payload.tax_invoice_start_seq)
        factory.next_tax_invoice_number = int(payload.tax_invoice_start_seq)
    if payload.bill_of_supply_simple_start_seq is not None:
        settings.bill_of_supply_simple_start_seq = int(payload.bill_of_supply_simple_start_seq)
        factory.next_bill_of_supply_simple_number = int(payload.bill_of_supply_simple_start_seq)

    if payload.invoice_prefix is not None:
        factory.invoice_prefix = payload.invoice_prefix.strip()

    if payload.advance_payment_discount_percentage is not None:
        factory.advance_payment_discount_percentage = payload.advance_payment_discount_percentage

    if payload.digital_signature_url is not None:
        if current_user.role != "Owner":
            raise HTTPException(status_code=403, detail="Only Owner can update invoice signature")
        factory.digital_signature_url = payload.digital_signature_url.strip() if payload.digital_signature_url else None

    db.commit()
    db.refresh(factory)
    return FactoryProfileResponse(
        id=factory.id,
        factory_name=factory.factory_name or factory.name,
        address=factory.address,
        gst_number=factory.gst_number,
        invoice_prefix=factory.invoice_prefix or "INV-",
        advance_payment_discount_percentage=factory.advance_payment_discount_percentage,
        digital_signature_url=factory.digital_signature_url,
        bill_of_supply_start_seq=settings.bill_of_supply_start_seq or 1,
        tax_invoice_start_seq=settings.tax_invoice_start_seq or 1,
        bill_of_supply_simple_start_seq=settings.bill_of_supply_simple_start_seq or 1,
        next_tax_invoice_number=getattr(factory, "next_tax_invoice_number", 1) or 1,
        next_bill_of_supply_number=getattr(factory, "next_bill_of_supply_number", 1) or 1,
        next_bill_of_supply_simple_number=getattr(factory, "next_bill_of_supply_simple_number", 1) or 1,
    )


@router.post("/factory-profile/signature")
async def upload_invoice_signature(
    file: UploadFile = File(...),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=422, detail="Signature must be PNG, JPG, or JPEG")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Signature image must be 2 MB or smaller")
    signature_dir = Path("volumes/media/signatures") / str(current_user.factory_id)
    signature_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    target = signature_dir / filename
    target.write_bytes(content)
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).with_for_update().first()
    if factory is None:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="Factory not found")
    factory.digital_signature_url = f"/media/signatures/{current_user.factory_id}/{filename}"
    db.commit()
    return {"digital_signature_url": factory.digital_signature_url}


@router.delete("/factory-profile/signature")
def remove_invoice_signature(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).with_for_update().first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")
    old_url = factory.digital_signature_url
    factory.digital_signature_url = None
    db.commit()
    if old_url and old_url.startswith(f"/media/signatures/{current_user.factory_id}/"):
        (Path("volumes/media") / old_url.removeprefix("/media/")).unlink(missing_ok=True)
    return {"digital_signature_url": None}


@router.get("/overview", response_model=OnboardingOverviewResponse)
def onboarding_overview(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    workers = (
        db.query(Worker)
        .filter(Worker.factory_id == factory_id)
        .filter(Worker.is_active.is_(True))
        .order_by(Worker.name.asc().nullslast(), Worker.id.asc())
        .all()
    )
    opening_by_worker_id = {
        row.worker_id: int(row.present_days or 0)
        for row in db.query(WorkerOpeningAttendance)
        .filter(WorkerOpeningAttendance.factory_id == factory_id)
        .filter(WorkerOpeningAttendance.worker_id.in_([worker.id for worker in workers] or [0]))
        .all()
    }
    machines = (
        db.query(Machine)
        .filter(Machine.factory_id == factory_id)
        .order_by(Machine.machine_number.asc().nullslast(), Machine.name.asc().nullslast(), Machine.id.asc())
        .all()
    )
    raw_metrics = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .order_by(RawMaterialMetrics.material_type.asc().nullslast(), RawMaterialMetrics.size_ml_or_mm.asc().nullslast(), RawMaterialMetrics.id.asc())
        .all()
    )
    packaging_metrics = (
        db.query(PackagingMetrics)
        .filter(PackagingMetrics.factory_id == factory_id)
        .order_by(PackagingMetrics.cup_size_ml.asc().nullslast(), PackagingMetrics.id.asc())
        .all()
    )
    return OnboardingOverviewResponse(
        workers=[_worker_summary(worker, opening_by_worker_id.get(worker.id, 0)) for worker in workers],
        machines=[_machine_summary(machine) for machine in machines],
        raw_material_metrics=[_raw_metric_summary(metric) for metric in raw_metrics],
        packaging_metrics=[_packaging_metric_summary(metric) for metric in packaging_metrics],
    )


@router.post("/final-stock", response_model=FinalProductOpeningStockResponse)
def save_final_product_opening_stock(
    payload: FinalProductOpeningStockRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    stock = None
    provided_fields = getattr(payload, "model_fields_set", set())

    try:
        product_size_ml = payload.product_size_ml
        packaging_size_name = (payload.packaging_size_name or payload.packaging_size or "").strip()
        variety = (payload.variety or "Standard/White").strip() or "Standard/White"
        pieces_per_packet = int(payload.pieces_per_packet or 1)
        packets_per_box_limit = int(payload.packets_per_box_limit or payload.packets_per_box or 1)
        quantity = payload.current_quantity
        if quantity is None:
            quantity = payload.total_boxes
        if quantity is None:
            quantity = payload.initial_quantity
        quantity = int(quantity or 0)
        loose_packets = int(payload.loose_packets or 0)

        if payload.product_id:
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == factory_id)
                .filter(FinalProductStock.id == payload.product_id)
                .with_for_update()
                .first()
            )
            if stock is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Final product stock item not found")
            product_size_ml = product_size_ml if "product_size_ml" in provided_fields else stock.product_size_ml
            packaging_size_name = packaging_size_name if ("packaging_size_name" in provided_fields or "packaging_size" in provided_fields) else (stock.packaging_size_name or f"{product_size_ml or 210}ml Standard Box")
            variety = variety.strip() if "variety" in provided_fields else (stock.variety or "Standard/White")
            pieces_per_packet = int(pieces_per_packet if "pieces_per_packet" in provided_fields else (stock.pieces_per_packet or 1))
            packets_per_box_limit = int(
                packets_per_box_limit
                if ("packets_per_box_limit" in provided_fields or "packets_per_box" in provided_fields)
                else (stock.packets_per_box_limit or 1)
            )
        else:
            product_size_ml = int(product_size_ml or 210)
            packaging_size_name = packaging_size_name or f"{product_size_ml}ml Standard Box"
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == factory_id)
                .filter(FinalProductStock.product_size_ml == product_size_ml)
                .filter(sql_func.lower(sql_func.trim(FinalProductStock.variety)) == variety.strip().lower())
                .filter(sql_func.lower(sql_func.trim(FinalProductStock.packaging_size_name)) == packaging_size_name.strip().lower())
                .with_for_update()
                .first()
            )
            if stock is None:
                stock = FinalProductStock(
                    factory_id=factory_id,
                    product_size_ml=product_size_ml,
                    variety=variety,
                    packaging_size_name=packaging_size_name,
                    pieces_per_packet=max(pieces_per_packet, 1),
                    packets_per_box_limit=max(packets_per_box_limit, 1),
                    current_quantity=0,
                    total_boxes=0,
                    loose_packets=0,
                )
                db.add(stock)

        if not product_size_ml:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="product_size_ml is required")
        if not packaging_size_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="packaging_size_name is required")

        stock.product_size_ml = int(product_size_ml)
        stock.variety = variety
        stock.packaging_size_name = packaging_size_name
        stock.pieces_per_packet = max(int(pieces_per_packet or 1), 1)
        stock.packets_per_box_limit = max(int(packets_per_box_limit or 1), 1)
        stock.current_quantity = max(quantity, 0)
        stock.total_boxes = max(quantity, 0)
        stock.loose_packets = max(loose_packets, 0)
        db.flush()
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Variant combination already initialized: {exc}"
            )
        db.refresh(stock)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Final product opening stock core save failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Final product stock save failed: {exc}") from exc

    # Optional dependency/bootstrap work must never break the saved opening stock.
    try:
        poly_inventory = get_or_create_inventory(db, factory_id, f"{stock.product_size_ml}ml Polybag", "Packaging", "pieces")
        box_inventory = get_or_create_inventory(db, factory_id, stock.packaging_size_name, "Packaging", "pieces")
        profile = (
            db.query(PackagingProfile)
            .filter(PackagingProfile.factory_id == factory_id)
            .filter(sql_func.lower(PackagingProfile.profile_name) == stock.packaging_size_name.lower())
            .first()
        )
        if profile is None:
            profile = PackagingProfile(
                factory_id=factory_id,
                profile_name=stock.packaging_size_name,
                product_name=f"{stock.product_size_ml}ml Paper Cup",
                product_name_ml=stock.product_size_ml,
                cup_size_ml=stock.product_size_ml,
                polybag_capacity=stock.pieces_per_packet,
                box_capacity=stock.pieces_per_packet * stock.packets_per_box_limit,
                box_size_name=stock.packaging_size_name,
                cups_per_poly=stock.pieces_per_packet,
                cups_per_polybag=stock.pieces_per_packet,
                polys_per_box=stock.packets_per_box_limit,
                polybags_per_box=stock.packets_per_box_limit,
                box_inventory_id=box_inventory.id,
                poly_inventory_id=poly_inventory.id,
            )
            db.add(profile)
            db.flush()
        finished = (
            db.query(FinishedGoodsStock)
            .filter(FinishedGoodsStock.factory_id == factory_id)
            .filter(FinishedGoodsStock.packaging_profile_id == profile.id)
            .first()
        )
        if finished is None:
            finished = FinishedGoodsStock(
                factory_id=factory_id,
                cup_size_ml=stock.product_size_ml,
                packaging_profile_id=profile.id,
                boxes_available=0,
            )
            db.add(finished)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Optional final-stock packaging bootstrap failed and was suppressed: %s", exc)

    try:
        metric = (
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == factory_id)
            .filter(PackagingMetrics.cup_size_ml == stock.product_size_ml)
            .filter(sql_func.lower(PackagingMetrics.variant_name) == stock.variety.lower())
            .first()
        )
        if metric is None:
            metric = PackagingMetrics(
                factory_id=factory_id,
                cup_size_ml=stock.product_size_ml,
                variant_name=stock.variety,
                kg_per_box=Decimal("10.000"),
                cups_per_box=stock.packets_per_box_limit,
            )
            db.add(metric)
        else:
            metric.cups_per_box = stock.packets_per_box_limit
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Optional packaging metrics sync failed and was suppressed: %s", exc)

    try:
        from routers.inventory import recalculate_and_sync_sku_stock
        recalculate_and_sync_sku_stock(
            db=db,
            factory_id=factory_id,
            product_size_ml=stock.product_size_ml,
            variety=stock.variety,
            packaging_size_name=stock.packaging_size_name,
        )
        db.commit()
        db.refresh(stock)
    except Exception as exc:
        db.rollback()
        logger.exception("Optional final-stock live cache sync failed and was suppressed: %s", exc)
        stock = db.query(FinalProductStock).filter(FinalProductStock.id == stock.id).first()

    try:
        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=factory_id,
            sync_type="onboarding",
            action="insert",
            data=payload,
        )
    except Exception as exc:
        logger.exception("Optional final-stock n8n enqueue failed and was suppressed: %s", exc)

    return FinalProductOpeningStockResponse(
        id=stock.id,
        factory_id=str(stock.factory_id),
        product_size_ml=stock.product_size_ml,
        variety=stock.variety or "Standard/White",
        packaging_size=stock.packaging_size_name,
        packaging_size_name=stock.packaging_size_name,
        pieces_per_packet=stock.pieces_per_packet,
        packets_per_box=stock.packets_per_box_limit,
        current_quantity=stock.current_quantity if stock.current_quantity is not None else 0,
        total_boxes=stock.total_boxes or 0,
        loose_packets=stock.loose_packets or 0,
        packets_per_box_limit=stock.packets_per_box_limit,
    )

@router.get("/workers", response_model=List[OnboardingWorkerSummary])
def list_onboarding_workers(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    workers = (
        db.query(Worker)
        .filter(Worker.factory_id == str(current_user.factory_id))
        .filter(Worker.is_active.is_(True))
        .order_by(Worker.name.asc())
        .all()
    )
    opening_by_worker_id = {
        row.worker_id: int(row.present_days or 0)
        for row in db.query(WorkerOpeningAttendance)
        .filter(WorkerOpeningAttendance.factory_id == str(current_user.factory_id))
        .filter(WorkerOpeningAttendance.worker_id.in_([worker.id for worker in workers] or [0]))
        .all()
    }
    return [_worker_summary(worker, opening_by_worker_id.get(worker.id, 0)) for worker in workers]


@router.get("/machines", response_model=List[OnboardingMachineSummary])
def list_onboarding_machines(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    machines = (
        db.query(Machine)
        .filter(Machine.factory_id == str(current_user.factory_id))
        .order_by(Machine.machine_number.asc().nullslast(), Machine.name.asc().nullslast(), Machine.id.asc())
        .all()
    )
    return [_machine_summary(machine) for machine in machines]


@router.get("/machines/limits", response_model=MachineLimitResponse)
def get_machine_limits(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    usage = get_machine_limit_usage(db, str(current_user.factory_id))
    return MachineLimitResponse(
        used=usage.used,
        limit=usage.limit,
        plan=usage.plan,
        nearing_limit=usage.used >= max(usage.limit - 1, 0),
        limit_reached=usage.used >= usage.limit,
    )


@router.get("/materials")
def list_onboarding_materials(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    return {
        "raw_material_metrics": (
            db.query(RawMaterialMetrics)
            .filter(RawMaterialMetrics.factory_id == factory_id)
            .order_by(RawMaterialMetrics.material_type.asc(), RawMaterialMetrics.size_ml_or_mm.asc())
            .all()
        ),
        "packaging_metrics": (
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == factory_id)
            .order_by(PackagingMetrics.cup_size_ml.asc())
            .all()
        ),
    }


@router.get("/customers", response_model=List[OnboardingCustomerSummary])
def list_onboarding_customers(
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    return (
        db.query(Customer)
        .filter(Customer.factory_id == str(current_user.factory_id))
        .order_by(Customer.name.asc())
        .all()
    )


@router.post("/raw-material/blank", status_code=status.HTTP_201_CREATED)
def create_blank_stock(
    payload: BlankStockCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    total_weight_kg = payload.kg_per_sack * payload.total_sacks
    stock = (
        db.query(BlankStock)
        .filter(BlankStock.factory_id == factory_id)
        .filter(BlankStock.blank_size_ml == payload.size_ml)
        .first()
    )
    if stock is None:
        stock = BlankStock(
            factory_id=factory_id,
            blank_size_ml=payload.size_ml,
            linked_bottom_size_mm=payload.size_ml,
        )
        db.add(stock)

    stock.weight_per_bora_kg = payload.kg_per_sack
    stock.total_boras = payload.total_sacks
    stock.total_qty_kg = total_weight_kg
    db.commit()

    # Synchronize RawMaterialMetrics for Dashboard mapping
    metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.material_type == "Blank")
        .filter(RawMaterialMetrics.size_ml_or_mm == payload.size_ml)
        .first()
    )
    if metric is None:
        metric = RawMaterialMetrics(
            factory_id=factory_id,
            material_type="Blank",
            size_ml_or_mm=payload.size_ml,
            weight_per_sack_kg=payload.kg_per_sack if payload.kg_per_sack > 0 else Decimal("20.000"),
            pieces_per_sack=1000,
        )
        db.add(metric)
    else:
        if payload.kg_per_sack > 0:
            metric.weight_per_sack_kg = payload.kg_per_sack
    db.commit()

    background_tasks.add_task(
        log_activity,
        db=db,
        factory_id=int(current_user.factory_id),
        user_id=current_user.id,
        user_name=current_user.username,
        user_role=current_user.role,
        action_type="RAW_MATERIAL_ADDED",
        action_summary=f"Raw material '{payload.material_name}' added - {total_weight_kg} kg",
        entity_type="raw_material",
        entity_id=stock.id,
        metadata=None,
    )
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=factory_id,
        sync_type="onboarding",
        action="insert",
        data=payload,
    )

    db.refresh(stock)
    return {
        "id": stock.id,
        "material_name": payload.material_name,
        "size_ml": stock.blank_size_ml,
        "kg_per_sack": payload.kg_per_sack,
        "total_sacks": payload.total_sacks,
        "total_weight_kg": stock.total_qty_kg,
    }


@router.post("/raw-material/bottom", status_code=status.HTTP_201_CREATED)
def create_bottom_stock(
    payload: BottomStockCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    calculated_rolls = (payload.rolls_per_bag or 0) * (payload.total_bags or 0)
    calculated_weight_kg = (payload.bag_weight_kg or Decimal("0.000")) * Decimal(payload.total_bags or 0)
    total_rolls = payload.total_rolls if payload.total_rolls is not None else calculated_rolls
    total_weight_kg = payload.total_weight_kg if payload.total_weight_kg is not None else calculated_weight_kg
    stock = (
        db.query(BottomStock)
        .filter(BottomStock.factory_id == factory_id)
        .filter(BottomStock.bottom_size_mm == payload.bottom_size_mm)
        .first()
    )
    if stock is None:
        stock = BottomStock(factory_id=factory_id, bottom_size_mm=payload.bottom_size_mm)
        db.add(stock)

    stock.bag_weight_kg = payload.bag_weight_kg
    stock.rolls_per_bag = payload.rolls_per_bag
    stock.total_bags = payload.total_bags
    stock.total_rolls = total_rolls
    stock.total_weight_kg = total_weight_kg
    stock.total_qty_kg = total_weight_kg

    db.commit()

    # Synchronize RawMaterialMetrics for Dashboard mapping
    metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.material_type == "Bottom")
        .filter(RawMaterialMetrics.size_ml_or_mm == payload.bottom_size_mm)
        .first()
    )
    if metric is None:
        metric = RawMaterialMetrics(
            factory_id=factory_id,
            material_type="Bottom",
            size_ml_or_mm=payload.bottom_size_mm,
            weight_per_sack_kg=payload.bag_weight_kg if (payload.bag_weight_kg and payload.bag_weight_kg > 0) else Decimal("10.000"),
            pieces_per_sack=1,
        )
        db.add(metric)
    else:
        if payload.bag_weight_kg and payload.bag_weight_kg > 0:
            metric.weight_per_sack_kg = payload.bag_weight_kg
    db.commit()

    background_tasks.add_task(
        log_activity,
        db=db,
        factory_id=int(current_user.factory_id),
        user_id=current_user.id,
        user_name=current_user.username,
        user_role=current_user.role,
        action_type="RAW_MATERIAL_ADDED",
        action_summary=f"Raw material '{payload.bottom_size_mm}mm Bottom' added - {total_weight_kg} kg",
        entity_type="raw_material",
        entity_id=stock.id,
        metadata=None,
    )
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=factory_id,
        sync_type="onboarding",
        action="insert",
        data=payload,
    )

    db.refresh(stock)
    return {
        "id": stock.id,
        "bottom_size_mm": stock.bottom_size_mm,
        "bag_weight_kg": stock.bag_weight_kg,
        "rolls_per_bag": stock.rolls_per_bag,
        "total_bags": stock.total_bags,
        "total_rolls": stock.total_rolls,
        "total_weight_kg": stock.total_weight_kg,
    }


@router.post("/raw-material/box", status_code=status.HTTP_201_CREATED)
def create_box_stock(
    payload: BoxStockCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    stock = (
        db.query(BoxStock)
        .filter(BoxStock.factory_id == factory_id)
        .filter(sql_func.lower(BoxStock.packaging_size_name) == payload.box_type.lower())
        .first()
    )
    if stock is None:
        stock = BoxStock(factory_id=factory_id, packaging_size_name=payload.box_type)
        db.add(stock)

    stock.box_type = payload.box_type
    stock.quantity = payload.quantity
    stock.total_boxes = payload.quantity
    stock.price_per_box = payload.price_per_box
    db.commit()
    background_tasks.add_task(
        log_activity,
        db=db,
        factory_id=int(current_user.factory_id),
        user_id=current_user.id,
        user_name=current_user.username,
        user_role=current_user.role,
        action_type="PACKAGING_MATERIAL_ADDED",
        action_summary=f"Packaging material '{payload.box_type}' added",
        entity_type="packaging_material",
        entity_id=stock.id,
        metadata=None,
    )
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=factory_id,
        sync_type="onboarding",
        action="insert",
        data=payload,
    )
    db.refresh(stock)
    return {
        "id": stock.id,
        "box_type": stock.box_type or stock.packaging_size_name,
        "quantity": stock.quantity,
        "price_per_box": stock.price_per_box,
    }


@router.post("/raw-material/plastic", status_code=status.HTTP_201_CREATED)
def create_plastic_stock(
    payload: PlasticStockCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    stock = (
        db.query(PlasticStock)
        .filter(PlasticStock.factory_id == factory_id)
        .filter(sql_func.lower(PlasticStock.plastic_size_name) == payload.plastic_size_name.lower())
        .filter(PlasticStock.cup_size_ml == payload.cup_size_ml)
        .first()
    )
    if stock is None:
        stock = PlasticStock(
            factory_id=factory_id,
            plastic_size_name=payload.plastic_size_name.strip(),
            cup_size_ml=payload.cup_size_ml,
        )
        db.add(stock)

    stock.total_boras = payload.total_boras
    stock.weight_per_bora_kg = payload.weight_per_bora_kg
    stock.price_per_kg = payload.price_per_kg
    db.commit()

    # Synchronize PackagingMetrics for Dashboard mapping
    metric = (
        db.query(PackagingMetrics)
        .filter(PackagingMetrics.factory_id == factory_id)
        .filter(PackagingMetrics.cup_size_ml == payload.cup_size_ml)
        .filter(sql_func.lower(PackagingMetrics.variant_name) == "standard/white")
        .first()
    )
    if metric is None:
        metric = PackagingMetrics(
            factory_id=factory_id,
            cup_size_ml=payload.cup_size_ml,
            variant_name="Standard/White",
            kg_per_box=Decimal(str(payload.weight_per_bora_kg or 0)) if payload.weight_per_bora_kg > 0 else Decimal("10.000"),
            cups_per_box=1000,
        )
        db.add(metric)
    else:
        if payload.weight_per_bora_kg > 0:
            metric.kg_per_box = payload.weight_per_bora_kg
    db.commit()

    background_tasks.add_task(
        log_activity,
        db=db,
        factory_id=int(current_user.factory_id),
        user_id=current_user.id,
        user_name=current_user.username,
        user_role=current_user.role,
        action_type="PACKAGING_MATERIAL_ADDED",
        action_summary=f"Packaging material '{payload.plastic_size_name}' added",
        entity_type="packaging_material",
        entity_id=stock.id,
        metadata=None,
    )
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=factory_id,
        sync_type="onboarding",
        action="insert",
        data=payload,
    )

    db.refresh(stock)
    return {
        "id": stock.id,
        "plastic_size_name": stock.plastic_size_name,
        "cup_size_ml": stock.cup_size_ml,
        "total_boras": stock.total_boras,
        "weight_per_bora_kg": stock.weight_per_bora_kg,
        "total_plastic_kg": stock.total_boras * stock.weight_per_bora_kg,
        "price_per_kg": stock.price_per_kg,
    }


@router.delete("/worker/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_worker(
    worker_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    assert_owner_delete_permission(current_user)
    can_cleanup_null_factory = (current_user.role or "").lower() in {"admin", "owner"}
    worker = (
        db.query(Worker)
        .filter(Worker.id == worker_id)
        .first()
    )
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    if str(worker.factory_id) != str(current_user.factory_id):
        if not (worker.factory_id is None and can_cleanup_null_factory):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    try:
        worker.is_active = False
        _log_onboarding_change(db, int(current_user.factory_id), "Deleted", worker.name)
        db.commit()
        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(current_user.factory_id),
            sync_type="worker",
            action="delete",
            data={"worker_id": worker_id},
        )
    except Exception as e:
        db.rollback()
        logger.warning("Worker delete failed for worker_id=%s factory_id=%s", worker_id, current_user.factory_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Worker delete karte waqt error aaya.",
        ) from e
    return None


@router.delete("/machine/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_machine(
    machine_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner_delete),
    db: Session = Depends(get_db),
):
    machine = (
        db.query(Machine)
        .filter(Machine.factory_id == str(current_user.factory_id))
        .filter(Machine.id == machine_id)
        .first()
    )
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
    machine_spec = machine.machine_name or machine.name or machine.machine_number or f"Machine {machine.id}"
    db.delete(machine)
    _log_onboarding_change(db, int(current_user.factory_id), "Deleted", machine_spec)
    db.commit()
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=str(current_user.factory_id),
        sync_type="onboarding",
        action="delete",
        data={"machine_id": machine_id},
    )
    return None


@router.delete("/raw-material/{raw_material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_raw_material(
    raw_material_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner_delete),
    db: Session = Depends(get_db),
):
    metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == str(current_user.factory_id))
        .filter(RawMaterialMetrics.id == raw_material_id)
        .first()
    )
    if metric is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw material metric not found")
    db.delete(metric)
    db.commit()
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=str(current_user.factory_id),
        sync_type="onboarding",
        action="delete",
        data={"raw_material_id": raw_material_id},
    )
    return None


@router.delete("/customer/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_customer(
    customer_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner_delete),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == str(current_user.factory_id))
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    db.delete(customer)
    db.commit()
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=str(current_user.factory_id),
        sync_type="onboarding",
        action="delete",
        data={"customer_id": customer_id},
    )
    return None


# =============================================================================
# LEVEL 1 ONBOARDING — Factory & Owner
# =============================================================================

@router.post("/step1", response_model=Step1Response)
def onboarding_step1(
    payload: Step1Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    if current_user.factory_id and current_user.factory_id > 0:
        existing = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already linked to a factory",
            )

    factory = Factory(
        name=payload.factory_name.strip(),
        owner_phone_number=current_user.phone_number,
    )
    db.add(factory)
    db.commit()
    db.refresh(factory)

    current_user.factory_id = factory.id
    db.commit()
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=str(factory.id),
        sync_type="onboarding",
        action="insert",
        data=payload,
    )

    return Step1Response(
        message="Factory created successfully",
        factory_id=factory.id,
        factory_name=factory.name,
    )


@router.post("/step1/workers", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
def onboarding_step1_create_worker(
    payload: WorkerCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    worker = (
        db.query(Worker)
        .filter(Worker.factory_id == str(current_user.factory_id))
        .filter(sql_func.lower(Worker.name) == payload.name.strip().lower())
        .first()
    )
    created = worker is None
    if worker is None:
        worker = Worker(factory_id=str(current_user.factory_id), name=payload.name.strip())
        db.add(worker)
        db.flush()

    if payload.phone:
        worker.phone, _ = normalize_phone_number(payload.phone, payload.country_code)
    worker.daily_wages = payload.daily_wages
    worker.duty_hours = payload.duty_hours
    worker.daily_salary = payload.daily_wages
    worker.salary = payload.daily_wages
    worker.shift_hours = payload.duty_hours
    worker.is_active = True
    db.flush()

    if payload.opening_attendance is not None:
        existing_oa = (
            db.query(WorkerOpeningAttendance)
            .filter(WorkerOpeningAttendance.factory_id == str(current_user.factory_id))
            .filter(WorkerOpeningAttendance.worker_id == worker.id)
            .first()
        )
        if existing_oa is not None:
            existing_oa.period_start = payload.opening_attendance.period_start
            existing_oa.period_end = payload.opening_attendance.period_end
            existing_oa.present_days = payload.opening_attendance.present_days
            existing_oa.half_days = payload.opening_attendance.half_days
            existing_oa.absent_days = payload.opening_attendance.absent_days
            existing_oa.paid_leave_days = payload.opening_attendance.paid_leave_days
            existing_oa.overtime_hours = payload.opening_attendance.overtime_hours
            existing_oa.advance_paid = payload.opening_attendance.advance_paid
            existing_oa.deductions = payload.opening_attendance.deductions
            existing_oa.notes = payload.opening_attendance.notes
        else:
            opening_att = WorkerOpeningAttendance(
                factory_id=str(current_user.factory_id),
                worker_id=worker.id,
                period_start=payload.opening_attendance.period_start,
                period_end=payload.opening_attendance.period_end,
                present_days=payload.opening_attendance.present_days,
                half_days=payload.opening_attendance.half_days,
                absent_days=payload.opening_attendance.absent_days,
                paid_leave_days=payload.opening_attendance.paid_leave_days,
                overtime_hours=payload.opening_attendance.overtime_hours,
                advance_paid=payload.opening_attendance.advance_paid,
                deductions=payload.opening_attendance.deductions,
                notes=payload.opening_attendance.notes,
                created_by_user_id=current_user.id,
            )
            db.add(opening_att)

    _log_onboarding_change(db, int(current_user.factory_id), "Added" if created else "Updated", worker.name)
    db.commit()
    db.refresh(worker)
    background_tasks.add_task(
        log_activity,
        db,
        int(current_user.factory_id),
        current_user.id,
        getattr(current_user, "full_name", None) or current_user.username,
        current_user.role,
        "ONBOARDING_UPDATED",
        f"{'Added' if created else 'Updated'} worker {worker.name}",
        "onboarding",
        worker.id,
        {"entity": "worker"},
    )
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=str(current_user.factory_id),
        sync_type="worker",
        action="insert",
        data=payload,
    )
    return worker


# =============================================================================
# LEVEL 2 ONBOARDING — Machine Configuration
# =============================================================================

@router.post("/step2/machines", response_model=Step2Response)
def onboarding_step2_machines(
    payload: Step2Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    check_machine_limit(factory_id, db, requested_count=len(payload.machines))

    machine_specs: list[str] = []
    for item in payload.machines:
        seq = item.machine_sequence_number.strip().upper()
        existing = (
            db.query(Machine)
            .filter(Machine.factory_id == factory_id)
            .filter(sql_func.lower(Machine.machine_sequence_number) == seq.lower())
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Machine sequence {seq} already exists for this factory",
            )

        machine = Machine(
            factory_id=factory_id,
            name=item.name or seq,
            machine_name=item.name or seq,
            machine_type=item.name or "Custom Machine",
            machine_sequence_number=seq,
            cup_size_ml=item.cup_size_ml,
            bottom_size_mm=item.bottom_size_mm,
            speed_cups_per_minute=item.speed_cups_per_minute,
            speed_per_minute=item.speed_cups_per_minute,
            speed_bpm=item.speed_cups_per_minute,
            default_speed=float(item.speed_cups_per_minute or 0),
            can_swap_moulds=item.can_swap_moulds,
        )
        db.add(machine)
        machine_specs.append(machine.name or machine.machine_sequence_number or f"{item.cup_size_ml}ml machine")

    if machine_specs:
        _log_onboarding_change(db, int(factory_id), "Added", ", ".join(machine_specs))
    db.commit()
    background_tasks.add_task(
        log_activity,
        db,
        int(current_user.factory_id),
        current_user.id,
        current_user.full_name or current_user.username,
        current_user.role,
        "ONBOARDING_UPDATED",
        f"Added {len(payload.machines)} machine setup entries",
        "onboarding",
        None,
        {"entity": "machine", "machines": machine_specs},
    )
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=factory_id,
        sync_type="onboarding",
        action="insert",
        data=payload,
    )
    return Step2Response(
        message="Machines configured successfully",
        factory_id=factory_id,
        machines_saved=len(payload.machines),
    )


# =============================================================================
# LEVEL 3 ONBOARDING — Raw Material & Packaging Metrics
# =============================================================================

@router.post("/step3/materials", response_model=Step3Response)
def onboarding_step3_materials(
    payload: Step3Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)

    raw_saved = 0
    for item in payload.raw_material_metrics:
        metric = (
            db.query(RawMaterialMetrics)
            .filter(RawMaterialMetrics.factory_id == factory_id)
            .filter(RawMaterialMetrics.material_type == item.material_type)
            .filter(RawMaterialMetrics.size_ml_or_mm == item.size_ml_or_mm)
            .first()
        )
        if metric is None:
            metric = RawMaterialMetrics(
                factory_id=factory_id,
                material_type=item.material_type,
                size_ml_or_mm=item.size_ml_or_mm,
            )
            db.add(metric)

        metric.weight_per_sack_kg = item.weight_per_sack_kg
        metric.pieces_per_sack = item.pieces_per_sack
        total_weight_kg = item.total_weight_kg or (item.weight_per_sack_kg * item.total_sacks)
        if item.material_type == "Blank":
            stock = (
                db.query(BlankStock)
                .filter(BlankStock.factory_id == factory_id)
                .filter(BlankStock.blank_size_ml == item.size_ml_or_mm)
                .first()
            )
            if stock is None:
                stock = BlankStock(
                    factory_id=factory_id,
                    blank_size_ml=item.size_ml_or_mm,
                    linked_bottom_size_mm=item.size_ml_or_mm,
                    total_qty_kg=Decimal("0.000"),
                )
                db.add(stock)
            stock.total_qty_kg = total_weight_kg
        if item.material_type == "Bottom":
            stock = (
                db.query(BottomStock)
                .filter(BottomStock.factory_id == factory_id)
                .filter(BottomStock.bottom_size_mm == item.size_ml_or_mm)
                .first()
            )
            if stock is None:
                stock = BottomStock(
                    factory_id=factory_id,
                    bottom_size_mm=item.size_ml_or_mm,
                    total_qty_kg=Decimal("0.000"),
                    total_weight_kg=Decimal("0.000"),
                )
                db.add(stock)
            stock.total_qty_kg = total_weight_kg
            stock.total_weight_kg = total_weight_kg
        raw_saved += 1

    pack_saved = 0
    for item in payload.packaging_metrics:
        variety = getattr(item, "variety", "Standard/White") or "Standard/White"
        metric = (
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == factory_id)
            .filter(PackagingMetrics.cup_size_ml == item.cup_size_ml)
            .filter(sql_func.lower(PackagingMetrics.variant_name) == variety.lower())
            .first()
        )
        if metric is None:
            metric = PackagingMetrics(
                factory_id=factory_id,
                cup_size_ml=item.cup_size_ml,
                variant_name=variety,
            )
            db.add(metric)

        metric.kg_per_box = item.kg_per_box
        metric.cups_per_box = item.cups_per_box
        packaging_size_name = f"{item.cup_size_ml}ml Standard Box"
        box_stock = (
            db.query(BoxStock)
            .filter(BoxStock.factory_id == factory_id)
            .filter(sql_func.lower(BoxStock.packaging_size_name) == packaging_size_name.lower())
            .first()
        )
        if box_stock is None:
            db.add(
                BoxStock(
                    factory_id=factory_id,
                    packaging_size_name=packaging_size_name,
                    total_boxes=0,
                )
            )

        final_stock = (
            db.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == factory_id)
            .filter(FinalProductStock.product_size_ml == item.cup_size_ml)
            .filter(sql_func.lower(FinalProductStock.packaging_size_name) == packaging_size_name.lower())
            .first()
        )
        if final_stock is None:
            db.add(
                FinalProductStock(
                    factory_id=factory_id,
                    product_size_ml=item.cup_size_ml,
                    packaging_size_name=packaging_size_name,
                    current_quantity=0,
                    total_boxes=0,
                    loose_packets=0,
                    packets_per_box_limit=item.cups_per_box,
                )
            )
        pack_saved += 1

    db.commit()
    if raw_saved:
        background_tasks.add_task(
            log_activity,
            db=db,
            factory_id=int(current_user.factory_id),
            user_id=current_user.id,
            user_name=current_user.username,
            user_role=current_user.role,
            action_type="RAW_MATERIAL_ADDED",
            action_summary=f"Raw material metrics updated - {raw_saved} entries",
            entity_type="raw_material",
            entity_id=None,
            metadata={"raw_material_metrics_saved": raw_saved},
        )
    if pack_saved:
        background_tasks.add_task(
            log_activity,
            db=db,
            factory_id=int(current_user.factory_id),
            user_id=current_user.id,
            user_name=current_user.username,
            user_role=current_user.role,
            action_type="PACKAGING_MATERIAL_ADDED",
            action_summary=f"Packaging material metrics updated - {pack_saved} entries",
            entity_type="packaging_material",
            entity_id=None,
            metadata={"packaging_metrics_saved": pack_saved},
        )
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=factory_id,
        sync_type="onboarding",
        action="insert",
        data=payload,
    )
    return Step3Response(
        message="Material and packaging metrics saved successfully",
        factory_id=factory_id,
        raw_material_metrics_saved=raw_saved,
        packaging_metrics_saved=pack_saved,
    )


# =============================================================================
# LEGACY BULK ONBOARDING (Backward Compatible)
# =============================================================================

@router.post("/complete", response_model=OnboardingCompleteResponse)
def complete_onboarding(
    payload: OnboardingCompleteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)

    try:
        machine_names = []
        for machine_payload in payload.machines:
            upsert_machine(db, factory_id, machine_payload)
            machine_names.append(machine_payload.name.strip())

        for material_payload in payload.raw_materials:
            material = upsert_raw_material(db, factory_id, material_payload)
            upsert_inventory_from_raw_material(db, factory_id, material)

        for profile_payload in payload.packaging_profiles:
            upsert_packaging_profile(db, factory_id, profile_payload)

        for yield_payload in payload.material_yields:
            upsert_material_yield(db, factory_id, yield_payload)

        upsert_costing_master(db, factory_id, payload.costing_master)

        worker_names = []
        for worker_payload in payload.workers:
            upsert_worker(db, factory_id, worker_payload)
            worker_names.append(worker_payload.name.strip())

        for customer_payload in payload.customers:
            upsert_customer(db, factory_id, customer_payload)

        if machine_names:
            _log_onboarding_change(db, int(factory_id), "Updated", ", ".join(machine_names))
        if worker_names:
            _log_onboarding_change(db, int(factory_id), "Updated", ", ".join(worker_names))
        db.commit()
        if payload.raw_materials:
            background_tasks.add_task(
                log_activity,
                db=db,
                factory_id=int(current_user.factory_id),
                user_id=current_user.id,
                user_name=current_user.username,
                user_role=current_user.role,
                action_type="RAW_MATERIAL_ADDED",
                action_summary=f"Raw materials updated during onboarding - {len(payload.raw_materials)} entries",
                entity_type="raw_material",
                entity_id=None,
                metadata={"raw_materials_saved": len(payload.raw_materials)},
            )
        if payload.packaging_profiles:
            background_tasks.add_task(
                log_activity,
                db=db,
                factory_id=int(current_user.factory_id),
                user_id=current_user.id,
                user_name=current_user.username,
                user_role=current_user.role,
                action_type="PACKAGING_MATERIAL_ADDED",
                action_summary=f"Packaging profiles updated during onboarding - {len(payload.packaging_profiles)} entries",
                entity_type="packaging_material",
                entity_id=None,
                metadata={"packaging_profiles_saved": len(payload.packaging_profiles)},
            )
        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=factory_id,
            sync_type="onboarding",
            action="insert",
            data=payload,
        )
        return OnboardingCompleteResponse(
            message="Factory onboarding completed successfully",
            factory_id=factory_id,
            machines_saved=len(payload.machines),
            raw_materials_saved=len(payload.raw_materials),
            packaging_profiles_saved=len(payload.packaging_profiles),
            material_yields_saved=len(payload.material_yields),
            workers_saved=len(payload.workers),
            customers_saved=len(payload.customers),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Onboarding failed and was rolled back: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Legacy Upsert Helpers
# ---------------------------------------------------------------------------

def upsert_machine(db: Session, factory_id: int, payload: MachinePayload) -> Machine:
    name = payload.name.strip()
    machine = (
        db.query(Machine)
        .filter(Machine.factory_id == factory_id)
        .filter(sql_func.lower(Machine.name) == name.lower())
        .first()
    )
    if machine is None:
        machine = Machine(factory_id=factory_id, name=name)
        db.add(machine)

    machine.speed_bpm = payload.speed_bpm
    machine.speed_per_minute = payload.speed_bpm
    machine.current_mould_size = payload.current_mould_size
    machine.default_mould_size = payload.current_mould_size
    machine.current_bottom_size = payload.current_bottom_size
    machine.bottom_size = payload.current_bottom_size
    machine.can_swap_moulds = payload.can_swap_moulds
    return machine


def upsert_raw_material(db: Session, factory_id: int, payload: RawMaterialPayload) -> RawMaterial:
    material_name = payload.name or build_raw_material_name(payload)
    material_type = payload.type
    unit = payload.unit or ("pieces" if material_type in {"Polybag", "Carton Box"} else "kg")
    size_name = f"{payload.size_ml}ml" if payload.size_ml else None

    raw_material = (
        db.query(RawMaterial)
        .filter(RawMaterial.factory_id == factory_id)
        .filter(sql_func.lower(RawMaterial.name) == material_name.lower())
        .filter(RawMaterial.material_type == material_type)
        .filter(RawMaterial.size_name == size_name)
        .first()
    )
    if raw_material is None:
        raw_material = RawMaterial(
            factory_id=factory_id,
            name=material_name,
            material_type=material_type,
            size_name=size_name,
        )
        db.add(raw_material)

    raw_material.type = material_type
    raw_material.size_ml = payload.size_ml
    raw_material.gsm = payload.gsm
    raw_material.unit = unit
    raw_material.opening_stock = payload.stock_quantity
    raw_material.current_stock = payload.stock_quantity
    raw_material.stock_quantity = payload.stock_quantity
    raw_material.price_per_unit = payload.price_per_unit
    return raw_material


def build_raw_material_name(payload: RawMaterialPayload) -> str:
    parts = [payload.type]
    if payload.size_ml:
        parts.append(f"{payload.size_ml}ml")
    if payload.gsm:
        parts.append(f"{payload.gsm}gsm")
    return " ".join(parts)


def upsert_inventory_from_raw_material(db: Session, factory_id: int, raw_material: RawMaterial) -> Inventory:
    category = "Packaging" if raw_material.material_type in {"Polybag", "Carton Box"} else "Raw"
    item = get_or_create_inventory(db, factory_id, raw_material.name, category, raw_material.unit)
    item.quantity = raw_material.stock_quantity
    item.price_per_unit = raw_material.price_per_unit
    return item


def upsert_packaging_profile(
    db: Session,
    factory_id: int,
    payload: PackagingProfilePayload,
) -> PackagingProfile:
    product_name = f"{payload.product_name_ml}ml Paper Cup"
    profile_name = f"{payload.product_name_ml}ml Standard Box"
    poly_inventory = get_or_create_inventory(db, factory_id, f"{payload.product_name_ml}ml Polybag", "Packaging", "pieces")
    box_inventory = get_or_create_inventory(db, factory_id, payload.box_size_name or f"{payload.product_name_ml}ml Carton Box", "Packaging", "pieces")

    profile = (
        db.query(PackagingProfile)
        .filter(PackagingProfile.factory_id == factory_id)
        .filter(sql_func.lower(PackagingProfile.profile_name) == profile_name.lower())
        .first()
    )
    if profile is None:
        profile = PackagingProfile(factory_id=factory_id, profile_name=profile_name)
        db.add(profile)

    cups_per_box = payload.cups_per_polybag * payload.polybags_per_box
    profile.product_name = product_name
    profile.product_name_ml = payload.product_name_ml
    profile.cup_size_ml = payload.product_name_ml
    profile.polybag_capacity = payload.cups_per_polybag
    profile.box_capacity = cups_per_box
    profile.box_size_name = payload.box_size_name
    profile.cups_per_poly = payload.cups_per_polybag
    profile.cups_per_polybag = payload.cups_per_polybag
    profile.polys_per_box = payload.polybags_per_box
    profile.polybags_per_box = payload.polybags_per_box
    profile.box_inventory_id = box_inventory.id
    profile.poly_inventory_id = poly_inventory.id
    return profile


def upsert_material_yield(db: Session, factory_id: int, payload: MaterialYieldPayload) -> MaterialYield:
    material_yield = (
        db.query(MaterialYield)
        .filter(MaterialYield.factory_id == factory_id)
        .filter(MaterialYield.material_type == payload.material_type)
        .filter(MaterialYield.size_ml == payload.size_ml)
        .filter(MaterialYield.gsm == payload.gsm)
        .first()
    )
    if material_yield is None:
        material_yield = MaterialYield(
            factory_id=factory_id,
            material_type=payload.material_type,
            size_ml=payload.size_ml,
            gsm=payload.gsm,
        )
        db.add(material_yield)

    material_yield.pieces_per_kg = payload.pieces_per_kg
    return material_yield


def upsert_costing_master(db: Session, factory_id: int, payload) -> CostingMaster:
    costing = db.query(CostingMaster).filter(CostingMaster.factory_id == factory_id).first()
    if costing is None:
        costing = CostingMaster(factory_id=factory_id)
        db.add(costing)

    costing.paper_price_per_kg = payload.paper_price_per_kg
    costing.bottom_roll_price_per_kg = payload.bottom_roll_price_per_kg
    costing.polybag_price = payload.polybag_price
    costing.carton_price = payload.carton_price
    costing.labour_cost_per_box = payload.labour_cost_per_box
    costing.electricity_cost_per_box = payload.electricity_cost_per_box
    return costing


def upsert_worker(db: Session, factory_id: int, payload: WorkerPayload) -> Worker:
    worker = (
        db.query(Worker)
        .filter(Worker.factory_id == factory_id)
        .filter(sql_func.lower(Worker.name) == payload.name.lower())
        .first()
    )
    if worker is None:
        worker = Worker(factory_id=factory_id, name=payload.name.strip())
        db.add(worker)

    worker.is_active = True
    worker.daily_salary = payload.daily_salary
    worker.salary = payload.daily_salary
    worker.shift_type = payload.shift_type
    worker.shift_timing = payload.shift_type
    return worker


def upsert_customer(db: Session, factory_id: int, payload: CustomerPayload) -> Customer:
    customer_name = (payload.name or payload.firm_name).strip()
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == factory_id)
        .filter(sql_func.lower(Customer.name) == customer_name.lower())
        .first()
    )
    if customer is None:
        customer = Customer(factory_id=factory_id, name=customer_name)
        db.add(customer)

    customer.firm_name = payload.firm_name.strip()
    customer.contact_number = payload.contact_number
    customer.pending_balance = payload.pending_balance
    customer.pending_dues = float(payload.pending_balance)
    customer.balance_amount = payload.pending_balance
    return customer


def get_or_create_inventory(db: Session, factory_id: int, item_name: str, category: str, unit: str) -> Inventory:
    db.flush()
    item = (
        db.query(Inventory)
        .filter(Inventory.factory_id == factory_id)
        .filter(sql_func.lower(Inventory.item_name) == item_name.lower())
        .first()
    )
    if item is None:
        item = Inventory(
            factory_id=factory_id,
            item_name=item_name.strip(),
            category=category,
            unit=unit,
            quantity=Decimal("0.000"),
            price_per_unit=Decimal("0.00"),
        )
        db.add(item)
        db.flush()
    return item


@router.delete("/entry/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_entry(
    entry_id: str,
    background_tasks: BackgroundTasks,
    type: Optional[str] = None,
    current_user: User = Depends(require_owner_delete),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    
    # Try to parse string ID containing prefix
    try:
        actual_id = int(entry_id)
    except ValueError:
        parts = entry_id.split("-")
        if len(parts) == 2:
            type = parts[0]
            try:
                actual_id = int(parts[1])
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid entry_id format")
        else:
            raise HTTPException(status_code=400, detail="Invalid entry_id format")

    if not type:
        type = "final"
        
    type_lower = type.lower()
    
    def trigger_delete_sync():
        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(factory_id),
            sync_type="onboarding",
            action="delete",
            data={"entry_id": actual_id, "type": type_lower}
        )
    
    try:
        if type_lower in ("final", "final product", "cups", "final-product"):
            entry = db.query(FinalProductStock).filter(FinalProductStock.id == actual_id, FinalProductStock.factory_id == factory_id).first()
            if entry:
                product_size_ml = entry.product_size_ml
                variety = entry.variety
                packaging_size_name = entry.packaging_size_name
                
                db.delete(entry)
                db.flush()
                
                # Recalculate dynamic live stock balance and sync caches
                from routers.inventory import recalculate_and_sync_sku_stock
                recalculate_and_sync_sku_stock(
                    db=db,
                    factory_id=factory_id,
                    product_size_ml=product_size_ml,
                    variety=variety,
                    packaging_size_name=packaging_size_name,
                )
                db.commit()
                trigger_delete_sync()
                return None
        elif type_lower in ("blank", "blankstock"):
            entry = db.query(BlankStock).filter(BlankStock.id == actual_id, BlankStock.factory_id == factory_id).first()
            if entry:
                db.delete(entry)
                db.commit()
                trigger_delete_sync()
                return None
        elif type_lower in ("bottom", "bottomstock"):
            entry = db.query(BottomStock).filter(BottomStock.id == actual_id, BottomStock.factory_id == factory_id).first()
            if entry:
                db.delete(entry)
                db.commit()
                trigger_delete_sync()
                return None
        elif type_lower in ("box", "boxstock", "carton box", "carton", "packaging", "inventory"):
            entry = db.query(BoxStock).filter(BoxStock.id == actual_id, BoxStock.factory_id == factory_id).first()
            if entry:
                db.delete(entry)
                db.commit()
                trigger_delete_sync()
                return None
            inv_entry = db.query(Inventory).filter(Inventory.id == actual_id, Inventory.factory_id == factory_id).first()
            if inv_entry:
                profiles = db.query(PackagingProfile).filter(
                    (PackagingProfile.box_inventory_id == actual_id) |
                    (PackagingProfile.poly_inventory_id == actual_id)
                ).all()

                from models import DailyProduction
                has_production_links = False
                for profile in profiles:
                    linked_log = db.query(DailyProduction).filter(
                        DailyProduction.factory_id == factory_id,
                        sql_func.lower(DailyProduction.packaging_size_name) == profile.profile_name.lower(),
                    ).first()
                    if linked_log:
                        has_production_links = True
                        break

                if has_production_links:
                    inv_entry.item_name = f"[DELETED] {inv_entry.item_name}"
                    db.add(inv_entry)
                else:
                    for profile in profiles:
                        db.query(FinishedGoodsStock).filter(FinishedGoodsStock.packaging_profile_id == profile.id).delete()
                        db.delete(profile)
                    db.delete(inv_entry)
                db.commit()
                trigger_delete_sync()
                return None
        elif type_lower in ("plastic", "plasticstock", "polybag"):
            entry = db.query(PlasticStock).filter(PlasticStock.id == actual_id, PlasticStock.factory_id == factory_id).first()
            if entry:
                db.delete(entry)
                db.commit()
                trigger_delete_sync()
                return None
        elif type_lower in ("polybag", "polybagstock"):
            entry = db.query(PolybagStock).filter(PolybagStock.id == actual_id, PolybagStock.factory_id == factory_id).first()
            if entry:
                db.delete(entry)
                db.commit()
                trigger_delete_sync()
                return None
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete entry: {exc}"
        )
        
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Onboarding entry of type '{type}' with ID {actual_id} not found")


@router.delete("/v1/onboarding/items/{item_id}")
@v1_router.delete("/items/{item_id}")
def delete_onboarding_item(
    item_id: int,
    type: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_owner_delete),
    db: Session = Depends(get_db)
):
    factory_id = str(current_user.factory_id)
    type_lower = type.lower()
    
    try:
        if type_lower in ("blank", "blankstock"):
            entry = db.query(BlankStock).filter(BlankStock.id == item_id, BlankStock.factory_id == factory_id).first()
            if not entry:
                raise HTTPException(status_code=404, detail="Blank stock not found")
            db.delete(entry)
            db.commit()
            
        elif type_lower in ("bottom", "bottomstock"):
            entry = db.query(BottomStock).filter(BottomStock.id == item_id, BottomStock.factory_id == factory_id).first()
            if not entry:
                raise HTTPException(status_code=404, detail="Bottom stock not found")
            db.delete(entry)
            db.commit()
            
        elif type_lower in ("box", "boxstock", "carton box", "carton", "packaging", "inventory"):
            # Check BoxStock first
            entry = db.query(BoxStock).filter(BoxStock.id == item_id, BoxStock.factory_id == factory_id).first()
            if entry:
                db.delete(entry)
                db.commit()
            else:
                # Check standard Inventory table (Corrugated Box variants)
                inv_entry = db.query(Inventory).filter(Inventory.id == item_id, Inventory.factory_id == factory_id).first()
                if not inv_entry:
                    raise HTTPException(status_code=404, detail="Item not found")
                
                # Deletion constraints: override any hardcoded constraints blocking "Standard" boxes 
                # Check for dependencies in PackagingProfile
                profiles = db.query(PackagingProfile).filter(
                    (PackagingProfile.box_inventory_id == item_id) |
                    (PackagingProfile.poly_inventory_id == item_id)
                ).all()
                
                can_hard_delete = True
                from models import DailyProduction
                for p in profiles:
                    # check if active production logs exist
                    has_logs = db.query(DailyProduction).filter(
                        (DailyProduction.factory_id == factory_id) &
                        (sql_func.lower(DailyProduction.packaging_size_name) == p.profile_name.lower())
                    ).first()
                    if has_logs:
                        can_hard_delete = False
                        break
                
                if can_hard_delete:
                    for p in profiles:
                        db.query(FinishedGoodsStock).filter(FinishedGoodsStock.packaging_profile_id == p.id).delete()
                        db.delete(p)
                    db.flush()
                    
                    # Direct SQL Deletion against the primary table identifier string
                    from sqlalchemy import text
                    db.execute(
                        text("DELETE FROM inventory WHERE factory_id = :factory_id AND id = :item_id"),
                        {"factory_id": factory_id, "item_id": item_id}
                    )
                    db.commit()
                else:
                    # Apply soft-delete status by renaming mapping
                    inv_entry.item_name = f"[DELETED] {inv_entry.item_name}"
                    db.commit()
            
        elif type_lower in ("plastic", "plasticstock", "polybag"):
            entry = db.query(PlasticStock).filter(PlasticStock.id == item_id, PlasticStock.factory_id == factory_id).first()
            if not entry:
                raise HTTPException(status_code=404, detail="Plastic stock not found")
            db.delete(entry)
            db.commit()
            
        elif type_lower in ("polybag", "polybagstock"):
            entry = db.query(PolybagStock).filter(PolybagStock.id == item_id, PolybagStock.factory_id == factory_id).first()
            if not entry:
                raise HTTPException(status_code=404, detail="Polybag stock not found")
            db.delete(entry)
            db.commit()
            
        else:
            raise HTTPException(status_code=400, detail="Invalid stock type")
            
        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(factory_id),
            sync_type="onboarding",
            action="delete",
            data={"entry_id": item_id, "type": type_lower}
        )
        return {"message": "Item deleted successfully"}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete item because it contains active data associations: {exc}"
        )
