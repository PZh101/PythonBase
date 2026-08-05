"""企业组织与权限 ORM 模型测试。"""

from app.system.models import (
    SysDept,
    SysMenu,
    SysRole,
    SysRoleDept,
    SysRoleMenu,
    SysUser,
    SysUserDept,
    SysUserRole,
)


def test_system_table_names_are_stable() -> None:
    """系统权限相关表名应与数据库设计文档保持一致。"""
    assert SysDept.__tablename__ == "sys_dept"
    assert SysUser.__tablename__ == "sys_user"
    assert SysUserDept.__tablename__ == "sys_user_dept"
    assert SysRole.__tablename__ == "sys_role"
    assert SysMenu.__tablename__ == "sys_menu"
    assert SysRoleMenu.__tablename__ == "sys_role_menu"
    assert SysUserRole.__tablename__ == "sys_user_role"
    assert SysRoleDept.__tablename__ == "sys_role_dept"


def test_role_contains_data_scope_columns() -> None:
    """角色表应包含数据范围策略字段。"""
    assert "data_scope" in SysRole.__table__.columns
    assert "data_scope_rule" in SysRole.__table__.columns


def test_dept_contains_path_and_tags_columns() -> None:
    """部门表应包含层级路径和标签字段。"""
    assert "dept_path" in SysDept.__table__.columns
    assert "dept_tags" in SysDept.__table__.columns

