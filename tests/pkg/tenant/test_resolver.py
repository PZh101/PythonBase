"""租户解析器测试。"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pkg.tenant.context import TenantContext
from pkg.tenant.resolver import resolve_tenant_id_from_header


def test_tenant_context_is_immutable() -> None:
    """租户上下文应不可变。"""
    context = TenantContext(tenant_id=123, tenant_code="demo", tenant_name="演示租户")

    with pytest.raises(FrozenInstanceError):
        context.tenant_id = 456


def test_resolver_reads_x_tenant_id_header() -> None:
    """租户解析器应从 X-Tenant-Id 请求头读取租户 ID。"""
    app = FastAPI()

    @app.get("/tenant")
    async def read_tenant(tenant_id: int | None = resolve_tenant_id_from_header()):
        return {"tenant_id": tenant_id}

    client = TestClient(app)
    response = client.get("/tenant", headers={"X-Tenant-Id": "123"})

    assert response.status_code == 200
    assert response.json() == {"tenant_id": 123}


def test_resolver_allows_missing_header_for_optional_routes() -> None:
    """未提供租户请求头时，解析器应返回 None 供上层决定是否必需。"""
    app = FastAPI()

    @app.get("/tenant")
    async def read_tenant(tenant_id: int | None = resolve_tenant_id_from_header()):
        return {"tenant_id": tenant_id}

    client = TestClient(app)
    response = client.get("/tenant")

    assert response.status_code == 200
    assert response.json() == {"tenant_id": None}
