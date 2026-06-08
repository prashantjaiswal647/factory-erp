from auth import OWNER_LEVEL_ROLES, check_permissions, get_current_active_user, get_current_user


OWNER_ROLES = OWNER_LEVEL_ROLES
PRODUCTION_ROLES = ["Owner", "Sub-Owner", "Supervisor", "Operator"]
INVENTORY_ROLES = ["Owner", "Sub-Owner", "Supervisor", "Operator"]
SALES_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
PAYMENT_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
EXPENSE_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
FACTORY_VIEW_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
DASHBOARD_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
MACHINE_VIEW_ROLES = ["Owner", "Sub-Owner", "Supervisor"]
