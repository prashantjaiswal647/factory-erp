from auth import check_permissions, get_current_active_user, get_current_user


OWNER_ROLES = ["Owner", "Sub-Owner"]
PRODUCTION_ROLES = ["Owner", "Sub-Owner", "Supervisor", "Operator"]
INVENTORY_ROLES = ["Owner", "Sub-Owner", "Supervisor", "Operator"]
SALES_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
PAYMENT_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
EXPENSE_ROLES = ["Owner", "Sub-Owner", "Supervisor", "Operator", "Worker"]
