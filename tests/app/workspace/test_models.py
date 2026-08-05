"""业务空间与临时授权 ORM 模型测试。"""

from app.workspace.models import SysTempAuth, SysWorkspace, SysWorkspaceMember


def test_workspace_table_names_are_stable() -> None:
    """业务空间相关表名应与数据库设计文档保持一致。"""
    assert SysTempAuth.__tablename__ == "sys_temp_auth"
    assert SysWorkspace.__tablename__ == "sys_workspace"
    assert SysWorkspaceMember.__tablename__ == "sys_workspace_member"


def test_temp_auth_contains_validity_columns() -> None:
    """临时授权表应包含有效期字段。"""
    assert "start_time" in SysTempAuth.__table__.columns
    assert "end_time" in SysTempAuth.__table__.columns

