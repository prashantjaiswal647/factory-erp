from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Auth Schemas
# ---------------------------------------------------------------------------

class OTPRequest(BaseModel):
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone_number: str = Field(..., min_length=5, max_length=50)


class OTPVerifyRequest(BaseModel):
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone_number: str = Field(..., min_length=5, max_length=50)
    otp: str = Field(..., min_length=4, max_length=10)
    password: str = Field(..., min_length=4, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    phone_number: str
    role: str
    factory_id: Optional[int] = None


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    phone_number: Optional[str] = None
    role: str
    factory_id: int
    is_verified: bool


# ---------------------------------------------------------------------------
# Onboarding Schemas
# ---------------------------------------------------------------------------

class Step1Request(BaseModel):
    factory_name: str = Field(..., min_length=1, max_length=255)


class Step1Response(BaseModel):
    message: str
    factory_id: int
    factory_name: str


class Step2MachineItem(BaseModel):
    machine_sequence_number: str = Field(..., min_length=1, max_length=50)
    name: Optional[str] = Field(default=None, max_length=255)
    cup_size_ml: int = Field(..., gt=0)
    bottom_size_mm: int = Field(..., gt=0)
    speed_cups_per_minute: int = Field(..., ge=0)
    can_swap_moulds: bool = False


class Step2Request(BaseModel):
    machines: List[Step2MachineItem] = Field(..., min_length=1)


class Step2Response(BaseModel):
    message: str
    factory_id: int
    machines_saved: int


class Step3RawMaterialMetricItem(BaseModel):
    material_type: str = Field(..., pattern="^(Blank|Bottom)$")
    size: Optional[int] = Field(default=None, gt=0)
    size_ml_or_mm: Optional[int] = Field(default=None, gt=0)
    kg_per_sack: Optional[Decimal] = Field(default=None, gt=0)
    weight_per_sack_kg: Optional[Decimal] = Field(default=None, gt=0)
    total_sacks: Decimal = Field(default=Decimal("0"), ge=0)
    total_weight_kg: Optional[Decimal] = Field(default=None, ge=0)
    pieces_per_sack: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def normalize_material_fields(self):
        if self.size_ml_or_mm is None:
            self.size_ml_or_mm = self.size
        if self.weight_per_sack_kg is None:
            self.weight_per_sack_kg = self.kg_per_sack
        if self.size_ml_or_mm is None:
            raise ValueError("size is required")
        if self.weight_per_sack_kg is None:
            raise ValueError("kg_per_sack is required")
        calculated_weight = self.weight_per_sack_kg * self.total_sacks
        if self.total_weight_kg is None:
            self.total_weight_kg = calculated_weight
        return self


class Step3PackagingMetricItem(BaseModel):
    cup_size_ml: int = Field(..., gt=0)
    kg_per_box: Decimal = Field(default=Decimal("0.000"), ge=0)
    cups_per_box: int = Field(..., gt=0)


class Step3Request(BaseModel):
    raw_material_metrics: List[Step3RawMaterialMetricItem] = Field(default_factory=list)
    packaging_metrics: List[Step3PackagingMetricItem] = Field(default_factory=list)


class Step3Response(BaseModel):
    message: str
    factory_id: int
    raw_material_metrics_saved: int
    packaging_metrics_saved: int


# ---------------------------------------------------------------------------
# Calculator Schemas
# ---------------------------------------------------------------------------

class CalculateCostRequest(BaseModel):
    blank_metric_id: int = Field(..., gt=0)
    bottom_metric_id: int = Field(..., gt=0)
    packaging_metric_id: int = Field(..., gt=0)
    selling_price_per_box: Decimal = Field(..., ge=0)


class CalculateCostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    product_cup_size_ml: int
    total_cost_price_per_box: Decimal
    cost_per_piece: Decimal
    selling_price_per_box: Decimal
    selling_price_per_piece: Decimal
    profit_per_box: Decimal
    profit_per_piece: Decimal


class DailyCapacityResponse(BaseModel):
    machine_id: int
    machine_sequence_number: str
    speed_cups_per_minute: int
    shift_hours: float
    total_cups_per_day: int
    estimated_blank_sacks_needed: Decimal
    estimated_bottom_sacks_needed: Decimal


# ---------------------------------------------------------------------------
# Legacy Onboarding Compatibility Schemas
# ---------------------------------------------------------------------------

class MachinePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    speed_bpm: int = Field(..., ge=0)
    current_mould_size: Optional[str] = Field(default=None, max_length=100)
    current_bottom_size: Optional[str] = Field(default=None, max_length=100)
    can_swap_moulds: bool = False


class RawMaterialPayload(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    type: str = Field(..., pattern="^(Paper Blank|Bottom Roll|Polybag|Carton Box)$")
    size_ml: Optional[int] = Field(default=None, gt=0)
    gsm: Optional[int] = Field(default=None, gt=0)
    stock_quantity: Decimal = Field(default=Decimal("0.000"), ge=0)
    price_per_unit: Decimal = Field(default=Decimal("0.00"), ge=0)
    unit: Optional[str] = Field(default=None, pattern="^(kg|pieces)$")


class PackagingProfilePayload(BaseModel):
    product_name_ml: int = Field(..., gt=0)
    cups_per_polybag: int = Field(..., gt=0)
    polybags_per_box: int = Field(..., gt=0)
    box_size_name: Optional[str] = Field(default=None, max_length=100)


class MaterialYieldPayload(BaseModel):
    material_type: str = Field(..., pattern="^(Blank|Bottom)$")
    size_ml: int = Field(..., gt=0)
    gsm: Optional[int] = Field(default=None, gt=0)
    pieces_per_kg: Decimal = Field(..., gt=0)


class CostingMasterPayload(BaseModel):
    paper_price_per_kg: Decimal = Field(default=Decimal("0.00"), ge=0)
    bottom_roll_price_per_kg: Decimal = Field(default=Decimal("0.00"), ge=0)
    polybag_price: Decimal = Field(default=Decimal("0.0000"), ge=0)
    carton_price: Decimal = Field(default=Decimal("0.0000"), ge=0)
    labour_cost_per_box: Decimal = Field(default=Decimal("0.00"), ge=0)
    electricity_cost_per_box: Decimal = Field(default=Decimal("0.00"), ge=0)


class WorkerPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    daily_salary: Decimal = Field(default=Decimal("0.00"), ge=0)
    shift_type: Optional[str] = Field(default=None, max_length=100)


class CustomerPayload(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    firm_name: str = Field(..., min_length=1, max_length=255)
    contact_number: Optional[str] = Field(default=None, max_length=50)
    pending_balance: Decimal = Field(default=Decimal("0.00"), ge=0)


class OnboardingCompleteRequest(BaseModel):
    machines: List[MachinePayload] = Field(default_factory=list)
    raw_materials: List[RawMaterialPayload] = Field(default_factory=list)
    packaging_profiles: List[PackagingProfilePayload] = Field(default_factory=list)
    material_yields: List[MaterialYieldPayload] = Field(default_factory=list)
    costing_master: CostingMasterPayload = Field(default_factory=CostingMasterPayload)
    workers: List[WorkerPayload] = Field(default_factory=list)
    customers: List[CustomerPayload] = Field(default_factory=list)
    opening_finished_goods: List[dict] = Field(default_factory=list)


class OnboardingCompleteResponse(BaseModel):
    message: str
    factory_id: int
    machines_saved: int
    raw_materials_saved: int
    packaging_profiles_saved: int
    material_yields_saved: int
    workers_saved: int
    customers_saved: int


# ---------------------------------------------------------------------------
# Phase 1 Tenant Setup Schemas
# ---------------------------------------------------------------------------

class FactoryInfoCreate(BaseModel):
    factory_name: str = Field(..., min_length=1, max_length=255)


class FactoryInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_name: Optional[str] = None
    owner_id: Optional[int] = None


class MachineCreate(BaseModel):
    machine_type: str = Field(..., pattern="^(Paper Cup|Dona|Paper Bag)$")
    machine_number: str = Field(..., min_length=1, max_length=50)
    mould_size_ml: int = Field(..., gt=0)
    bottom_size_mm: int = Field(..., gt=0)
    speed_per_minute: int = Field(..., ge=0)
    machine_name: Optional[str] = Field(default=None, max_length=255)


class MachineUpdate(BaseModel):
    machine_type: Optional[str] = Field(default=None, pattern="^(Paper Cup|Dona|Paper Bag)$")
    machine_number: Optional[str] = Field(default=None, min_length=1, max_length=50)
    mould_size_ml: Optional[int] = Field(default=None, gt=0)
    bottom_size_mm: Optional[int] = Field(default=None, gt=0)
    speed_per_minute: Optional[int] = Field(default=None, ge=0)
    machine_name: Optional[str] = Field(default=None, max_length=255)


class MachineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    machine_type: str
    machine_number: Optional[str] = None
    mould_size_ml: Optional[int] = None
    bottom_size_mm: Optional[int] = None
    speed_per_minute: int
    machine_name: Optional[str] = None


class BlankBatchInput(BaseModel):
    blank_size_ml: int = Field(..., gt=0)
    weight_per_sack: Decimal = Field(..., gt=0)
    total_sacks: int = Field(..., gt=0)


class BlankStockBatchCreate(BaseModel):
    linked_bottom_size_mm: int = Field(..., gt=0)
    batches: List[BlankBatchInput] = Field(..., min_length=1)


class BlankStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    blank_size_ml: int
    linked_bottom_size_mm: int
    total_qty_kg: Decimal


class BottomStockCreate(BaseModel):
    bottom_size_mm: int = Field(..., gt=0)
    bag_weight_kg: Optional[float] = Field(default=None, ge=0)
    rolls_per_bag: Optional[int] = Field(default=None, ge=0)
    total_bags: Optional[int] = Field(default=None, ge=0)
    total_rolls: Optional[int] = Field(default=None, ge=0)
    total_weight_kg: Optional[float] = Field(default=None, ge=0)
    total_qty_kg: Decimal = Field(default=Decimal("0.000"), ge=0)


class BottomStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    bottom_size_mm: int
    total_qty_kg: Decimal


class BoxStockCreate(BaseModel):
    box_type: str = Field(..., min_length=1, max_length=100)
    quantity: Optional[int] = Field(default=None, ge=0)
    box_quantity: Optional[int] = Field(default=None, ge=0)
    price_per_box: float = Field(..., ge=0)

    @model_validator(mode="before")
    @classmethod
    def populate_quantity(cls, data):
        if isinstance(data, dict):
            if "box_quantity" in data and "quantity" not in data:
                data["quantity"] = data["box_quantity"]
            elif "quantity" in data and "box_quantity" not in data:
                data["box_quantity"] = data["quantity"]
            if data.get("quantity") is None and data.get("box_quantity") is None:
                data["quantity"] = 0
                data["box_quantity"] = 0
        return data


class PlasticStockCreate(BaseModel):
    plastic_size_name: str = Field(..., min_length=1, max_length=100)
    cup_size_ml: int = Field(..., gt=0)
    total_boras: int = Field(..., ge=0)
    weight_per_bora_kg: float = Field(..., ge=0)
    price_per_kg: float = Field(..., ge=0)


class BoxStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    packaging_size_name: str
    total_boxes: int


class PolybagStockCreate(BaseModel):
    packaging_size_name: str = Field(..., min_length=1, max_length=100)
    total_packets: int = Field(..., ge=0)


class PolybagStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    packaging_size_name: str
    total_packets: int


# ---------------------------------------------------------------------------
# Worker Opening Attendance Schemas
# ---------------------------------------------------------------------------

class OpeningAttendanceCreate(BaseModel):
    period_start: date
    period_end: date
    present_days: float = 0.0
    half_days: float = 0.0
    absent_days: float = 0.0
    paid_leave_days: float = 0.0
    overtime_hours: float = 0.0
    advance_paid: float = 0.0
    deductions: float = 0.0
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_start > self.period_end:
            raise ValueError("period_start must be <= period_end")
        for field in ["present_days", "half_days", "absent_days", "paid_leave_days", "overtime_hours", "advance_paid", "deductions"]:
            val = getattr(self, field)
            if val is not None and val < 0:
                raise ValueError(f"{field} cannot be negative")
        return self


class OpeningAttendanceResponse(BaseModel):
    id: int
    worker_id: int
    period_start: date
    period_end: date
    present_days: float
    half_days: float
    absent_days: float
    paid_leave_days: float
    overtime_hours: float
    advance_paid: float
    deductions: float
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class WorkerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    country_code: Optional[str] = Field(default=None, max_length=8)
    phone: Optional[str] = Field(default=None, max_length=50)
    daily_wages: Decimal = Field(..., ge=0)
    duty_hours: float = Field(..., gt=0)
    opening_attendance: Optional[OpeningAttendanceCreate] = None



class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    name: str
    daily_wages: Decimal
    duty_hours: float


class FinalProductStockCreate(BaseModel):
    product_size_ml: int = Field(..., gt=0)
    packaging_size_name: str = Field(..., min_length=1, max_length=100)
    total_boxes: int = Field(default=0, ge=0)
    loose_packets: int = Field(default=0, ge=0)
    packets_per_box_limit: int = Field(..., gt=0)


class FinalProductStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    product_size_ml: int
    packaging_size_name: str
    current_quantity: int = 0
    total_boxes: int
    loose_packets: int
    packets_per_box_limit: int


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone_number: str = Field(..., min_length=1, max_length=50)
    place: str = Field(..., min_length=1, max_length=255)
    gst_number: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    previous_due: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_due: Decimal = Field(default=Decimal("0.00"), ge=0)
    opening_balance: Decimal = Field(default=Decimal("0.00"), ge=0)
    legacy_dues: Decimal = Field(default=Decimal("0.00"), ge=0)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    name: str
    phone_number: Optional[str] = None
    place: Optional[str] = None
    gst_number: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    previous_due: Decimal
    total_due: Decimal


# ---------------------------------------------------------------------------
# Phase 2 Operations Schemas
# ---------------------------------------------------------------------------

class DailyProductionCreate(BaseModel):
    factory_id: Optional[str] = Field(default=None, max_length=100)
    date: date
    operator_id: Optional[int] = Field(default=None, ge=0)
    worker_id: int = Field(default=0, ge=0)
    machine_id: int = Field(default=0, ge=0)
    product_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: Optional[int] = Field(default=None, gt=0)
    variety: str = Field(default="Standard/White", min_length=1, max_length=255)
    packaging_size: Optional[str] = Field(default=None, min_length=1, max_length=100)
    packaging_size_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    pieces_per_packet: int = Field(default=1, gt=0)
    packets_per_box_limit: int = Field(default=1, gt=0)
    shift: str = Field(default="Day", pattern="^(Day|Night)$")
    total_boxes_made: int = Field(default=0, ge=0)
    loose_packets_made: int = Field(default=0, ge=0)
    blank_used_bori: Decimal = Field(default=Decimal("0.000"), ge=0)
    bottom_used_rolls: int = Field(default=0, ge=0)
    blank_used_kg: Decimal = Field(default=Decimal("0.000"), ge=0)
    bottom_used_kg: Decimal = Field(default=Decimal("0.000"), ge=0)
    wastage_kg: Decimal = Field(default=Decimal("0.000"), ge=0)
    remarks: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def normalize_blank_form_values(cls, values):
        if not isinstance(values, dict):
            return values

        cleaned = dict(values)
        alias_map = {
            "production_date": "date",
            "workerId": "worker_id",
            "operator_id": "worker_id",
            "operatorId": "worker_id",
            "machineId": "machine_id",
            "productId": "product_id",
            "productSizeMl": "product_size_ml",
            "packagingSize": "packaging_size",
            "packagingSizeName": "packaging_size_name",
            "piecesPerPacket": "pieces_per_packet",
            "packetsPerBoxLimit": "packets_per_box_limit",
            "boxes_produced": "total_boxes_made",
            "boxesProduced": "total_boxes_made",
            "totalBoxesMade": "total_boxes_made",
            "production_quantity": "total_boxes_made",
            "productionQuantity": "total_boxes_made",
            "loosePacketsMade": "loose_packets_made",
            "loose_packets": "loose_packets_made",
            "loosePackets": "loose_packets_made",
            "blank_used": "blank_used_bori",
            "blankUsedBori": "blank_used_bori",
            "blankUsed": "blank_used_bori",
            "rolls_used": "bottom_used_rolls",
            "rollsUsed": "bottom_used_rolls",
            "bottom_used": "bottom_used_rolls",
            "bottomUsed": "bottom_used_rolls",
            "bottomRollsUsed": "bottom_used_rolls",
            "bottomUsedRolls": "bottom_used_rolls",
            "wastage": "wastage_kg",
            "wastageKg": "wastage_kg",
        }
        for source_field, target_field in alias_map.items():
            if source_field in cleaned and target_field not in cleaned:
                cleaned[target_field] = cleaned[source_field]

        none_if_blank_fields = {"product_id", "product_size_ml", "packaging_size", "packaging_size_name"}
        zero_if_blank_fields = {
            "worker_id",
            "machine_id",
            "total_boxes_made",
            "loose_packets_made",
            "blank_used_bori",
            "bottom_used_rolls",
            "blank_used_kg",
            "bottom_used_kg",
            "wastage_kg",
        }
        one_if_blank_fields = {"pieces_per_packet", "packets_per_box_limit"}

        if cleaned.get("factory_id") not in (None, ""):
            cleaned["factory_id"] = str(cleaned["factory_id"]).strip()
        if cleaned.get("date") in ("", None):
            cleaned["date"] = date.today().isoformat()
        if cleaned.get("operator_id") in ("", None):
            cleaned["operator_id"] = None
        for field_name in none_if_blank_fields:
            if cleaned.get(field_name) == "":
                cleaned[field_name] = None
        for field_name in ("product_id", "product_size_ml"):
            if cleaned.get(field_name) in (0, "0"):
                cleaned[field_name] = None
        for field_name in zero_if_blank_fields:
            if cleaned.get(field_name) in ("", None):
                cleaned[field_name] = 0
        for field_name in one_if_blank_fields:
            if cleaned.get(field_name) in ("", None):
                cleaned[field_name] = 1
        if cleaned.get("variety") in ("", None):
            cleaned["variety"] = "Standard/White"
        if cleaned.get("shift") in ("", None):
            cleaned["shift"] = "Day"
        return cleaned


class DailyProductionResponse(BaseModel):
    production_id: int
    attendance_auto_marked: bool = False
    attendance_log_id: Optional[int] = None
    product_size_ml: int
    total_boxes_before: int
    loose_packets_before: int
    boxes_from_loose: int
    total_boxes_after: int
    loose_packets_after: int
    blank_stock_after_kg: Decimal
    bottom_stock_after_kg: Decimal
    box_stock_after: int
    wastage_status: str = "NORMAL"
    total_raw_material_kg: Decimal = Decimal("0.000")
    production_cost: Decimal = Decimal("0.00")


class DailySaleItemCreate(BaseModel):
    product_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: int = Field(..., gt=0)
    variety: str = Field(default="Standard/White", min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    daily_wages: Decimal = Field(..., ge=0)
    duty_hours: float = Field(..., gt=0)
    opening_attendance: Optional[OpeningAttendanceCreate] = None



class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    name: str
    daily_wages: Decimal
    duty_hours: float


class FinalProductStockCreate(BaseModel):
    product_size_ml: int = Field(..., gt=0)
    packaging_size_name: str = Field(..., min_length=1, max_length=100)
    total_boxes: int = Field(default=0, ge=0)
    loose_packets: int = Field(default=0, ge=0)
    packets_per_box_limit: int = Field(..., gt=0)


class FinalProductStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    product_size_ml: int
    packaging_size_name: str
    current_quantity: int = 0
    total_boxes: int
    loose_packets: int
    packets_per_box_limit: int


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone_number: str = Field(..., min_length=1, max_length=50)
    place: str = Field(..., min_length=1, max_length=255)
    gst_number: Optional[str] = Field(default=None, max_length=50)
    company_name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    previous_due: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_due: Decimal = Field(default=Decimal("0.00"), ge=0)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    name: str
    phone_number: Optional[str] = None
    place: Optional[str] = None
    gst_number: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    previous_due: Decimal
    total_due: Decimal


# ---------------------------------------------------------------------------
# Phase 2 Operations Schemas
# ---------------------------------------------------------------------------

class DailyProductionCreate(BaseModel):
    factory_id: Optional[str] = Field(default=None, max_length=100)
    date: date
    operator_id: Optional[int] = Field(default=None, ge=0)
    worker_id: int = Field(default=0, ge=0)
    machine_id: int = Field(default=0, ge=0)
    product_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: Optional[int] = Field(default=None, gt=0)
    variety: str = Field(default="Standard/White", min_length=1, max_length=100)
    packaging_size: Optional[str] = Field(default=None, min_length=1, max_length=100)
    packaging_size_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    pieces_per_packet: int = Field(default=1, gt=0)
    packets_per_box_limit: int = Field(default=1, gt=0)
    shift: str = Field(default="Day", pattern="^(Day|Night)$")
    total_boxes_made: int = Field(default=0, ge=0)
    loose_packets_made: int = Field(default=0, ge=0)
    blank_used_bori: Decimal = Field(default=Decimal("0.000"), ge=0)
    bottom_used_rolls: int = Field(default=0, ge=0)
    blank_used_kg: Decimal = Field(default=Decimal("0.000"), ge=0)
    bottom_used_kg: Decimal = Field(default=Decimal("0.000"), ge=0)
    wastage_kg: Decimal = Field(default=Decimal("0.000"), ge=0)
    remarks: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def normalize_blank_form_values(cls, values):
        if not isinstance(values, dict):
            return values

        cleaned = dict(values)
        alias_map = {
            "production_date": "date",
            "workerId": "worker_id",
            "operator_id": "worker_id",
            "operatorId": "worker_id",
            "machineId": "machine_id",
            "productId": "product_id",
            "productSizeMl": "product_size_ml",
            "packagingSize": "packaging_size",
            "packagingSizeName": "packaging_size_name",
            "piecesPerPacket": "pieces_per_packet",
            "packetsPerBoxLimit": "packets_per_box_limit",
            "boxes_produced": "total_boxes_made",
            "boxesProduced": "total_boxes_made",
            "totalBoxesMade": "total_boxes_made",
            "production_quantity": "total_boxes_made",
            "productionQuantity": "total_boxes_made",
            "loosePacketsMade": "loose_packets_made",
            "loose_packets": "loose_packets_made",
            "loosePackets": "loose_packets_made",
            "blank_used": "blank_used_bori",
            "blankUsedBori": "blank_used_bori",
            "blankUsed": "blank_used_bori",
            "rolls_used": "bottom_used_rolls",
            "rollsUsed": "bottom_used_rolls",
            "bottom_used": "bottom_used_rolls",
            "bottomUsed": "bottom_used_rolls",
            "bottomRollsUsed": "bottom_used_rolls",
            "bottomUsedRolls": "bottom_used_rolls",
            "wastage": "wastage_kg",
            "wastageKg": "wastage_kg",
        }
        for source_field, target_field in alias_map.items():
            if source_field in cleaned and target_field not in cleaned:
                cleaned[target_field] = cleaned[source_field]

        none_if_blank_fields = {"product_id", "product_size_ml", "packaging_size", "packaging_size_name"}
        zero_if_blank_fields = {
            "worker_id",
            "machine_id",
            "total_boxes_made",
            "loose_packets_made",
            "blank_used_bori",
            "bottom_used_rolls",
            "blank_used_kg",
            "bottom_used_kg",
            "wastage_kg",
        }
        one_if_blank_fields = {"pieces_per_packet", "packets_per_box_limit"}

        if cleaned.get("factory_id") not in (None, ""):
            cleaned["factory_id"] = str(cleaned["factory_id"]).strip()
        if cleaned.get("date") in ("", None):
            cleaned["date"] = date.today().isoformat()
        if cleaned.get("operator_id") in ("", None):
            cleaned["operator_id"] = None
        for field_name in none_if_blank_fields:
            if cleaned.get(field_name) == "":
                cleaned[field_name] = None
        for field_name in ("product_id", "product_size_ml"):
            if cleaned.get(field_name) in (0, "0"):
                cleaned[field_name] = None
        for field_name in zero_if_blank_fields:
            if cleaned.get(field_name) in ("", None):
                cleaned[field_name] = 0
        for field_name in one_if_blank_fields:
            if cleaned.get(field_name) in ("", None):
                cleaned[field_name] = 1
        if cleaned.get("variety") in ("", None):
            cleaned["variety"] = "Standard/White"
        if cleaned.get("shift") in ("", None):
            cleaned["shift"] = "Day"
        return cleaned


class DailyProductionResponse(BaseModel):
    production_id: int
    attendance_auto_marked: bool = False
    attendance_log_id: Optional[int] = None
    product_size_ml: int
    total_boxes_before: int
    loose_packets_before: int
    boxes_from_loose: int
    total_boxes_after: int
    loose_packets_after: int
    blank_stock_after_kg: Decimal
    bottom_stock_after_kg: Decimal
    box_stock_after: int
    wastage_status: str = "NORMAL"
    total_raw_material_kg: Decimal = Decimal("0.000")
    production_cost: Decimal = Decimal("0.00")


class DailySaleItemCreate(BaseModel):
    product_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: int = Field(..., gt=0)
    variety: str = Field(default="Standard/White", min_length=1, max_length=255)
    packaging_size: Optional[str] = Field(default=None, min_length=1, max_length=255)
    packaging_size_name: str = Field(..., min_length=1, max_length=255)
    boxes_sold: int = Field(default=0, ge=0)
    loose_packets_sold: int = Field(default=0, ge=0)
    rate_per_box: Decimal = Field(default=Decimal("0.00"), ge=0)
    rate_per_packet: Decimal = Field(default=Decimal("0.00"), ge=0)
    packets_per_box: int = Field(default=0, ge=0)
    hsn_code: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)
    tax_rate: Optional[float] = Field(default=0.0, ge=0.0)


SalesOrderItemCreate = DailySaleItemCreate


class DailySaleCreate(BaseModel):
    date: date
    customer_id: int = Field(..., gt=0)
    amount_paid: Decimal = Field(default=Decimal("0.00"), ge=0)
    legal_invoice_type: Literal["tax_invoice", "bill_of_supply"] = "bill_of_supply"
    legal_invoice_number: Optional[str] = Field(default=None, max_length=50)
    rough_bill_enabled: bool = True
    rough_bill_number: Optional[str] = Field(default=None, max_length=50)
    items: List[DailySaleItemCreate] = Field(..., min_length=1)
    buyer_gstin: Optional[str] = Field(default=None, max_length=50)
    transport_mode: Optional[str] = Field(default=None, max_length=100)
    vehicle_number: Optional[str] = Field(default=None, max_length=100)
    state_code: Optional[str] = Field(default=None, max_length=50)
    place_of_supply: Optional[str] = Field(default=None, max_length=150)


class DailySaleResponse(BaseModel):
    sale_ids: List[int]
    customer_id: int
    bill_total: Decimal
    amount_paid: Decimal
    customer_total_due: Decimal
    invoice_document_id: Optional[int] = None


class UserSubscriptionResponse(BaseModel):
    active_plan: Optional[str] = None
    plan_name: str
    plan_expires_at: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    days_left: int
    last_login: Optional[datetime] = None
    server_time: datetime
    subscription_status: Optional[str] = None
    billing_cycle: Optional[str] = None
    payment_status: Optional[str] = None
    is_manual_override: bool = False
    is_trial: bool = False
    access_allowed: bool = False
    
    # Temporary debug fields


class UserSubscriptionResponse(BaseModel):
    active_plan: Optional[str] = None
    plan_name: str
    plan_expires_at: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    days_left: int
    last_login: Optional[datetime] = None
    server_time: datetime
    subscription_status: Optional[str] = None
    billing_cycle: Optional[str] = None
    payment_status: Optional[str] = None
    is_manual_override: bool = False
    is_trial: bool = False
    access_allowed: bool = False
    
    # Temporary debug fields
    raw_active_plan: Optional[str] = None
    raw_plan_name: Optional[str] = None
    raw_subscription_end_date: Optional[datetime] = None
    raw_plan_expires_at: Optional[datetime] = None
    raw_trial_end_date: Optional[datetime] = None
    effective_plan: Optional[str] = None
    effective_status: Optional[str] = None
    effective_expires_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Invoicing and Factory Profile Setup Schemas
# ---------------------------------------------------------------------------

class FactoryProfileUpdate(BaseModel):
    factory_name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    gst_number: Optional[str] = Field(default=None, max_length=50)
    initial_invoice_number: Optional[int] = Field(default=1, ge=1)
    invoice_prefix: Optional[str] = Field(default="INV-", max_length=50)
    advance_payment_discount_percentage: Optional[Decimal] = Field(default=Decimal('2.00'), ge=0, le=100)


class FactoryProfileResponse(BaseModel):
    id: int
    factory_name: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    initial_invoice_number: int
    current_invoice_counter: int
    invoice_prefix: Optional[str] = "INV-"
    advance_payment_discount_percentage: Decimal = Decimal('2.00')


class AccountantSummaryResponse(BaseModel):
    month: int
    year: int
    total_invoices: int
    starting_invoice_number: Optional[str] = None
    ending_invoice_number: Optional[str] = None
    total_billed_amount: Decimal
    total_paid_amount: Decimal


class AnalyticsSummaryResponse(BaseModel):
    total_wastage_weight: float = 0.0
    active_worker_count: float = 0.0
    ledger_net_receivables: float = 0.0
