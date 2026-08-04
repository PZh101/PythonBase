"""IAM ORM 模型测试。"""

from app.iam.models import (
    IamPermission,
    IamRole,
    IamTenant,
    IamTenantMember,
    IamUser,
)


def test_table_names_are_stable() -> None:
    """IAM 表名应稳定，便于迁移脚本和运维识别。"""
    assert IamUser.__tablename__ == "iam_users"
    assert IamTenant.__tablename__ == "iam_tenants"
    assert IamTenantMember.__tablename__ == "iam_tenant_members"
    assert IamRole.__tablename__ == "iam_roles"
    assert IamPermission.__tablename__ == "iam_permissions"


def test_role_and_permission_are_tenant_scoped() -> None:
    """角色和成员关系应包含 tenant_id 以支持租户内差异化授权。"""
    assert "tenant_id" in IamRole.__table__.columns
    assert "tenant_id" in IamTenantMember.__table__.columns
