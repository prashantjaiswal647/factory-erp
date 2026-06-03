from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from db import engine


def apply_runtime_compat_schema(connection: Optional[Connection] = None) -> None:
    """Apply legacy additive DDL through Alembic, not FastAPI startup."""
    default_factory_name = (os.getenv("DEFAULT_FACTORY_NAME") or "Default Factory").replace("'", "''")
    statements = [
        "CREATE TABLE IF NOT EXISTS factories (id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE, created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS google_sheet_id VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS gst_number VARCHAR(50)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS address_place VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS invoice_prefix VARCHAR(50) NOT NULL DEFAULT 'INV-'",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS next_tax_invoice_number INTEGER DEFAULT 1",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS next_bill_of_supply_number INTEGER DEFAULT 1",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS next_bill_of_supply_simple_number INTEGER DEFAULT 1",
        f"INSERT INTO factories (name) VALUES ('{default_factory_name}') ON CONFLICT (name) DO NOTHING",
        "CREATE TABLE IF NOT EXISTS factory_settings (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, last_month_electricity_bill NUMERIC(14,2) NOT NULL DEFAULT 0, number_of_machines INTEGER NOT NULL DEFAULT 0, default_shift_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0, bill_of_supply_start_seq INTEGER NOT NULL DEFAULT 1, tax_invoice_start_seq INTEGER NOT NULL DEFAULT 1, bill_of_supply_simple_start_seq INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_factory_settings_factory UNIQUE (factory_id))",
        "ALTER TABLE factory_settings ADD COLUMN IF NOT EXISTS bill_of_supply_start_seq INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE factory_settings ADD COLUMN IF NOT EXISTS tax_invoice_start_seq INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE factory_settings ADD COLUMN IF NOT EXISTS bill_of_supply_simple_start_seq INTEGER NOT NULL DEFAULT 1",
        "CREATE TABLE IF NOT EXISTS factory_automation_sheets (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, sheet_name VARCHAR(255) NOT NULL, sheet_type VARCHAR(50) NOT NULL DEFAULT 'cron_automation', google_sheet_url VARCHAR(500), google_sheet_id VARCHAR(255) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())",
        "CREATE INDEX IF NOT EXISTS idx_factory_automation_sheets_factory_id ON factory_automation_sheets(factory_id)",
        "CREATE INDEX IF NOT EXISTS idx_factory_automation_sheets_sheet_type ON factory_automation_sheets(sheet_type)",
        "CREATE TABLE IF NOT EXISTS recycled_invoices (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, recycled_number INTEGER NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), CONSTRAINT uq_recycled_invoices_factory_number UNIQUE (factory_id, recycled_number), CONSTRAINT ck_recycled_invoices_number_positive CHECK (recycled_number > 0))",
        "CREATE INDEX IF NOT EXISTS idx_recycled_invoices_factory_number ON recycled_invoices(factory_id, recycled_number)",
        "CREATE TABLE IF NOT EXISTS invoice_documents (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id), customer_id INTEGER NULL REFERENCES customers(id), order_id INTEGER NULL REFERENCES orders(id), invoice_number VARCHAR(100) NOT NULL, invoice_date DATE NOT NULL, customer_name VARCHAR(255) NOT NULL, customer_phone VARCHAR(50), payment_method VARCHAR(50) NOT NULL DEFAULT 'Cash', bill_total NUMERIC(14,2) NOT NULL DEFAULT 0, amount_paid NUMERIC(14,2) NOT NULL DEFAULT 0, customer_total_due NUMERIC(14,2) NOT NULL DEFAULT 0, status VARCHAR(50) NOT NULL DEFAULT 'created', payload_json JSONB NOT NULL DEFAULT '{}'::jsonb, pdf_generated_count INTEGER NOT NULL DEFAULT 0, last_pdf_generated_at TIMESTAMP WITH TIME ZONE NULL, created_by_user_id INTEGER NULL REFERENCES users(id), created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), CONSTRAINT uq_invoice_documents_factory_invoice_number UNIQUE (factory_id, invoice_number), CONSTRAINT ck_invoice_documents_bill_total_non_negative CHECK (bill_total >= 0), CONSTRAINT ck_invoice_documents_amount_paid_non_negative CHECK (amount_paid >= 0), CONSTRAINT ck_invoice_documents_due_non_negative CHECK (customer_total_due >= 0), CONSTRAINT ck_invoice_documents_pdf_count_non_negative CHECK (pdf_generated_count >= 0))",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS buyer_gstin VARCHAR(50)",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS hsn_code VARCHAR(50)",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS transport_mode VARCHAR(100)",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS vehicle_number VARCHAR(100)",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS state_code VARCHAR(50)",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS place_of_supply VARCHAR(150)",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS tax_rate DOUBLE PRECISION",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS total_taxable_value NUMERIC(14,2) NOT NULL DEFAULT 0",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS total_cgst NUMERIC(14,2) NOT NULL DEFAULT 0",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS total_sgst NUMERIC(14,2) NOT NULL DEFAULT 0",
        "ALTER TABLE invoice_documents ADD COLUMN IF NOT EXISTS total_igst NUMERIC(14,2) NOT NULL DEFAULT 0",
        "CREATE INDEX IF NOT EXISTS idx_invoice_documents_factory_created ON invoice_documents(factory_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_invoice_documents_factory_date ON invoice_documents(factory_id, invoice_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_invoice_documents_customer_id ON invoice_documents(customer_id)",
        "ALTER TABLE machines DROP CONSTRAINT IF EXISTS ck_machines_machine_type",
        "ALTER TABLE machines ALTER COLUMN machine_type TYPE VARCHAR(255)",
        "ALTER TABLE machines ALTER COLUMN machine_type SET DEFAULT 'Custom Machine'",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS machine_name VARCHAR(255)",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS default_speed DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS target_output_per_shift INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS raw_materials_mapped JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        # Safe backfill: only fills missing/blank machine names from legacy type/name fields.
        # It does not overwrite any non-blank production machine_name value.
        "UPDATE machines SET machine_name = COALESCE(NULLIF(machine_name, ''), NULLIF(machine_type, ''), name) WHERE machine_name IS NULL OR trim(machine_name) = ''",
        # Safe backfill: only fills NULL default_speed. Existing non-null values,
        # including user-entered 0, are preserved.
        "UPDATE machines SET default_speed = COALESCE(NULLIF(speed_per_minute, 0), NULLIF(speed_cups_per_minute, 0), NULLIF(speed_bpm, 0), 0) WHERE default_speed IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_machines_factory_active ON machines(factory_id, is_active)",
        "ALTER TABLE customers DROP CONSTRAINT IF EXISTS uq_customers_factory_name",
        "DROP INDEX IF EXISTS uq_customers_factory_name",
        "CREATE TABLE IF NOT EXISTS outstanding_bills (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, customer_id INTEGER NOT NULL REFERENCES customers(id), order_id INTEGER NULL REFERENCES orders(id), invoice_document_id INTEGER NULL REFERENCES invoice_documents(id), source_type VARCHAR(50) NOT NULL DEFAULT 'invoice', tracking_number VARCHAR(100) NOT NULL, bill_date DATE NOT NULL DEFAULT CURRENT_DATE, bill_amount NUMERIC(14,2) NOT NULL DEFAULT 0, amount_paid NUMERIC(14,2) NOT NULL DEFAULT 0, balance_amount NUMERIC(14,2) NOT NULL DEFAULT 0, status VARCHAR(50) NOT NULL DEFAULT 'active', created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), CONSTRAINT uq_outstanding_bills_factory_tracking UNIQUE (factory_id, tracking_number), CONSTRAINT ck_outstanding_bills_bill_amount_non_negative CHECK (bill_amount >= 0), CONSTRAINT ck_outstanding_bills_amount_paid_non_negative CHECK (amount_paid >= 0), CONSTRAINT ck_outstanding_bills_balance_amount_non_negative CHECK (balance_amount >= 0))",
        "CREATE INDEX IF NOT EXISTS idx_outstanding_bills_factory_customer ON outstanding_bills(factory_id, customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_outstanding_bills_factory_status ON outstanding_bills(factory_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_outstanding_bills_order_id ON outstanding_bills(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_outstanding_bills_invoice_document_id ON outstanding_bills(invoice_document_id)",
        "CREATE TABLE IF NOT EXISTS payment_collections (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, customer_id INTEGER NOT NULL REFERENCES customers(id), payment_id INTEGER NULL REFERENCES payments(id), outstanding_bill_id INTEGER NULL REFERENCES outstanding_bills(id), amount_collected NUMERIC(14,2) NOT NULL, payment_mode VARCHAR(20) NOT NULL DEFAULT 'Cash', collection_date DATE NOT NULL, reference_number VARCHAR(100), created_by_user_id INTEGER NULL REFERENCES users(id), created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), CONSTRAINT ck_payment_collections_amount_positive CHECK (amount_collected > 0), CONSTRAINT ck_payment_collections_mode_valid CHECK (payment_mode IN ('Cash', 'UPI', 'Bank Transfer')))",
        "CREATE INDEX IF NOT EXISTS idx_payment_collections_factory_customer ON payment_collections(factory_id, customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_payment_collections_bill_id ON payment_collections(outstanding_bill_id)",
        "CREATE INDEX IF NOT EXISTS idx_payment_collections_payment_id ON payment_collections(payment_id)",
        "CREATE TABLE IF NOT EXISTS bill_payments (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, bill_id INTEGER NOT NULL REFERENCES outstanding_bills(id) ON DELETE CASCADE, amount_allocated NUMERIC(14,2) NOT NULL, payment_date DATE NOT NULL DEFAULT CURRENT_DATE, received_by_name VARCHAR(100) NULL, received_by_role VARCHAR(50) NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), CONSTRAINT ck_bill_payments_amount_allocated_positive CHECK (amount_allocated > 0))",
        "CREATE INDEX IF NOT EXISTS idx_bill_payments_bill_id ON bill_payments(bill_id)",
        "ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS duty_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0",
        "ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_logs_duty_hours_positive",
        "ALTER TABLE attendance_logs ADD CONSTRAINT ck_attendance_logs_duty_hours_positive CHECK (duty_hours > 0)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS advance_payment_discount_percentage NUMERIC(5, 2) DEFAULT 2.00",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS utr_transaction_id VARCHAR(50)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_payment_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_status",
        "ALTER TABLE orders ADD CONSTRAINT ck_orders_status CHECK (status IN ('pending_owner', 'confirmed', 'cancelled', 'adjusted_closed', 'Pending', 'Approved', 'Rejected', 'Received'))",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS variety VARCHAR(100) DEFAULT 'Standard/White'",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS packaging_size_name VARCHAR(100)",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS pieces_per_packet INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS packets_per_box_limit INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS loose_packets INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS total_boxes INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS current_quantity INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE final_product_stock ALTER COLUMN pieces_per_packet SET DEFAULT 1",
        "ALTER TABLE final_product_stock ALTER COLUMN packets_per_box_limit SET DEFAULT 1",
        "ALTER TABLE final_product_stock ALTER COLUMN loose_packets SET DEFAULT 0",
        "ALTER TABLE final_product_stock ALTER COLUMN total_boxes SET DEFAULT 0",
        "ALTER TABLE final_product_stock ALTER COLUMN current_quantity SET DEFAULT 0",
        # Safe backfill: only fills missing/blank variety so NOT NULL can be enforced.
        # User-entered non-blank varieties are preserved.
        "UPDATE final_product_stock SET variety = 'Standard/White' WHERE variety IS NULL OR trim(variety) = ''",
        # Safe backfill: only fills missing/blank packaging labels from product size.
        # Existing packaging_size_name values are preserved.
        "UPDATE final_product_stock SET packaging_size_name = CONCAT(product_size_ml, 'ml Standard Box') WHERE packaging_size_name IS NULL OR trim(packaging_size_name) = ''",
        "ALTER TABLE final_product_stock ALTER COLUMN variety SET NOT NULL",
        "ALTER TABLE final_product_stock ALTER COLUMN packaging_size_name SET NOT NULL",
        "ALTER TABLE final_product_stock DROP CONSTRAINT IF EXISTS uq_final_product_factory_product_pack",
        "ALTER TABLE final_product_stock DROP CONSTRAINT IF EXISTS uq_final_product_factory_product_packaging",
        "ALTER TABLE final_product_stock DROP CONSTRAINT IF EXISTS uq_final_product_factory_product_size_packaging",
        "ALTER TABLE final_product_stock DROP CONSTRAINT IF EXISTS uq_final_product_factory_size_pack",
        "ALTER TABLE final_product_stock DROP CONSTRAINT IF EXISTS uq_final_product_stock_factory_product_packaging",
        "DROP INDEX IF EXISTS uq_final_product_factory_product_pack",
        "DROP INDEX IF EXISTS uq_final_product_factory_product_packaging",
        "DROP INDEX IF EXISTS uq_final_product_factory_product_size_packaging",
        "DROP INDEX IF EXISTS uq_final_product_factory_size_pack",
        "DROP INDEX IF EXISTS uq_final_product_stock_factory_product_packaging",
        "DO $$ DECLARE constraint_row RECORD; BEGIN FOR constraint_row IN SELECT con.conname FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace WHERE rel.relname = 'final_product_stock' AND nsp.nspname = current_schema() AND con.contype = 'u' AND con.conname <> 'uq_final_product_factory_product_variety_pack' AND NOT EXISTS (SELECT 1 FROM unnest(con.conkey) key(attnum) JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = key.attnum WHERE att.attname = 'variety') LOOP EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT IF EXISTS %I', current_schema(), 'final_product_stock', constraint_row.conname); END LOOP; END $$",
        "ALTER TABLE final_product_stock DROP CONSTRAINT IF EXISTS uq_final_product_factory_product_variety_pack",
        "DROP INDEX IF EXISTS uq_final_product_factory_product_variety_pack",
        "CREATE UNIQUE INDEX uq_final_product_factory_product_variety_pack ON final_product_stock (factory_id, product_size_ml, variety, packaging_size_name)",
        "ALTER TABLE finished_goods_stock ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'CUP_FINISHED'",
        "ALTER TABLE finished_goods_stock ADD COLUMN IF NOT EXISTS variant_name VARCHAR(255)",
        "ALTER TABLE finished_goods_stock ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000)",
        "ALTER TABLE finished_goods_stock ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
        # Safe backfill: only fills missing/blank category values required by the
        # category check constraint. Existing categories are preserved.
        "UPDATE finished_goods_stock SET category = 'CUP_FINISHED' WHERE category IS NULL OR trim(category) = ''",
        # Safe backfill: only fills missing/blank variant labels from cup size.
        # Existing variant_name values are preserved.
        "UPDATE finished_goods_stock SET variant_name = CONCAT(cup_size_ml, 'ml_Standard') WHERE variant_name IS NULL OR trim(variant_name) = ''",
        "ALTER TABLE finished_goods_stock DROP CONSTRAINT IF EXISTS ck_finished_goods_stock_category",
        "ALTER TABLE finished_goods_stock ADD CONSTRAINT ck_finished_goods_stock_category CHECK (category IN ('CUP_FINISHED', 'CUP_BLANK', 'CUP_BOTTOM', 'PACKAGING_MATERIAL'))",
        "CREATE INDEX IF NOT EXISTS idx_finished_goods_factory_category ON finished_goods_stock(factory_id, category)",
        "ALTER TABLE packaging_metrics ADD COLUMN IF NOT EXISTS variant_name VARCHAR(100) NOT NULL DEFAULT 'Standard/White'",
        "ALTER TABLE packaging_metrics ALTER COLUMN variant_name SET DEFAULT 'Standard/White'",
        # Safe backfill: only fills missing/blank packaging metric variants.
        # Existing non-blank variant_name values are preserved.
        "UPDATE packaging_metrics SET variant_name = 'Standard/White' WHERE variant_name IS NULL OR trim(variant_name) = ''",
        "ALTER TABLE packaging_metrics DROP CONSTRAINT IF EXISTS uq_packaging_metrics_factory_cup",
        "DROP INDEX IF EXISTS uq_packaging_metrics_factory_cup",
        "ALTER TABLE packaging_metrics DROP CONSTRAINT IF EXISTS uq_packaging_metrics_factory_cup_variant",
        "DROP INDEX IF EXISTS uq_packaging_metrics_factory_cup_variant",
        "CREATE UNIQUE INDEX uq_packaging_metrics_factory_cup_variant ON packaging_metrics (factory_id, cup_size_ml, variant_name)",
        "CREATE TABLE IF NOT EXISTS activity_logs (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, event_type VARCHAR(50) NOT NULL, description TEXT NOT NULL, log_date DATE NOT NULL DEFAULT CURRENT_DATE, created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW())",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS log_date DATE NOT NULL DEFAULT CURRENT_DATE",
        "ALTER TABLE activity_logs ALTER COLUMN factory_id TYPE INTEGER USING factory_id::integer",
        "ALTER TABLE activity_logs ALTER COLUMN factory_id SET NOT NULL",
        "ALTER TABLE activity_logs ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at",
        "ALTER TABLE activity_logs ALTER COLUMN created_at SET DEFAULT NOW()",
        "ALTER TABLE activity_logs ALTER COLUMN created_at SET NOT NULL",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS user_role VARCHAR(100)",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS user_name VARCHAR(255)",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS action_type VARCHAR(100)",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS action_summary TEXT",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS entity_type VARCHAR(100)",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS entity_id INTEGER",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS short_statement TEXT",
        "ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS committed_at TIMESTAMP WITH TIME ZONE",
        # Safe backfill: only fills missing committed_at from the existing created_at
        # timestamp. Existing committed_at values are preserved.
        "UPDATE activity_logs SET committed_at = created_at WHERE committed_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_activity_logs_factory_created ON activity_logs (factory_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_activity_logs_factory_log_date ON activity_logs (factory_id, log_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_activity_logs_factory_committed ON activity_logs (factory_id, committed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_activity_logs_factory_entity ON activity_logs (factory_id, entity_type)",
        "ALTER TABLE activity_logs DROP CONSTRAINT IF EXISTS ck_activity_logs_event_type"
    ]
    if connection is not None:
        for stmt in statements:
            connection.execute(text(stmt))
        return

    with engine.begin() as connection:
        for stmt in statements:
            connection.execute(text(stmt))
