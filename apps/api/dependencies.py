from auth import check_permissions, get_current_active_user, get_current_user


OWNER_ROLES = ["Owner"]
PRODUCTION_ROLES = ["Owner", "Supervisor", "Operator"]
INVENTORY_ROLES = ["Owner", "Supervisor", "Operator"]
SALES_ROLES = ["Owner", "Supervisor"]
PAYMENT_ROLES = ["Owner", "Supervisor"]
