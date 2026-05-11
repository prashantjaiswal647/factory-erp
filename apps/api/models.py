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
)
from sqlalchemy.orm import relationship

from db import Base


class Factory(Base):
    __tablename__ = "factories"
    __table_args__ = (
        CheckConstraint(
            "subscription_status IN ('trial', 'active', 'expired')",
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
    subscription_status = Column(String(50), nullable=False, default="trial", server_default="trial", index=True)
    razorpay_customer_id = Column(String(255), nullable=True)
    razorpay_subscription_id = Column(String(255), nullable=True)

    users = relationship("User", back_populates="factory", foreign_keys="User.factory_id")
    owner = relationship("User", foreign_keys=[owner_phone_number], back_populates="owned_factory")


class TenantMixin:
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False, index=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), nullable=True, unique=True, index=True)
    factory_id = Column(Integer, ForeignKey("factories.id"), nullable=False, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    phone_number = Column(String(50), nullable=True, unique=True, index=True)
    full_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="Operator", server_default="Operator", index=True)
    is_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    telegram_id = Column(String(100), nullable=True, unique=True, index=True)

    factory = relationship("Factory", back_populates="users", foreign_keys=[factory_id])
    owned_factory = relationship("Factory", back_populates="owner", foreign_keys="Factory.owner_phone_number")

    __table_args__ = (
        CheckConstraint("role IN ('Owner', 'Supervisor', 'Operator')", name="ck_users_role"),
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
    machine_type = Column(String(50), nullable=False, default="Paper Cup", server_default="Paper Cup", index=True)
    machine_number = Column(String(50), nullable=True, index=True)
    mould_size_ml = Column(Integer, nullable=True, index=True)
    machine_sequence_number = Column(String(50), nullable=True, index=True)
    speed_per_minute = Column(Integer, nullable=False, default=0, server_default="0")
    speed_bpm = Column(Integer, nullable=False, default=0, server_default="0")
    speed_cups_per_minute = Column(Integer, nullable=False, default=0, server_default="0")
    cup_size_ml = Column(Integer, nullable=True, index=True)
    bottom_size_mm = Column(Integer, nullable=True, index=True)
    default_mould_size = Column(String(100), nullable=True)
    current_mould_size = Column(String(100), nullable=True)
    bottom_size = Column(String(100), nullable=True)
    current_bottom_size = Column(String(100), nullable=True)
    can_swap_moulds = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        CheckConstraint("machine_type IN ('Paper Cup', 'Dona', 'Paper Bag')", name="ck_machines_machine_type"),
        CheckConstraint("mould_size_ml IS NULL OR mould_size_ml > 0", name="ck_machines_mould_size_positive"),
        CheckConstraint("speed_per_minute >= 0", name="ck_machines_speed_non_negative"),
        CheckConstraint("speed_bpm >= 0", name="ck_machines_speed_bpm_non_negative"),
        CheckConstraint("speed_cups_per_minute >= 0", name="ck_machines_speed_cups_non_negative"),
        UniqueConstraint("factory_id", "name", name="uq_machines_factory_name"),
        UniqueConstraint("factory_id", "machine_sequence_number", name="uq_machines_factory_sequence"),
    )


class FactorySettings(TenantMixin, Base):
    __tablename__ = "factory_settings"

    id = Column(Integer, primary_key=True, index=True)
    last_month_electricity_bill = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    number_of_machines = Column(Integer, nullable=False, default=0, server_default="0")
    default_shift_hours = Column(Float, nullable=False, default=8.0, server_default="8.0")

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
        UniqueConstraint("factory_id", "name", name="uq_customers_factory_name"),
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
    category = Column(String(50), nullable=False, index=True)
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

    __table_args__ = (
        CheckConstraint("cup_size_ml > 0", name="ck_packaging_metrics_cup_size_positive"),
        CheckConstraint("kg_per_box >= 0", name="ck_packaging_metrics_kg_non_negative"),
        CheckConstraint("cups_per_box > 0", name="ck_packaging_metrics_cups_positive"),
        UniqueConstraint("factory_id", "cup_size_ml", name="uq_packaging_metrics_factory_cup"),
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
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="Absent", server_default="Absent", index=True)
    production_qty = Column(Numeric(14, 3), nullable=True)
    is_settled = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    is_present = Column(Boolean, nullable=False, default=False)
    overtime_hours = Column(Float, nullable=False, default=0)

    employee = relationship("Employee", back_populates="attendance_logs")

    __table_args__ = (
        UniqueConstraint("factory_id", "date", "employee_id", name="uq_attendance_logs_factory_date_employee"),
        UniqueConstraint("factory_id", "date", "worker_id", name="uq_attendance_logs_factory_date_worker"),
        CheckConstraint("status IN ('Present', 'Absent', 'Half-day')", name="ck_attendance_logs_status"),
        CheckConstraint("overtime_hours >= 0", name="ck_attendance_logs_overtime_non_negative"),
    )


class AdvancePayment(TenantMixin, Base):
    __tablename__ = "advance_payments"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True, index=True)
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
    status = Column(String(50), nullable=False, default="Pending", server_default="Pending", index=True)
    payment_method = Column(String(50), nullable=False)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    terms_accepted = Column(Boolean, nullable=False, default=False)
    is_discount_revoked = Column(Boolean, nullable=False, default=False, server_default="false")

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")

    __table_args__ = (
        CheckConstraint("status IN ('Pending', 'Approved', 'Rejected')", name="ck_orders_status"),
        CheckConstraint(
            "payment_method IN ('Normal_Credit', 'Full_Advance_UPI', 'Full_Advance_Doorstep')",
            name="ck_orders_payment_method",
        ),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
    )


class OrderItem(TenantMixin, Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("finished_goods_stock.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    base_rate = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    final_rate = Column(Numeric(14, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("FinishedGoodsStock", back_populates="order_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("base_rate >= 0", name="ck_order_items_base_rate_non_negative"),
        CheckConstraint("final_rate >= 0", name="ck_order_items_final_rate_non_negative"),
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
    total_boxes = Column(Integer, nullable=False, default=0, server_default="0")
    loose_packets = Column(Integer, nullable=False, default=0, server_default="0")
    packets_per_box_limit = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("factory_id", "product_size_ml", "variety", "packaging_size_name", name="uq_final_product_factory_product_variety_pack"),
        CheckConstraint("product_size_ml > 0", name="ck_final_product_size_positive"),
        CheckConstraint("loose_packets >= 0", name="ck_final_product_loose_non_negative"),
        CheckConstraint("packets_per_box_limit > 0", name="ck_final_product_packets_limit_positive"),
    )


class DailyProduction(TenantMixin, Base):
    __tablename__ = "daily_productions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False, index=True)
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
