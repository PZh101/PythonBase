"""当前租户解析器。"""

from fastapi import Header


def resolve_tenant_id_from_header() -> int | None:
    """声明从 X-Tenant-Id 请求头读取当前租户 ID。"""
    return Header(default=None, alias="X-Tenant-Id")
