"""租户请求上下文。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """当前请求所在租户。"""

    tenant_id: int
    tenant_code: str | None = None
    tenant_name: str | None = None
    tenant_status: str | None = None
    is_required: bool = True
