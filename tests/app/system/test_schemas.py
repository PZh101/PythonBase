"""企业组织与权限 API 模型测试。"""

from app.system.schemas import DeptResponse, UserAccessProfileResponse
from pkg.common.api import BaseSchema


def test_dept_response_uses_base_schema_and_camel_case() -> None:
    """部门响应模型应继承 BaseSchema 并输出驼峰字段。"""
    response = DeptResponse(
        id=1,
        parent_id=0,
        dept_name="研发部",
        dept_path="/1/",
        dept_tags=["研发"],
        sort_order=1,
        status=1,
        created_at="2026-08-04 10:00:00",
        updated_at="2026-08-04 10:00:00",
    )

    assert isinstance(response, BaseSchema)
    assert response.model_dump(mode="json")["deptName"] == "研发部"
    assert response.model_dump(mode="json")["id"] == "1"


def test_user_access_profile_serializes_safe_bigint_list() -> None:
    """用户权限画像中的 ID 列表应按 JSON 安全大整数序列化。"""
    response = UserAccessProfileResponse(
        user_id=1,
        dept_ids=[10, 20],
        primary_dept_id=10,
        role_ids=[100],
        role_keys=["admin"],
        permissions=["system:user:add"],
    )

    dumped = response.model_dump(mode="json")
    assert dumped["userId"] == "1"
    assert dumped["deptIds"] == ["10", "20"]

