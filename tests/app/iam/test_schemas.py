"""IAM Pydantic 模型测试。"""

from app.iam.schemas import TenantResponse
from pkg.common.api import BaseSchema


def test_tenant_response_extends_base_schema_and_serializes_camel_case() -> None:
    """租户响应模型必须继承 BaseSchema 并输出驼峰字段。"""
    response = TenantResponse(tenant_id=123, tenant_code="demo", tenant_name="演示租户", status="active")

    assert isinstance(response, BaseSchema)
    assert response.model_dump(mode="json") == {
        "tenantId": "123",
        "tenantCode": "demo",
        "tenantName": "演示租户",
        "status": "active",
    }
