from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    Text,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import relationship

from db import Base


class Factory(Base):
    __tablename__ = "factories"
    __table_args__ = (
        CheckConstraint(
            "subscription_status IN ('trial_active', 'trial_expired', 'active', 'inactive', 'expired', 'cancelled', 'payment_pending', 'trial', 'suspended')",
            name="ck_factories_subscription_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    factory_name = Column(String(255), nullable=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_factories_owner_id_users"), nullable=True, index=True)
    owner_phone_number = Column(
        String(50),
        ForeignKey("users.phone_number"),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    trial_start_date = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    trial_end_date = Column(DateTime(timezone=True), nullable=True)
    subscription_status = Column(String(50), nullable=False, default="trial_active", server_default="trial_active", index=True)
    active_plan = Column(String(50), nullable=True)
    plan_name = Column(String(50), nullable=False, default="Free Trial", server_default="Free Trial")
    billing_cycle = Column(String(20), nullable=True)
    subscription_start_date = Column(DateTime(timezone=True), nullable=True)
    subscription_end_date = Column(DateTime(timezone=True), nullable=True, index=True)
    subscription_start = Column(DateTime(timezone=True), nullable=True)
    subscription_end = Column(DateTime(timezone=True), nullable=True, index=True)
    payment_status = Column(String(50), nullable=False, default="payment_pending", server_default="payment_pending", index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    address = Column(Text, nullable=True)
    razorpay_customer_id = Column(String(255), nullable=True)
    razorpay_subscription_id = Column(String(255), nullable=True)
    telegram_bot_token = Column(String(255), nullable=True)
    telegram_token = Column(String(500), nullable=True)
    telegram_chat_id = Column(String(255), nullable=True)
    telegram_bot_username = Column(String(255), nullable=True)
    subscription_override = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    plan_expires_at = Column(DateTime(timezone=True), nullable=True)
    override_plan = Column(String(255), nullable=True)
    override_expires_at = Column(DateTime(timezone=True), nullable=True)
    override_reason = Column(Text, nullable=True)
    override_updated_at = Column(DateTime(timezone=True), nullable=True)
    usage_limit = Column(Integer, nullable=True)
    token_limit = Column(Integer, nullable=True)
    admin_note = Column(Text, nullable=True)
    google_sheet_id = Column(String(255), nullable=True)
    gst_number = Column(String(50), nullable=True)
    address_place = Column(String(255), nullable=True)
    initial_invoice_number = Column(Integer, default=1, server_default="1")
    current_invoice_counter = Column(Integer, default=1, server_default="1")
    next_tax_invoice_number = Column(Integer, default=1, server_default="1")
    next_bill_of_supply_number = Column(Integer, default=1, server_default="1")
    next_bill_of_supply_simple_number = Column(Integer, default=1, server_default="1")
    invoice_prefix = Column(String(50), nullable=False, default="INV-", server_default="INV-")
    advance_payment_discount_percentage = Column(Numeric(5, 2), nullable=False, default=2.00, server_default="2.00")
    digital_signature_url = Column(String(500), nullable=True)

    users = relationship("User", back_populates="factory", foreign_keys="User.factory_id")
    owner = relationship("User", foreign_keys=[owner_phone_number], back_populates="owned_factory")


class FactoryAutomationSheet(Base):
    __tablename__ = "factory_automation_sheets"

    id = Column(Integer, primary_key=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_name = Column(String(255), nullable=False)
    sheet_type = Column(String(50), nullable=False, default="cron_automation", index=True)
    google_sheet_url = Column(String(500), nullable=True)
    google_sheet_id = Column(String(255), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), index=True)

    factory = relationship("Factory", backref="automation_sheets")


class RecycledInvoice(Base):
    __tablename__ = "recycled_invoices"

    id = Column(Integer, primary_key=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id", ondelete="CASCADE"), nullable=False, index=True)
    recycled_number = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        UniqueConstraint("factory_id", "recycled_number", name="uq_recycled_invoices_factory_number"),
        CheckConstraint("recycled_number > 0", name="ck_recycled_invoices_number_positive"),
    )


class CustomPlanEnquiry(Base):
    __tablename__ = "custom_plan_enquiries"

    id = Column(Integer, primary_key=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=True, index=True)
    owner_name = Column(String(255), nullable=False)
    factory_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    number_of_machines = Column(Integer, nullable=False)
    requirement_details = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class DemoBookingRequest(Base):
    __tablename__ = "demo_booking_requests"

    id = Column(Integer, primary_key=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=True, index=True)
    owner_name = Column(String(255), nullable=False)
    factory_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    preferred_plan = Column(String(50), nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class SubscriptionPayment(Base):
    __tablename__ = "subscription_payments"

    id = Column(Integer, primary_key=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False, index=True)
    plan_code = Column(String(50), nullable=False, index=True)
    billing_cycle = Column(String(20), nullable=False)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(10), nullable=False, default="INR", server_default="INR")
    payment_status = Column(String(50), nullable=False, default="paid", server_default="paid", index=True)
    provider = Column(String(50), nullable=True)
    provider_payment_id = Column(String(255), nullable=True, index=True)
    subscription_start_date = Column(DateTime(timezone=True), nullable=False)
    subscription_end_date = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class SuperAdminAuditLog(Base):
    __tablename__ = "super_admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_email = Column(String(255), nullable=False, index=True)
    action_type = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(100), nullable=True, index=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    ip_address = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class AppUsageLog(Base):
    __tablename__ = "app_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    route_or_module = Column(String(255), nullable=True, index=True)
    method = Column(String(20), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class TokenUsageLog(Base):
    __tablename__ = "token_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    provider = Column(String(100), nullable=True)
    model = Column(String(255), nullable=True)
    feature_name = Column(String(255), nullable=False, index=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Numeric(14, 6), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class TenantMixin:
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False, index=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), nullable=True, unique=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=True, unique=True, index=True)
    phone_number = Column(String(50), nullable=True, unique=True, index=True)
    phone_number_normalized = Column(String(50), nullable=True, index=True)
    full_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="Operator", server_default="Operator", index=True)
    is_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    telegram_id = Column(String(100), nullable=True, unique=True, index=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    factory = relationship("Factory", back_populates="users", foreign_keys=[factory_id])
    owned_factory = relationship("Factory", back_populates="owner", foreign_keys="Factory.owner_phone_number")

    __table_args__ = (
        CheckConstraint("role IN ('Owner', 'Sub-Owner', 'Supervisor', 'Operator')", name="ck_users_role"),
    )


class OTPStore(Base):
    __tablename__ = "otp_store"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(50), nullable=False, index=True)
    otp_code = Column(String(10), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Machine(TenantMixin, Base):
    __tablename__ = "machines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    machine_type = Column(String(255), nullable=False, default="Custom Machine", server_default="Custom Machine", index=True)
    machine_name = Column(String(255), nullable=True, index=True)
    machine_number = Column(String(50), nullable=True, index=True)
    mould_size_ml = Column(Integer, nullable=True, index=True)
    machine_sequence_number = Column(String(50), nullable=True, index=True)
    speed_per_minute = Column(Integer, nullable=False, default=0, server_default="0")
    speed_bpm = Column(Integer, nullable=False, default=0, server_default="0")
    speed_cups_per_minute = Column(Integer, nullable=False, default=0, server_default="0")
    default_speed = Column(Float, nullable=False, default=0, server_default="0")
    target_output_per_shift = Column(Integer, nullable=False, default=0, server_default="0")
    raw_materials_mapped = Column(
        MutableList.as_mutable(JSON().with_variant(JSONB, "postgresql")),
        nullable=False,
        default=list,
        server_default="[]",
    )
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    cup_size_ml = Column(Integer, nullable=True, index=True)
    bottom_size_mm = Column(Integer, nullable=True, index=True)
    default_mould_size = Column(String(100), nullable=True)
    current_mould_size = Column(String(100), nullable=True)
    bottom_size = Column(String(100), nullable=True)
    current_bottom_size = Column(String(100), nullable=True)
    can_swap_moulds = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        CheckConstraint("mould_size_ml IS NULL OR mould_size_ml > 0", name="ck_machines_mould_size_positive"),
        CheckConstraint("speed_per_minute >= 0", name="ck_machines_speed_non_negative"),
        CheckConstraint("speed_bpm >= 0", name="ck_machines_speed_bpm_non_negative"),
        CheckConstraint("speed_cups_per_minute >= 0", name="ck_machines_speed_cups_non_negative"),
        UniqueConstraint("factory_id", "name", name="uq_machines_factory_name"),
        UniqueConstraint("factory_id", "machine_sequence_number", name="uq_machines_factory_sequence"),
    )


class MachineOnboarding(TenantMixin, Base):
    __tablename__ = "machine_onboardings"

    id = Column(Integer, primary_key=True, index=True)
    machine_type = Column(String(100), nullable=False, index=True)
    base_config = Column(
        MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql")),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    custom_fields = Column(
        MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql")),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class MachineTemplate(Base):
    __tablename__ = "machine_templates"
    __table_args__ = (
        CheckConstraint("status IN ('processing', 'pending', 'approved', 'rejected')", name="ck_machine_templates_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    machine_type = Column(String(100), nullable=False, index=True)
    base_config = Column(
        MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql")),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    custom_fields = Column(
        MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql")),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    status = Column(String(20), nullable=False, default="processing", server_default="processing", index=True)
    ai_confidence = Column(Float, nullable=True)
    ai_review = Column(
        MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql")),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("User", foreign_keys=[creator_id])


class FactorySettings(TenantMixin, Base):
    __tablename__ = "factory_settings"

    id = Column(Integer, primary_key=True, index=True)
    last_month_electricity_bill = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    number_of_machines = Column(Integer, nullable=False, default=0, server_default="0")
    default_shift_hours = Column(Float, nullable=False, default=8.0, server_default="8.0")
    bill_of_supply_start_seq = Column(Integer, nullable=False, default=1, server_default="1")
    tax_invoice_start_seq = Column(Integer, nullable=False, default=1, server_default="1")
    bill_of_supply_simple_start_seq = Column(Integer, nullable=False, default=1, server_default="1")

    __table_args__ = (
        CheckConstraint("last_month_electricity_bill >= 0", name="ck_factory_settings_electricity_bill_non_negative"),
        CheckConstraint("number_of_machines >= 0", name="ck_factory_settings_machine_count_non_negative"),
        CheckConstraint("default_shift_hours > 0", name="ck_factory_settings_shift_hours_positive"),
        UniqueConstraint("factory_id", name="uq_factory_settings_factory"),
    )


class FactoryInventory(TenantMixin, Base):
    __tablename__ = "factory_inventory"

    id = Column(Integer, primary_key=True, index=True)
    raw_material_name = Column(String(255), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Customer(TenantMixin, Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    phone_number = Column(String(50), nullable=True, index=True)
    place = Column(String(255), nullable=True, index=True)
    gst_number = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True)
    previous_due = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_due = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    contact_number = Column(String(50), nullable=True)
    telegram_id = Column(String(100), nullable=True, index=True)
    firm_name = Column(String(255), nullable=True, index=True)
    store_token = Column(String(255), nullable=True, unique=True, index=True)
    is_portal_approved = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    portal_access_token = Column(String(255), nullable=True, unique=True, index=True)
    last_balance_update = Column(DateTime(timezone=True), nullable=True)
    last_whatsapp_reminder_at = Column(DateTime(timezone=True), nullable=True)
    advance_discount_pct = Column(Float, nullable=False, default=5.0, server_default="5.0")
    balance_amount = Column(Numeric(14, 2), nullable=False, default=0)
    pending_dues = Column(Float, nullable=False, default=0.0, server_default="0")
    pending_balance = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    sales_invoices = relationship("SalesInvoice", back_populates="customer")
    orders = relationship("Order", back_populates="customer")
    activities = relationship("CustomerActivity", back_populates="customer")

    __table_args__ = (
        CheckConstraint("balance_amount >= 0", name="ck_customers_balance_amount_non_negative"),
        CheckConstraint("previous_due >= 0", name="ck_customers_previous_due_non_negative"),
        CheckConstraint("total_due >= 0", name="ck_customers_total_due_non_negative"),
        CheckConstraint("pending_dues >= 0", name="ck_customers_pending_dues_non_negative"),
        CheckConstraint("pending_balance >= 0", name="ck_customers_pending_balance_non_negative"),
        CheckConstraint(
            "advance_discount_pct >= 0 AND advance_discount_pct <= 100",
            name="ck_customers_advance_discount_pct_range",
        ),
        UniqueConstraint("factory_id", "phone_number", name="uq_customers_factory_phone_number"),
    )


class CustomerActivity(TenantMixin, Base):
    __tablename__ = "customer_activities"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    activity_type = Column(String(100), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    customer = relationship("Customer", back_populates="activities")


class Inventory(TenantMixin, Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=True, index=True)
    packaging_size = Column(String(100), nullable=True, index=True)
    pieces_per_packet = Column(Integer, nullable=True, default=1, server_default="1")
    packets_per_box = Column(Integer, nullable=True, default=0, server_default="0")
    unit = Column(String(50), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=False, default=0)
    price_per_unit = Column(Numeric(14, 2), nullable=False, default=0)

    box_packaging_profiles = relationship(
        "PackagingProfile",
        back_populates="box_inventory",
        foreign_keys="PackagingProfile.box_inventory_id",
    )
    poly_packaging_profiles = relationship(
        "PackagingProfile",
        back_populates="poly_inventory",
        foreign_keys="PackagingProfile.poly_inventory_id",
    )

    __table_args__ = (
        CheckConstraint("category IN ('Raw', 'Packaging')", name="ck_inventory_category"),
        CheckConstraint("unit IN ('kg', 'pieces')", name="ck_inventory_unit"),
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
        CheckConstraint("price_per_unit >= 0", name="ck_inventory_price_per_unit_non_negative"),
        UniqueConstraint("factory_id", "item_name", name="uq_inventory_factory_item_name"),
    )


class RawMaterial(TenantMixin, Base):
    __tablename__ = "raw_materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    material_type = Column(String(50), nullable=False, index=True)
    type = Column(String(50), nullable=True, index=True)
    size_name = Column(String(100), nullable=True, index=True)
    size_ml = Column(Integer, nullable=True, index=True)
    gsm = Column(Integer, nullable=True, index=True)
    unit = Column(String(50), nullable=False)
    opening_stock = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    current_stock = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    stock_quantity = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    price_per_unit = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    __table_args__ = (
        CheckConstraint(
            "material_type IN ('Paper Blank', 'Bottom Roll', 'Polybag', 'Carton Box')",
            name="ck_raw_materials_type",
        ),
        CheckConstraint("opening_stock >= 0", name="ck_raw_materials_opening_stock_non_negative"),
        CheckConstraint("current_stock >= 0", name="ck_raw_materials_current_stock_non_negative"),
        CheckConstraint("price_per_unit >= 0", name="ck_raw_materials_price_non_negative"),
        UniqueConstraint("factory_id", "name", "material_type", "size_name", name="uq_raw_materials_factory_material"),
    )


class RawMaterialMetrics(TenantMixin, Base):
    __tablename__ = "raw_material_metrics"

    id = Column(Integer, primary_key=True, index=True)
    material_type = Column(String(50), nullable=False, index=True)
    size_ml_or_mm = Column(Integer, nullable=False, index=True)
    weight_per_sack_kg = Column(Numeric(14, 3), nullable=False)
    pieces_per_sack = Column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("material_type IN ('Blank', 'Bottom')", name="ck_raw_material_metrics_type"),
        CheckConstraint("size_ml_or_mm > 0", name="ck_raw_material_metrics_size_positive"),
        CheckConstraint("weight_per_sack_kg > 0", name="ck_raw_material_metrics_weight_positive"),
        CheckConstraint("pieces_per_sack > 0", name="ck_raw_material_metrics_pieces_positive"),
        UniqueConstraint("factory_id", "material_type", "size_ml_or_mm", name="uq_raw_material_metrics_factory_spec"),
    )


class PackagingMetrics(TenantMixin, Base):
    __tablename__ = "packaging_metrics"

    id = Column(Integer, primary_key=True, index=True)
    cup_size_ml = Column(Integer, nullable=False, index=True)
    kg_per_box = Column(Numeric(14, 3), nullable=False, default=0)
    cups_per_box = Column(Integer, nullable=False)
    variant_name = Column(String(100), nullable=False, default="Standard/White", server_default="Standard/White", index=True)

    __table_args__ = (
        CheckConstraint("cup_size_ml > 0", name="ck_packaging_metrics_cup_size_positive"),
        CheckConstraint("kg_per_box >= 0", name="ck_packaging_metrics_kg_non_negative"),
        CheckConstraint("cups_per_box > 0", name="ck_packaging_metrics_cups_positive"),
        UniqueConstraint("factory_id", "cup_size_ml", "variant_name", name="uq_packaging_metrics_factory_cup_variant"),
    )


class PackagingProfile(TenantMixin, Base):
    __tablename__ = "packaging_profiles"

    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String(255), nullable=True, index=True)
    product_name_ml = Column(Integer, nullable=True, index=True)
    image_url = Column(String(1000), nullable=True)
    print_design_name = Column(String(255), nullable=True)
    profile_name = Column(String(255), nullable=False, index=True)
    cup_size_ml = Column(Integer, nullable=False, index=True)
    polybag_capacity = Column(Integer, nullable=True)
    box_capacity = Column(Integer, nullable=True)
    box_size_name = Column(String(100), nullable=True, index=True)
    cups_per_poly = Column(Integer, nullable=False)
    cups_per_polybag = Column(Integer, nullable=True)
    polys_per_box = Column(Integer, nullable=False)
    polybags_per_box = Column(Integer, nullable=True)
    box_inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=False, index=True)
    poly_inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=False, index=True)

    box_inventory = relationship(
        "Inventory",
        back_populates="box_packaging_profiles",
        foreign_keys=[box_inventory_id],
    )
    poly_inventory = relationship(
        "Inventory",
        back_populates="poly_packaging_profiles",
        foreign_keys=[poly_inventory_id],
    )
    production_logs = relationship("ProductionLog", back_populates="packaging_profile")
    sales_invoices = relationship("SalesInvoice", back_populates="packaging_profile")
    finished_goods_stock = relationship(
        "FinishedGoodsStock",
        back_populates="packaging_profile",
        uselist=False,
    )

    __table_args__ = (
        CheckConstraint("cup_size_ml > 0", name="ck_packaging_profiles_cup_size_positive"),
        CheckConstraint("polybag_capacity IS NULL OR polybag_capacity > 0", name="ck_packaging_profiles_polybag_capacity_positive"),
        CheckConstraint("box_capacity IS NULL OR box_capacity > 0", name="ck_packaging_profiles_box_capacity_positive"),
        CheckConstraint("cups_per_poly > 0", name="ck_packaging_profiles_cups_per_poly_positive"),
        CheckConstraint("cups_per_polybag IS NULL OR cups_per_polybag > 0", name="ck_packaging_profiles_cups_per_polybag_positive"),
        CheckConstraint("polys_per_box > 0", name="ck_packaging_profiles_polys_per_box_positive"),
        CheckConstraint("polybags_per_box IS NULL OR polybags_per_box > 0", name="ck_packaging_profiles_polybags_per_box_positive"),
        CheckConstraint(
            "box_inventory_id <> poly_inventory_id",
            name="ck_packaging_profiles_distinct_box_poly_inventory",
        ),
        UniqueConstraint("factory_id", "profile_name", name="uq_packaging_profiles_factory_profile_name"),
    )


class ProductionLog(TenantMixin, Base):
    __tablename__ = "production_logs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    shift = Column(String(50), nullable=False, index=True)
    cup_size_ml = Column(Integer, nullable=False, index=True)
    packaging_profile_id = Column(
        Integer,
        ForeignKey("packaging_profiles.id"),
        nullable=False,
        index=True,
    )
    blank_used_pcs = Column(Integer, nullable=False, default=0)
    bottom_used_kg = Column(Numeric(14, 3), nullable=False, default=0)
    boxes_produced = Column(Integer, nullable=False, default=0)
    blank_waste_pcs = Column(Integer, nullable=False, default=0)
    bottom_waste_kg = Column(Numeric(14, 3), nullable=False, default=0)
    box_packing_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    poly_packing_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_packing_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    blank_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    bottom_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_raw_material_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_production_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    packaging_profile = relationship("PackagingProfile", back_populates="production_logs")

    __table_args__ = (
        CheckConstraint("cup_size_ml > 0", name="ck_production_logs_cup_size_positive"),
        CheckConstraint("blank_used_pcs >= 0", name="ck_production_logs_blank_used_non_negative"),
        CheckConstraint("bottom_used_kg >= 0", name="ck_production_logs_bottom_used_non_negative"),
        CheckConstraint("boxes_produced >= 0", name="ck_production_logs_boxes_produced_non_negative"),
        CheckConstraint("blank_waste_pcs >= 0", name="ck_production_logs_blank_waste_non_negative"),
        CheckConstraint("bottom_waste_kg >= 0", name="ck_production_logs_bottom_waste_non_negative"),
        CheckConstraint("box_packing_cost >= 0", name="ck_production_logs_box_packing_cost_non_negative"),
        CheckConstraint("poly_packing_cost >= 0", name="ck_production_logs_poly_packing_cost_non_negative"),
        CheckConstraint("total_packing_cost >= 0", name="ck_production_logs_total_packing_cost_non_negative"),
        CheckConstraint("blank_cost >= 0", name="ck_production_logs_blank_cost_non_negative"),
        CheckConstraint("bottom_cost >= 0", name="ck_production_logs_bottom_cost_non_negative"),
        CheckConstraint(
            "total_raw_material_cost >= 0",
            name="ck_production_logs_total_raw_material_cost_non_negative",
        ),
        CheckConstraint("total_production_cost >= 0", name="ck_production_logs_total_production_cost_non_negative"),
    )


class FinishedGoodsStock(TenantMixin, Base):
    __tablename__ = "finished_goods_stock"

    id = Column(Integer, primary_key=True, index=True)
    cup_size_ml = Column(Integer, nullable=False, index=True)
    packaging_profile_id = Column(
        Integer,
        ForeignKey("packaging_profiles.id"),
        nullable=False,
        index=True,
    )
    boxes_available = Column(Integer, nullable=False, default=0, server_default="0")
    category = Column(String(50), nullable=True, index=True, default="CUP_FINISHED", server_default="CUP_FINISHED")
    variant_name = Column(String(255), nullable=True, index=True)
    image_url = Column(String(1000), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    packaging_profile = relationship("PackagingProfile", back_populates="finished_goods_stock")
    order_items = relationship("OrderItem", back_populates="product")

    __table_args__ = (
        UniqueConstraint("factory_id", "packaging_profile_id", name="uq_finished_goods_stock_factory_packaging_profile"),
        CheckConstraint("cup_size_ml > 0", name="ck_finished_goods_stock_cup_size_positive"),
        CheckConstraint("boxes_available >= 0", name="ck_finished_goods_stock_boxes_available_non_negative"),
        Index("idx_finished_goods_factory_category", "factory_id", "category"),
        CheckConstraint("category IN ('CUP_FINISHED', 'CUP_BLANK', 'CUP_BOTTOM', 'PACKAGING_MATERIAL')", name="ck_finished_goods_stock_category"),
    )


class ExpenseLog(TenantMixin, Base):
    __tablename__ = "expense_logs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False, default=0)
    payment_method = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_expense_logs_amount_non_negative"),
    )


class FactoryExpense(TenantMixin, Base):
    __tablename__ = "factory_expenses"

    id = Column(Integer, primary_key=True, index=True)
    expense_name = Column(String(255), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    category = Column(String(100), nullable=False, default="General", server_default="General", index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_factory_expenses_amount_non_negative"),
    )


class Employee(TenantMixin, Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    role = Column(String(100), nullable=False)
    daily_wage = Column(Numeric(14, 2), nullable=False, default=0)

    attendance_logs = relationship("AttendanceLog", back_populates="employee")
    advance_payments = relationship("AdvancePayment", back_populates="employee")

    __table_args__ = (
        CheckConstraint("daily_wage >= 0", name="ck_employees_daily_wage_non_negative"),
        UniqueConstraint("factory_id", "name", name="uq_employees_factory_name"),
    )


class Worker(TenantMixin, Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True, index=True)
    daily_wage_rate = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    daily_wages = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    duty_hours = Column(Float, nullable=False, default=8.0, server_default="8.0")
    salary = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    daily_salary = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    shift_hours = Column(Float, nullable=False, default=8.0, server_default="8.0")
    shift_timing = Column(String(100), nullable=True)
    shift_type = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)

    __table_args__ = (
        CheckConstraint("daily_wages >= 0", name="ck_workers_daily_wages_non_negative"),
        CheckConstraint("daily_wage_rate >= 0", name="ck_workers_daily_wage_rate_non_negative"),
        CheckConstraint("duty_hours > 0", name="ck_workers_duty_hours_positive"),
        CheckConstraint("salary >= 0", name="ck_workers_salary_non_negative"),
        CheckConstraint("daily_salary >= 0", name="ck_workers_daily_salary_non_negative"),
        CheckConstraint("shift_hours > 0", name="ck_workers_shift_hours_positive"),
        UniqueConstraint("factory_id", "name", name="uq_workers_factory_name"),
    )


class MaterialYield(TenantMixin, Base):
    __tablename__ = "material_yields"

    id = Column(Integer, primary_key=True, index=True)
    material_type = Column(String(50), nullable=False, index=True)
    size_ml = Column(Integer, nullable=False, index=True)
    gsm = Column(Integer, nullable=True, index=True)
    pieces_per_kg = Column(Numeric(14, 3), nullable=False)

    __table_args__ = (
        CheckConstraint("material_type IN ('Blank', 'Bottom')", name="ck_material_yields_type"),
        CheckConstraint("size_ml > 0", name="ck_material_yields_size_positive"),
        CheckConstraint("gsm IS NULL OR gsm > 0", name="ck_material_yields_gsm_positive"),
        CheckConstraint("pieces_per_kg > 0", name="ck_material_yields_pieces_positive"),
        UniqueConstraint("factory_id", "material_type", "size_ml", "gsm", name="uq_material_yields_factory_spec"),
    )


class CostingMaster(TenantMixin, Base):
    __tablename__ = "costing_master"

    id = Column(Integer, primary_key=True, index=True)
    paper_price_per_kg = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    bottom_roll_price_per_kg = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    polybag_price = Column(Numeric(14, 4), nullable=False, default=0, server_default="0")
    carton_price = Column(Numeric(14, 4), nullable=False, default=0, server_default="0")
    labour_cost_per_box = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    electricity_cost_per_box = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    __table_args__ = (
        CheckConstraint("paper_price_per_kg >= 0", name="ck_costing_master_paper_price_non_negative"),
        CheckConstraint("bottom_roll_price_per_kg >= 0", name="ck_costing_master_bottom_price_non_negative"),
        CheckConstraint("polybag_price >= 0", name="ck_costing_master_polybag_price_non_negative"),
        CheckConstraint("carton_price >= 0", name="ck_costing_master_carton_price_non_negative"),
        CheckConstraint("labour_cost_per_box >= 0", name="ck_costing_master_labour_non_negative"),
        CheckConstraint("electricity_cost_per_box >= 0", name="ck_costing_master_electricity_non_negative"),
        UniqueConstraint("factory_id", name="uq_costing_master_factory"),
    )


class CostingOutputMaster(TenantMixin, Base):
    __tablename__ = "costing_output_master"

    id = Column(Integer, primary_key=True, index=True)
    product_cup_size_ml = Column(Integer, nullable=False, index=True)
    selected_blank_metric_id = Column(Integer, ForeignKey("raw_material_metrics.id"), nullable=False)
    selected_bottom_metric_id = Column(Integer, ForeignKey("raw_material_metrics.id"), nullable=False)
    selected_packaging_metric_id = Column(Integer, ForeignKey("packaging_metrics.id"), nullable=False)
    total_cost_price_per_box = Column(Numeric(14, 2), nullable=False)
    cost_per_piece = Column(Numeric(14, 4), nullable=False)
    selling_price_per_box = Column(Numeric(14, 2), nullable=False)
    selling_price_per_piece = Column(Numeric(14, 4), nullable=False)
    profit_per_box = Column(Numeric(14, 2), nullable=False)
    profit_per_piece = Column(Numeric(14, 4), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    blank_metric = relationship("RawMaterialMetrics", foreign_keys=[selected_blank_metric_id])
    bottom_metric = relationship("RawMaterialMetrics", foreign_keys=[selected_bottom_metric_id])
    packaging_metric = relationship("PackagingMetrics", foreign_keys=[selected_packaging_metric_id])

    __table_args__ = (
        CheckConstraint("product_cup_size_ml > 0", name="ck_costing_output_cup_size_positive"),
        CheckConstraint("total_cost_price_per_box >= 0", name="ck_costing_output_total_cost_positive"),
        CheckConstraint("cost_per_piece >= 0", name="ck_costing_output_cost_piece_positive"),
        CheckConstraint("selling_price_per_box >= 0", name="ck_costing_output_selling_box_positive"),
        CheckConstraint("selling_price_per_piece >= 0", name="ck_costing_output_selling_piece_positive"),
    )


class AttendanceLog(TenantMixin, Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="Absent", server_default="Absent", index=True)
    production_qty = Column(Numeric(14, 3), nullable=True)
    duty_hours = Column(Float, nullable=False, default=8.0, server_default="8.0")
    is_settled = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    is_present = Column(Boolean, nullable=False, default=False)
    overtime_hours = Column(Float, nullable=False, default=0)

    employee = relationship("Employee", back_populates="attendance_logs")

    __table_args__ = (
        UniqueConstraint("factory_id", "date", "employee_id", name="uq_attendance_logs_factory_date_employee"),
        UniqueConstraint("factory_id", "date", "worker_id", name="uq_attendance_logs_factory_date_worker"),
        CheckConstraint("status IN ('Present', 'Absent', 'Half-day')", name="ck_attendance_logs_status"),
        CheckConstraint("duty_hours > 0", name="ck_attendance_logs_duty_hours_positive"),
        CheckConstraint("overtime_hours >= 0", name="ck_attendance_logs_overtime_non_negative"),
    )


class AdvancePayment(TenantMixin, Base):
    __tablename__ = "advance_payments"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = Column(Float, nullable=False, default=0)
    is_settled = Column(Boolean, nullable=False, default=False, server_default="false", index=True)

    employee = relationship("Employee", back_populates="advance_payments")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_advance_payments_amount_non_negative"),
    )


class HisabSettlement(TenantMixin, Base):
    __tablename__ = "hisab_settlements"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False, index=True)
    duty_from_date = Column(Date, nullable=False, index=True)
    duty_to_date = Column(Date, nullable=False, index=True)
    advance_cutoff_date = Column(Date, nullable=False, index=True)
    total_duty_amount = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_advance_deducted = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    net_paid = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("total_duty_amount >= 0", name="ck_hisab_settlements_duty_non_negative"),
        CheckConstraint("total_advance_deducted >= 0", name="ck_hisab_settlements_advance_non_negative"),
    )


class WorkerOpeningAttendance(TenantMixin, Base):
    __tablename__ = "worker_opening_attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    present_days = Column(Numeric(6, 1), nullable=False, default=0)
    half_days = Column(Numeric(6, 1), nullable=False, default=0)
    absent_days = Column(Numeric(6, 1), nullable=False, default=0)
    paid_leave_days = Column(Numeric(6, 1), nullable=False, default=0)
    overtime_hours = Column(Numeric(8, 2), nullable=False, default=0)
    advance_paid = Column(Numeric(14, 2), nullable=False, default=0)
    deductions = Column(Numeric(14, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("period_start <= period_end", name="ck_opening_attendance_period"),
        CheckConstraint("present_days >= 0", name="ck_opening_attendance_present_days"),
        CheckConstraint("half_days >= 0", name="ck_opening_attendance_half_days"),
        CheckConstraint("absent_days >= 0", name="ck_opening_attendance_absent_days"),
        CheckConstraint("paid_leave_days >= 0", name="ck_opening_attendance_paid_leave"),
        CheckConstraint("overtime_hours >= 0", name="ck_opening_attendance_overtime"),
        CheckConstraint("advance_paid >= 0", name="ck_opening_attendance_advance"),
        CheckConstraint("deductions >= 0", name="ck_opening_attendance_deductions"),
        UniqueConstraint("factory_id", "worker_id", name="uq_opening_attendance_worker"),
    )


class Order(TenantMixin, Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    order_date = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    status = Column(String(50), nullable=False, default="pending_owner", server_default="pending_owner", index=True)
    payment_method = Column(String(50), nullable=False)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    balance_amount = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    payment_status = Column(String(50), nullable=False, default="Unpaid", server_default="Unpaid", index=True)
    pending_amount = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    terms_accepted = Column(Boolean, nullable=False, default=False)
    is_discount_revoked = Column(Boolean, nullable=False, default=False, server_default="false")
    owner_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    utr_transaction_id = Column(String(50), nullable=True)
    is_payment_verified = Column(Boolean, nullable=False, default=False, server_default="false")

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")

    __table_args__ = (
        CheckConstraint("status IN ('pending_owner', 'confirmed', 'cancelled', 'adjusted_closed', 'Pending', 'Approved', 'Rejected', 'Received')", name="ck_orders_status"),
        CheckConstraint(
            "payment_method IN ('Normal_Credit', 'Full_Advance_UPI', 'Full_Advance_Doorstep')",
            name="ck_orders_payment_method",
        ),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
        CheckConstraint("amount_paid >= 0", name="ck_orders_amount_paid_non_negative"),
        CheckConstraint("balance_amount >= 0", name="ck_orders_balance_amount_non_negative"),
    )


class OrderItem(TenantMixin, Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("finished_goods_stock.id"), nullable=True, index=True)
    quantity = Column(Integer, nullable=False)
    base_rate = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    final_rate = Column(Numeric(14, 2), nullable=False)
    product_size_ml = Column(Integer, nullable=True, index=True)
    variety = Column(String(100), nullable=True, index=True)
    packaging_size_name = Column(String(100), nullable=True, index=True)
    boxes_sold = Column(Integer, nullable=False, default=0, server_default="0")
    loose_packets_sold = Column(Integer, nullable=False, default=0, server_default="0")
    rate_per_box = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    rate_per_packet = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    order = relationship("Order", back_populates="items")
    product = relationship("FinishedGoodsStock", back_populates="order_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("base_rate >= 0", name="ck_order_items_base_rate_non_negative"),
        CheckConstraint("final_rate >= 0", name="ck_order_items_final_rate_non_negative"),
        CheckConstraint("boxes_sold >= 0", name="ck_order_items_boxes_sold_non_negative"),
        CheckConstraint("loose_packets_sold >= 0", name="ck_order_items_loose_packets_sold_non_negative"),
        CheckConstraint("rate_per_box >= 0", name="ck_order_items_rate_per_box_non_negative"),
        CheckConstraint("rate_per_packet >= 0", name="ck_order_items_rate_per_packet_non_negative"),
    )


class SalesInvoice(TenantMixin, Base):
    __tablename__ = "sales_invoices"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    cup_size_ml = Column(Integer, nullable=False, index=True)
    packaging_profile_id = Column(
        Integer,
        ForeignKey("packaging_profiles.id"),
        nullable=False,
        index=True,
    )
    boxes_sold = Column(Integer, nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0)

    customer = relationship("Customer", back_populates="sales_invoices")
    packaging_profile = relationship("PackagingProfile", back_populates="sales_invoices")

    __table_args__ = (
        CheckConstraint("cup_size_ml > 0", name="ck_sales_invoices_cup_size_positive"),
        CheckConstraint("boxes_sold >= 0", name="ck_sales_invoices_boxes_sold_non_negative"),
        CheckConstraint("total_amount >= 0", name="ck_sales_invoices_total_amount_non_negative"),
        CheckConstraint("amount_paid >= 0", name="ck_sales_invoices_amount_paid_non_negative"),
    )


class InvoiceDocument(TenantMixin, Base):
    __tablename__ = "invoice_documents"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    invoice_number = Column(String(100), nullable=False, index=True)
    invoice_date = Column(Date, nullable=False, index=True)
    customer_name = Column(String(255), nullable=False, index=True)
    customer_phone = Column(String(50), nullable=True, index=True)
    payment_method = Column(String(50), nullable=False, default="Cash", server_default="Cash")
    bill_total = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    customer_total_due = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    status = Column(String(50), nullable=False, default="created", server_default="created", index=True)
    buyer_gstin = Column(String(50), nullable=True)
    hsn_code = Column(String(50), nullable=True)
    transport_mode = Column(String(100), nullable=True)
    vehicle_number = Column(String(100), nullable=True)
    state_code = Column(String(50), nullable=True)
    place_of_supply = Column(String(150), nullable=True)
    tax_rate = Column(Float, nullable=True)
    total_taxable_value = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_cgst = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_sgst = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_igst = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    payload_json = Column(
        MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql")),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    pdf_generated_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_pdf_generated_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer")
    order = relationship("Order")
    created_by = relationship("User")

    __table_args__ = (
        UniqueConstraint("factory_id", "invoice_number", name="uq_invoice_documents_factory_invoice_number"),
        CheckConstraint("bill_total >= 0", name="ck_invoice_documents_bill_total_non_negative"),
        CheckConstraint("amount_paid >= 0", name="ck_invoice_documents_amount_paid_non_negative"),
        CheckConstraint("customer_total_due >= 0", name="ck_invoice_documents_due_non_negative"),
        CheckConstraint("pdf_generated_count >= 0", name="ck_invoice_documents_pdf_count_non_negative"),
    )


class OutstandingBill(TenantMixin, Base):
    __tablename__ = "outstanding_bills"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    invoice_document_id = Column(Integer, ForeignKey("invoice_documents.id"), nullable=True, index=True)
    source_type = Column(String(50), nullable=False, default="invoice", server_default="invoice", index=True)
    tracking_number = Column(String(100), nullable=False, index=True)
    bill_date = Column(Date, nullable=False, server_default=func.current_date(), index=True)
    bill_amount = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    balance_amount = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    status = Column(String(50), nullable=False, default="active", server_default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer")
    order = relationship("Order")
    invoice_document = relationship("InvoiceDocument")
    payments = relationship("BillPayment", back_populates="bill", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("bill_amount >= 0", name="ck_outstanding_bills_bill_amount_non_negative"),
        CheckConstraint("amount_paid >= 0", name="ck_outstanding_bills_amount_paid_non_negative"),
        CheckConstraint("balance_amount >= 0", name="ck_outstanding_bills_balance_amount_non_negative"),
        UniqueConstraint("factory_id", "tracking_number", name="uq_outstanding_bills_factory_tracking"),
    )


class BlankStock(TenantMixin, Base):
    __tablename__ = "blank_stock"

    id = Column(Integer, primary_key=True, index=True)
    blank_size_ml = Column(Integer, nullable=False, index=True)
    variety = Column(String(100), nullable=False, default="Plain White", server_default="Plain White", index=True)
    linked_bottom_size_mm = Column(Integer, nullable=False, index=True)
    weight_per_bora_kg = Column(Numeric(14, 3), nullable=True)
    total_boras = Column(Numeric(14, 3), nullable=True)
    total_qty_kg = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("factory_id", "blank_size_ml", "variety", name="uq_blank_stock_factory_size_variety"),
        CheckConstraint("blank_size_ml > 0", name="ck_blank_stock_size_positive"),
        CheckConstraint("linked_bottom_size_mm > 0", name="ck_blank_stock_bottom_size_positive"),
    )


class BottomStock(TenantMixin, Base):
    __tablename__ = "bottom_stock"

    id = Column(Integer, primary_key=True, index=True)
    bottom_size_mm = Column(Integer, nullable=False, index=True)
    variety = Column(String(100), nullable=False, default="Plain White", server_default="Plain White", index=True)
    bag_weight_kg = Column(Numeric(14, 3), nullable=True)
    rolls_per_bag = Column(Integer, nullable=True)
    total_bags = Column(Integer, nullable=True)
    total_rolls = Column(Integer, nullable=False, default=0, server_default="0")
    total_weight_kg = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    total_qty_kg = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("factory_id", "bottom_size_mm", "variety", name="uq_bottom_stock_factory_size_variety"),
        CheckConstraint("bottom_size_mm > 0", name="ck_bottom_stock_size_positive"),
        CheckConstraint("bag_weight_kg >= 0", name="ck_bottom_stock_bag_weight_non_negative"),
        CheckConstraint("rolls_per_bag >= 0", name="ck_bottom_stock_rolls_per_bag_non_negative"),
        CheckConstraint("total_bags >= 0", name="ck_bottom_stock_total_bags_non_negative"),
        CheckConstraint("total_rolls >= 0", name="ck_bottom_stock_total_rolls_non_negative"),
    )


class BoxStock(TenantMixin, Base):
    __tablename__ = "box_stock"

    id = Column(Integer, primary_key=True, index=True)
    packaging_size_name = Column(String(100), nullable=False, index=True)
    total_boxes = Column(Integer, nullable=False, default=0, server_default="0")
    box_type = Column(String(100), nullable=True, index=True)
    quantity = Column(Integer, nullable=False, default=0, server_default="0")
    price_per_box = Column(Float, nullable=False, default=0.0, server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("factory_id", "packaging_size_name", name="uq_box_stock_factory_size"),
        CheckConstraint("quantity >= 0", name="ck_box_stock_quantity_non_negative"),
        CheckConstraint("price_per_box >= 0", name="ck_box_stock_price_non_negative"),
    )


class PlasticStock(TenantMixin, Base):
    __tablename__ = "plastic_stock"

    id = Column(Integer, primary_key=True, index=True)
    plastic_size_name = Column(String(100), nullable=False, index=True)
    cup_size_ml = Column(Integer, nullable=False, index=True)
    total_boras = Column(Integer, nullable=False, default=0, server_default="0")
    weight_per_bora_kg = Column(Float, nullable=False, default=0.0, server_default="0")
    price_per_kg = Column(Float, nullable=False, default=0.0, server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("factory_id", "plastic_size_name", "cup_size_ml", name="uq_plastic_stock_factory_size_cup"),
        CheckConstraint("cup_size_ml > 0", name="ck_plastic_stock_cup_size_positive"),
        CheckConstraint("total_boras >= 0", name="ck_plastic_stock_total_boras_non_negative"),
        CheckConstraint("weight_per_bora_kg >= 0", name="ck_plastic_stock_weight_non_negative"),
        CheckConstraint("price_per_kg >= 0", name="ck_plastic_stock_price_non_negative"),
    )


class PolybagStock(TenantMixin, Base):
    __tablename__ = "polybag_stock"

    id = Column(Integer, primary_key=True, index=True)
    packaging_size_name = Column(String(100), nullable=False, index=True)
    total_packets = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("factory_id", "packaging_size_name", name="uq_polybag_stock_factory_size"),
        CheckConstraint("total_packets >= 0", name="ck_polybag_stock_total_non_negative"),
    )


class FinalProductStock(TenantMixin, Base):
    __tablename__ = "final_product_stock"

    id = Column(Integer, primary_key=True, index=True)
    product_size_ml = Column(Integer, nullable=False, index=True)
    variety = Column(String(100), nullable=False, default="Standard/White", server_default="Standard/White", index=True)
    packaging_size_name = Column(String(100), nullable=False, index=True)
    pieces_per_packet = Column(Integer, nullable=False, default=1, server_default="1")
    current_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    total_boxes = Column(Integer, nullable=False, default=0, server_default="0")
    loose_packets = Column(Integer, nullable=False, default=0, server_default="0")
    packets_per_box_limit = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("factory_id", "product_size_ml", "variety", "packaging_size_name", name="uq_final_product_factory_product_variety_pack"),
        CheckConstraint("product_size_ml > 0", name="ck_final_product_size_positive"),
        CheckConstraint("loose_packets >= 0", name="ck_final_product_loose_non_negative"),
        CheckConstraint("packets_per_box_limit > 0", name="ck_final_product_packets_limit_positive"),
        CheckConstraint("pieces_per_packet > 0", name="ck_final_product_pieces_per_packet_positive"),
    )


class DailyProduction(TenantMixin, Base):
    __tablename__ = "daily_productions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False, index=True)
    product_size_ml = Column(Integer, nullable=False, index=True)
    variety = Column(String(100), nullable=False, default="Standard/White", server_default="Standard/White", index=True)
    packaging_size_name = Column(String(100), nullable=False, index=True)
    packets_per_box_limit = Column(Integer, nullable=False)
    total_boxes_made = Column(Integer, nullable=False, default=0, server_default="0")
    loose_packets_made = Column(Integer, nullable=False, default=0, server_default="0")
    boxes_from_loose = Column(Integer, nullable=False, default=0, server_default="0")
    blank_used_kg = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    bottom_used_kg = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    wastage_kg = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    wastage_status = Column(String(50), nullable=False, default="NORMAL", server_default="NORMAL", index=True)
    total_raw_material_kg = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    raw_material_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    labor_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    electricity_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    production_cost = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("product_size_ml > 0", name="ck_daily_productions_product_size_positive"),
        CheckConstraint("packets_per_box_limit > 0", name="ck_daily_productions_packets_limit_positive"),
        CheckConstraint("total_boxes_made >= 0", name="ck_daily_productions_boxes_non_negative"),
        CheckConstraint("loose_packets_made >= 0", name="ck_daily_productions_loose_non_negative"),
        CheckConstraint("blank_used_kg >= 0", name="ck_daily_productions_blank_used_non_negative"),
        CheckConstraint("bottom_used_kg >= 0", name="ck_daily_productions_bottom_used_non_negative"),
        CheckConstraint("wastage_kg >= 0", name="ck_daily_productions_wastage_non_negative"),
        CheckConstraint("total_raw_material_kg >= 0", name="ck_daily_productions_total_raw_non_negative"),
        CheckConstraint("raw_material_cost >= 0", name="ck_daily_productions_raw_cost_non_negative"),
        CheckConstraint("labor_cost >= 0", name="ck_daily_productions_labor_cost_non_negative"),
        CheckConstraint("electricity_cost >= 0", name="ck_daily_productions_electricity_cost_non_negative"),
        CheckConstraint("production_cost >= 0", name="ck_daily_productions_cost_non_negative"),
    )


class DailySale(TenantMixin, Base):
    __tablename__ = "daily_sales"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    product_size_ml = Column(Integer, nullable=False, index=True)
    variety = Column(String(100), nullable=False, default="Standard/White", server_default="Standard/White", index=True)
    packaging_size_name = Column(String(100), nullable=False, index=True)
    boxes_sold = Column(Integer, nullable=False, default=0, server_default="0")
    loose_packets_sold = Column(Integer, nullable=False, default=0, server_default="0")
    rate_per_box = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    rate_per_packet = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    total_amount = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    customer_phone = Column(String(50), nullable=True, index=True)
    total_bill = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    initial_payment = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("product_size_ml > 0", name="ck_daily_sales_product_size_positive"),
        CheckConstraint("boxes_sold >= 0", name="ck_daily_sales_boxes_non_negative"),
        CheckConstraint("loose_packets_sold >= 0", name="ck_daily_sales_loose_non_negative"),
        CheckConstraint("rate_per_box >= 0", name="ck_daily_sales_rate_box_non_negative"),
        CheckConstraint("rate_per_packet >= 0", name="ck_daily_sales_rate_packet_non_negative"),
        CheckConstraint("total_amount >= 0", name="ck_daily_sales_total_amount_non_negative"),
        CheckConstraint("amount_paid >= 0", name="ck_daily_sales_amount_paid_non_negative"),
        CheckConstraint("total_bill >= 0", name="ck_daily_sales_total_bill_non_negative"),
        CheckConstraint("initial_payment >= 0", name="ck_daily_sales_initial_payment_non_negative"),
    )


class Payment(TenantMixin, Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    customer_phone = Column(String(50), nullable=False, index=True)
    sale_id = Column(Integer, ForeignKey("daily_sales.id"), nullable=True, index=True)
    amount_paid = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    payment_mode = Column(String(20), nullable=False, default="Cash", server_default="Cash")
    date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount_paid > 0", name="ck_payments_amount_paid_positive"),
        CheckConstraint("payment_mode IN ('Cash', 'UPI', 'Bank Transfer')", name="ck_payments_mode_valid"),
    )


class PaymentCollection(TenantMixin, Base):
    __tablename__ = "payment_collections"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True, index=True)
    outstanding_bill_id = Column(Integer, ForeignKey("outstanding_bills.id"), nullable=True, index=True)
    amount_collected = Column(Numeric(14, 2), nullable=False)
    payment_mode = Column(String(20), nullable=False, default="Cash", server_default="Cash")
    collection_date = Column(Date, nullable=False, index=True)
    reference_number = Column(String(100), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    customer = relationship("Customer")
    payment = relationship("Payment")
    outstanding_bill = relationship("OutstandingBill")
    created_by = relationship("User")

    __table_args__ = (
        CheckConstraint("amount_collected > 0", name="ck_payment_collections_amount_positive"),
        CheckConstraint("payment_mode IN ('Cash', 'UPI', 'Bank Transfer')", name="ck_payment_collections_mode_valid"),
    )


class ActivityLog(TenantMixin, Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=False)
    log_date = Column(Date, nullable=False, server_default=func.current_date(), index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    user_id = Column(Integer, nullable=True, index=True)
    user_role = Column(String(100), nullable=True)
    user_name = Column(String(255), nullable=True)
    action_type = Column(String(100), nullable=True)
    action_summary = Column(Text, nullable=True)
    entity_name = Column(String(255), nullable=True)
    entity_type = Column(String(100), nullable=True, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    short_statement = Column(Text, nullable=True)
    committed_at = Column(DateTime(timezone=True), nullable=True, index=True)


class BillPayment(TenantMixin, Base):
    __tablename__ = "bill_payments"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("outstanding_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_allocated = Column(Numeric(14, 2), nullable=False)
    payment_date = Column(Date, nullable=False, index=True)
    received_by_name = Column(String(100), nullable=True)
    received_by_role = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    bill = relationship("OutstandingBill", back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount_allocated > 0", name="ck_bill_payments_amount_allocated_positive"),
    )


class WastageLog(TenantMixin, Base):
    __tablename__ = "wastage_logs"

    id = Column(Integer, primary_key=True, index=True)
    wastage_weight = Column(Float, nullable=False, default=0.0)
    date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

