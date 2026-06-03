from contextvars import ContextVar
from typing import Optional

_tenant_id: ContextVar[Optional[int]] = ContextVar("tenant_id", default=None)

def set_current_tenant_id(tenant_id: Optional[int]) -> None:
    _tenant_id.set(tenant_id)

def get_current_tenant_id() -> Optional[int]:
    return _tenant_id.get()

def clear_current_tenant_id() -> None:
    _tenant_id.set(None)
