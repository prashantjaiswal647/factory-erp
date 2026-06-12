# Factory Delete Relationship Map

This map documents the current SQLAlchemy/PostgreSQL relationships considered by the Super Admin factory delete cascade.

| Table / Model | Relation Field | Delete Behavior | Reason |
| --- | --- | --- | --- |
| factories / Factory | id, owner_id, owner_phone_number | hard delete last | Target factory row. Owner references are cleared before deleting users. |
| users / User | factory_id | hard delete for users in deleted factory | Current auth model assigns one factory per user. Super Admin is not stored here. |
| machine_templates / MachineTemplate | creator_id -> users.id | hard delete for creators in deleted factory | User-owned AI/template records block user deletion. |
| app_usage_logs / AppUsageLog | factory_id, user_id | hard delete | Factory/user activity logs are tenant records. |
| token_usage_logs / TokenUsageLog | factory_id, user_id | hard delete | Factory/user AI token logs are tenant records. |
| subscription_payments / SubscriptionPayment | factory_id | hard delete | Factory subscription/payment history belongs to deleted tenant. |
| custom_plan_enquiries / CustomPlanEnquiry | factory_id | hard delete | Factory-linked sales/billing enquiry metadata. |
| demo_booking_requests / DemoBookingRequest | factory_id | hard delete | Factory-linked booking metadata. |
| payments / Payment | factory_id, sale_id | hard delete before daily_sales | Payment records belong to factory sales. |
| daily_sales / DailySale | factory_id, customer_id | hard delete before customers | Sales records belong to tenant. |
| sales_invoices / SalesInvoice | factory_id, customer_id, packaging_profile_id | hard delete before customers/products | Invoice records belong to tenant. |
| orders / Order | factory_id, customer_id | hard delete after order_items | Tenant sales orders. |
| order_items / OrderItem | factory_id, order_id, product_id | hard delete before orders/products | Child records must be deleted first. |
| customers / Customer | factory_id | hard delete after customer child rows | Tenant customer master data. |
| customer_activities / CustomerActivity | factory_id, customer_id | hard delete before customers | Customer child activity. |
| production_logs / ProductionLog | factory_id, packaging_profile_id | hard delete before packaging profiles | Tenant production logs. |
| daily_productions / DailyProduction | factory_id, worker_id, machine_id | hard delete before workers/machines | Tenant production records. |
| factory_inventory / FactoryInventory | factory_id | hard delete | Tenant inventory records. |
| inventory / Inventory | factory_id | hard delete after packaging profiles | Tenant raw/packaging inventory. |
| raw_materials / RawMaterial | factory_id | hard delete | Tenant raw materials. |
| raw_material_metrics / RawMaterialMetrics | factory_id | hard delete after costing outputs | Tenant material metrics referenced by costing outputs. |
| packaging_metrics / PackagingMetrics | factory_id | hard delete after costing outputs | Tenant packaging metrics referenced by costing outputs. |
| packaging_profiles / PackagingProfile | factory_id, inventory ids | hard delete after production/sales/product stock | Tenant product/SKU packaging profiles. |
| finished_goods_stock / FinishedGoodsStock | factory_id, packaging_profile_id | hard delete after order_items | Tenant product stock. |
| final_product_stock / FinalProductStock | factory_id | hard delete | Tenant finished product stock. |
| blank_stock / BlankStock | factory_id | hard delete | Tenant stock data. |
| bottom_stock / BottomStock | factory_id | hard delete | Tenant stock data. |
| box_stock / BoxStock | factory_id | hard delete | Tenant stock data. |
| plastic_stock / PlasticStock | factory_id | hard delete | Tenant stock data. |
| polybag_stock / PolybagStock | factory_id | hard delete | Tenant stock data. |
| machines / Machine | factory_id | hard delete after daily production | Tenant machines. |
| machine_onboardings / MachineOnboarding | factory_id | hard delete | Tenant machine onboarding data. |
| factory_settings / FactorySettings | factory_id | hard delete | Tenant settings. |
| factory_expenses / FactoryExpense | factory_id | hard delete | Tenant expenses. |
| expense_logs / ExpenseLog | factory_id | hard delete | Tenant expenses. |
| employees / Employee | factory_id | hard delete after attendance/advance rows | Tenant staff records. |
| workers / Worker | factory_id | hard delete after attendance/production/hisab rows | Tenant worker records. |
| attendance_logs / AttendanceLog | factory_id, employee_id, worker_id | hard delete before employees/workers | Tenant attendance child data. |
| advance_payments / AdvancePayment | factory_id, employee_id, worker_id | hard delete before employees/workers | Tenant payroll child data. |
| hisab_settlements / HisabSettlement | factory_id, worker_id | hard delete before workers | Tenant payroll child data. |
| material_yields / MaterialYield | factory_id | hard delete | Tenant production metrics. |
| costing_master / CostingMaster | factory_id | hard delete | Tenant costing settings. |
| costing_output_master / CostingOutputMaster | factory_id, metric ids | hard delete before metrics | Tenant costing outputs. |
| super_admin_audit_logs / SuperAdminAuditLog | entity_type/entity_id | keep | Compliance/admin history is intentionally retained. New delete audit logs must not be deleted. |
| OTP/session/JWT secrets | phone/user credentials | keep unless user row is deleted | Not factory data unless represented by users linked to the factory. |
| global config tables | no factory_id | keep | Not tenant-owned data. |

Owner rule:

- If the owner user has `factory_id` equal to the deleted factory, the owner is deleted with that factory because the current schema has one `factory_id` per user.
- If an owner reference points outside the deleted factory, the owner is kept.
- If future schema supports multi-factory owners, the cascade should remove only the deleted factory relationship and keep the owner active.

File/upload note:

- No dedicated factory-linked upload/file metadata table was found in the current SQLAlchemy model scan. Physical file deletion is therefore not implemented here.
