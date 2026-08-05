"""企业组织、用户、角色和资源权限业务服务。"""

from pkg.common.exceptions import BadRequestException, NotFoundException

from app.system.repository import SystemRepository
from app.system.schemas import (
    DeptCreateRequest,
    MenuCreateRequest,
    RoleCreateRequest,
    UserAccessProfileResponse,
    UserCreateRequest,
)


class SystemService:
    """企业组织与权限业务服务。"""

    def __init__(self, repository: SystemRepository) -> None:
        self.repository = repository

    async def create_dept(self, body: DeptCreateRequest):
        """创建部门。"""
        return await self.repository.create_dept(body.model_dump())

    async def list_depts(self):
        """查询部门列表。"""
        return await self.repository.list_depts()

    async def create_user(self, body: UserCreateRequest):
        """创建用户。"""
        return await self.repository.create_user(body.model_dump())

    async def list_users(self):
        """查询用户列表。"""
        return await self.repository.list_users()

    async def assign_user_dept(self, *, user_id: int, dept_id: int, is_primary: int):
        """关联用户和部门。"""
        await self._require_user(user_id)
        await self._require_dept(dept_id)
        if is_primary not in (0, 1):
            raise BadRequestException("is_primary 只能为 0 或 1")
        return await self.repository.assign_user_dept(user_id=user_id, dept_id=dept_id, is_primary=is_primary)

    async def create_role(self, body: RoleCreateRequest):
        """创建角色。"""
        if body.data_scope not in (1, 2, 3, 4, 5, 6):
            raise BadRequestException("data_scope 必须在 1 到 6 之间")
        return await self.repository.create_role(body.model_dump())

    async def list_roles(self):
        """查询角色列表。"""
        return await self.repository.list_roles()

    async def create_menu(self, body: MenuCreateRequest):
        """创建菜单或资源。"""
        return await self.repository.create_menu(body.model_dump())

    async def list_menus(self):
        """查询菜单或资源列表。"""
        return await self.repository.list_menus()

    async def assign_role_menu(self, *, role_id: int, menu_id: int):
        """关联角色和菜单资源。"""
        await self._require_role(role_id)
        await self._require_menu(menu_id)
        return await self.repository.assign_role_menu(role_id=role_id, menu_id=menu_id)

    async def assign_user_role(self, *, user_id: int, role_id: int):
        """关联用户和角色。"""
        await self._require_user(user_id)
        await self._require_role(role_id)
        return await self.repository.assign_user_role(user_id=user_id, role_id=role_id)

    async def assign_role_dept(self, *, role_id: int, dept_id: int):
        """关联角色和自定义数据权限部门。"""
        await self._require_role(role_id)
        await self._require_dept(dept_id)
        return await self.repository.assign_role_dept(role_id=role_id, dept_id=dept_id)

    async def get_user_access_profile(self, user_id: int) -> UserAccessProfileResponse:
        """聚合用户部门、角色和功能权限画像。"""
        await self._require_user(user_id)
        user_depts = await self.repository.list_user_depts(user_id)
        roles = await self.repository.list_user_roles(user_id)
        role_ids = [role.id for role in roles]
        permissions = sorted(set(await self.repository.list_permission_codes_by_role_ids(role_ids)))
        primary_dept_id = next((item.dept_id for item in user_depts if item.is_primary == 1), None)
        return UserAccessProfileResponse(
            user_id=user_id,
            dept_ids=[item.dept_id for item in user_depts],
            primary_dept_id=primary_dept_id,
            role_ids=role_ids,
            role_keys=[role.role_key for role in roles],
            permissions=permissions,
        )

    async def _require_user(self, user_id: int) -> None:
        """确认用户存在。"""
        if await self.repository.get_user(user_id) is None:
            raise NotFoundException("用户不存在")

    async def _require_dept(self, dept_id: int) -> None:
        """确认部门存在。"""
        if await self.repository.get_dept(dept_id) is None:
            raise NotFoundException("部门不存在")

    async def _require_role(self, role_id: int) -> None:
        """确认角色存在。"""
        if await self.repository.get_role(role_id) is None:
            raise NotFoundException("角色不存在")

    async def _require_menu(self, menu_id: int) -> None:
        """确认菜单或资源存在。"""
        if await self.repository.get_menu(menu_id) is None:
            raise NotFoundException("菜单或资源不存在")

