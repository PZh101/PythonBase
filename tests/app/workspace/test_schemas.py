"""业务空间与临时授权 API 模型测试。"""

from app.workspace.schemas import TempAuthCheckResponse, WorkspaceResponse
from pkg.common.api import BaseSchema


def test_workspace_response_uses_base_schema_and_camel_case() -> None:
    """业务空间响应模型应继承 BaseSchema 并输出驼峰字段。"""
    response = WorkspaceResponse(
        id=1,
        space_name="项目空间",
        space_desc=None,
        owner_id=10,
        status=1,
        created_at="2026-08-04 10:00:00",
    )

    assert isinstance(response, BaseSchema)
    assert response.model_dump(mode="json")["spaceName"] == "项目空间"
    assert response.model_dump(mode="json")["ownerId"] == "10"


def test_temp_auth_check_response_is_base_schema() -> None:
    """临时授权校验响应模型应继承 BaseSchema。"""
    assert isinstance(TempAuthCheckResponse(allowed=True), BaseSchema)

