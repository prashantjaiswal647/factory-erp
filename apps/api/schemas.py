from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Auth Schemas
# ---------------------------------------------------------------------------

class OTPRequest(BaseModel):
    phone_number: str = Field(..., min_length=5, max_length=50)


class OTPVerifyRequest(BaseModel):
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
    size_ml_or_mm: int = Field(..., gt=0)
    weight_per_sack_kg: Decimal = Field(..., gt=0)
    pieces_per_sack: int = Field(..., gt=0)


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


class MachineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    machine_type: str
    machine_number: Optional[str] = None
    mould_size_ml: Optional[int] = None
    bottom_size_mm: Optional[int] = None
    speed_per_minute: int


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
    total_qty_kg: Decimal = Field(..., ge=0)


class BottomStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    bottom_size_mm: int
    total_qty_kg: Decimal


class BoxStockCreate(BaseModel):
    packaging_size_name: str = Field(..., min_length=1, max_length=100)
    total_boxes: int = Field(..., ge=0)


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


class WorkerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    daily_wages: Decimal = Field(..., ge=0)
    duty_hours: float = Field(..., gt=0)


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
    total_boxes: int
    loose_packets: int
    packets_per_box_limit: int


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    previous_due: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_due: Decimal = Field(default=Decimal("0.00"), ge=0)


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    previous_due: Decimal
    total_due: Decimal


# ---------------------------------------------------------------------------
# Phase 2 Operations Schemas
# ---------------------------------------------------------------------------

class DailyProductionCreate(BaseModel):
    date: date
    worker_id: int = Field(..., gt=0)
    machine_id: int = Field(..., gt=0)
    packaging_size_name: str = Field(..., min_length=1, max_length=100)
    packets_per_box_limit: int = Field(..., gt=0)
    total_boxes_made: int = Field(..., ge=0)
    loose_packets_made: int = Field(..., ge=0)
    blank_used_kg: Decimal = Field(..., ge=0)
    bottom_used_kg: Decimal = Field(..., ge=0)


class DailyProductionResponse(BaseModel):
    production_id: int
    product_size_ml: int
    total_boxes_before: int
    loose_packets_before: int
    boxes_from_loose: int
    total_boxes_after: int
    loose_packets_after: int
    blank_stock_after_kg: Decimal
    bottom_stock_after_kg: Decimal
    box_stock_after: int


class DailySaleItemCreate(BaseModel):
    product_size_ml: int = Field(..., gt=0)
    packaging_size_name: str = Field(..., min_length=1, max_length=100)
    boxes_sold: int = Field(default=0, ge=0)
    loose_packets_sold: int = Field(default=0, ge=0)
    rate_per_box: Decimal = Field(default=Decimal("0.00"), ge=0)
    rate_per_packet: Decimal = Field(default=Decimal("0.00"), ge=0)


class DailySaleCreate(BaseModel):
    date: date
    customer_id: int = Field(..., gt=0)
    amount_paid: Decimal = Field(default=Decimal("0.00"), ge=0)
    items: List[DailySaleItemCreate] = Field(..., min_length=1)


class DailySaleResponse(BaseModel):
    sale_ids: List[int]
    customer_id: int
    bill_total: Decimal
    amount_paid: Decimal
    customer_total_due: Decimal
