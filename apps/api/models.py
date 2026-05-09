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
)
from sqlalchemy.orm import relationship

from db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="Operator", server_default="Operator", index=True)

    __table_args__ = (
        CheckConstraint("role IN ('Owner', 'Operator')", name="ck_users_role"),
    )


class FactoryInventory(Base):
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


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    contact_number = Column(String(50), nullable=True)
    store_token = Column(String(255), nullable=True, unique=True, index=True)
    advance_discount_pct = Column(Float, nullable=False, default=5.0, server_default="5.0")
    balance_amount = Column(Numeric(14, 2), nullable=False, default=0)

    sales_invoices = relationship("SalesInvoice", back_populates="customer")
    orders = relationship("Order", back_populates="customer")
    activities = relationship("CustomerActivity", back_populates="customer")

    __table_args__ = (
        CheckConstraint("balance_amount >= 0", name="ck_customers_balance_amount_non_negative"),
        CheckConstraint(
            "advance_discount_pct >= 0 AND advance_discount_pct <= 100",
            name="ck_customers_advance_discount_pct_range",
        ),
    )


class CustomerActivity(Base):
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


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String(255), nullable=False, unique=True, index=True)
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
    )


class PackagingProfile(Base):
    __tablename__ = "packaging_profiles"

    id = Column(Integer, primary_key=True, index=True)
    profile_name = Column(String(255), nullable=False, unique=True, index=True)
    cup_size_ml = Column(Integer, nullable=False, index=True)
    cups_per_poly = Column(Integer, nullable=False)
    polys_per_box = Column(Integer, nullable=False)
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
        CheckConstraint("cups_per_poly > 0", name="ck_packaging_profiles_cups_per_poly_positive"),
        CheckConstraint("polys_per_box > 0", name="ck_packaging_profiles_polys_per_box_positive"),
        CheckConstraint(
            "box_inventory_id <> poly_inventory_id",
            name="ck_packaging_profiles_distinct_box_poly_inventory",
        ),
    )


class ProductionLog(Base):
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


class FinishedGoodsStock(Base):
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
        UniqueConstraint("packaging_profile_id", name="uq_finished_goods_stock_packaging_profile"),
        CheckConstraint("cup_size_ml > 0", name="ck_finished_goods_stock_cup_size_positive"),
        CheckConstraint("boxes_available >= 0", name="ck_finished_goods_stock_boxes_available_non_negative"),
    )


class ExpenseLog(Base):
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


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    role = Column(String(100), nullable=False)
    daily_wage = Column(Numeric(14, 2), nullable=False, default=0)

    attendance_logs = relationship("AttendanceLog", back_populates="employee")
    advance_payments = relationship("AdvancePayment", back_populates="employee")

    __table_args__ = (
        CheckConstraint("daily_wage >= 0", name="ck_employees_daily_wage_non_negative"),
    )


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    is_present = Column(Boolean, nullable=False, default=False)
    overtime_hours = Column(Float, nullable=False, default=0)

    employee = relationship("Employee", back_populates="attendance_logs")

    __table_args__ = (
        UniqueConstraint("date", "employee_id", name="uq_attendance_logs_date_employee"),
        CheckConstraint("overtime_hours >= 0", name="ck_attendance_logs_overtime_non_negative"),
    )


class AdvancePayment(Base):
    __tablename__ = "advance_payments"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False, default=0)

    employee = relationship("Employee", back_populates="advance_payments")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_advance_payments_amount_non_negative"),
    )


class Order(Base):
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


class OrderItem(Base):
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


class SalesInvoice(Base):
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
