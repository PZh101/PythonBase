"""企业组织、用户、角色和资源权限数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


class SystemRepository:
    """企业组织与权限数据访问仓储。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_dept(self, data: dict) -> SysDept:
        """创建部门。"""
        dept = SysDept(**data)
        self.db.add(dept)
        await self.db.flush()
        await self.db.refresh(dept)
        return dept

    async def list_depts(self) -> list[SysDept]:
        """查询部门列表。"""
        result = await self.db.execute(select(SysDept).order_by(SysDept.sort_order.asc(), SysDept.id.asc()))
        return list(result.scalars().all())

    async def get_dept(self, dept_id: int) -> SysDept | None:
        """按 ID 查询部门。"""
        result = await self.db.execute(select(SysDept).where(SysDept.id == dept_id))
        return result.scalars().first()

    async def create_user(self, data: dict) -> SysUser:
        """创建用户。"""
        user = SysUser(**data)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def list_users(self) -> list[SysUser]:
        """查询用户列表。"""
        result = await self.db.execute(select(SysUser).order_by(SysUser.id.asc()))
        return list(result.scalars().all())

    async def get_user(self, user_id: int) -> SysUser | None:
        """按 ID 查询用户。"""
        result = await self.db.execute(select(SysUser).where(SysUser.id == user_id))
        return result.scalars().first()

    async def assign_user_dept(self, *, user_id: int, dept_id: int, is_primary: int) -> SysUserDept:
        """关联用户和部门。"""
        relation = SysUserDept(user_id=user_id, dept_id=dept_id, is_primary=is_primary)
        self.db.add(relation)
        await self.db.flush()
        await self.db.refresh(relation)
        return relation

    async def list_user_depts(self, user_id: int) -> list[SysUserDept]:
        """查询用户关联部门。"""
        result = await self.db.execute(select(SysUserDept).where(SysUserDept.user_id == user_id))
        return list(result.scalars().all())

    async def create_role(self, data: dict) -> SysRole:
        """创建角色。"""
        role = SysRole(**data)
        self.db.add(role)
        await self.db.flush()
        await self.db.refresh(role)
        return role

    async def list_roles(self) -> list[SysRole]:
        """查询角色列表。"""
        result = await self.db.execute(select(SysRole).order_by(SysRole.id.asc()))
        return list(result.scalars().all())

    async def get_role(self, role_id: int) -> SysRole | None:
        """按 ID 查询角色。"""
        result = await self.db.execute(select(SysRole).where(SysRole.id == role_id))
        return result.scalars().first()

    async def create_menu(self, data: dict) -> SysMenu:
        """创建菜单或资源。"""
        menu = SysMenu(**data)
        self.db.add(menu)
        await self.db.flush()
        await self.db.refresh(menu)
        return menu

    async def list_menus(self) -> list[SysMenu]:
        """查询菜单或资源列表。"""
        result = await self.db.execute(select(SysMenu).order_by(SysMenu.sort_order.asc(), SysMenu.id.asc()))
        return list(result.scalars().all())

    async def get_menu(self, menu_id: int) -> SysMenu | None:
        """按 ID 查询菜单或资源。"""
        result = await self.db.execute(select(SysMenu).where(SysMenu.id == menu_id))
        return result.scalars().first()

    async def assign_role_menu(self, *, role_id: int, menu_id: int) -> SysRoleMenu:
        """关联角色和菜单。"""
        relation = SysRoleMenu(role_id=role_id, menu_id=menu_id)
        self.db.add(relation)
        await self.db.flush()
        await self.db.refresh(relation)
        return relation

    async def assign_user_role(self, *, user_id: int, role_id: int) -> SysUserRole:
        """关联用户和角色。"""
        relation = SysUserRole(user_id=user_id, role_id=role_id)
        self.db.add(relation)
        await self.db.flush()
        await self.db.refresh(relation)
        return relation

    async def assign_role_dept(self, *, role_id: int, dept_id: int) -> SysRoleDept:
        """关联角色和自定义数据权限部门。"""
        relation = SysRoleDept(role_id=role_id, dept_id=dept_id)
        self.db.add(relation)
        await self.db.flush()
        await self.db.refresh(relation)
        return relation

    async def list_user_roles(self, user_id: int) -> list[SysRole]:
        """查询用户拥有的角色。"""
        result = await self.db.execute(
            select(SysRole)
            .join(SysUserRole, SysUserRole.role_id == SysRole.id)
            .where(SysUserRole.user_id == user_id, SysRole.status == 1)
        )
        return list(result.scalars().all())

    async def list_permission_codes_by_role_ids(self, role_ids: list[int]) -> list[str]:
        """按角色 ID 查询权限标识。"""
        if not role_ids:
            return []
        result = await self.db.execute(
            select(SysMenu.permission)
            .join(SysRoleMenu, SysRoleMenu.menu_id == SysMenu.id)
            .where(SysRoleMenu.role_id.in_(role_ids), SysMenu.permission.is_not(None), SysMenu.status == 1)
        )
        return [permission for permission in result.scalars().all() if permission]


