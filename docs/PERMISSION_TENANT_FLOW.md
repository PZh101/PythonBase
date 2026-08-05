# 权限、租户与资源隔离业务流程说明

## 1. 当前模块边界

当前项目包含两套相关能力：

- `pkg/security` 与 `pkg/tenant`：通用认证上下文、租户上下文和权限依赖基础能力。
- `app/system` 与 `app/workspace`：根据数据库设计说明书实现的企业组织权限、资源权限、业务空间和临时授权业务模块。

本说明只描述当前代码已经落地的逻辑，不包含知识库相关表和接口。

## 2. 通用安全上下文

### 2.1 `Principal`

`Principal` 表示当前认证主体，包含：

- `user_id`：用户 ID。
- `username`：用户名或展示名。
- `is_platform_admin`：是否平台管理员。
- `authenticated`：是否已认证。

### 2.2 `TenantContext`

`TenantContext` 表示当前请求所在租户，包含：

- `tenant_id`
- `tenant_code`
- `tenant_name`
- `tenant_status`
- `is_required`

当前租户通过请求头 `X-Tenant-Id` 解析。解析器位于 `pkg/tenant/resolver.py`。

### 2.3 `AuthContext`

`AuthContext` 是一次请求的认证与授权快照，包含：

- `principal`
- `tenant`
- `member_id`
- `roles`
- `permissions`

权限集合使用精确字符串匹配，例如 `system:user:add`。权限判断工具位于 `pkg/security/permissions.py`，FastAPI 依赖工厂位于 `pkg/security/dependencies.py`。

## 3. 企业组织与角色权限模块

模块路径：`app/system`

### 3.1 数据模型

当前实现的数据表：

| 表名 | ORM 模型 | 说明 |
| --- | --- | --- |
| `sys_dept` | `SysDept` | 部门表，包含层级路径 `dept_path` 和标签 `dept_tags`。 |
| `sys_user` | `SysUser` | 用户基础信息表。 |
| `sys_user_dept` | `SysUserDept` | 用户-部门关联表，支持一人多部门和主部门。 |
| `sys_role` | `SysRole` | 角色表，包含数据范围 `data_scope` 和扩展规则 `data_scope_rule`。 |
| `sys_menu` | `SysMenu` | 菜单、按钮和 API 资源表。 |
| `sys_role_menu` | `SysRoleMenu` | 角色-菜单/资源关联表。 |
| `sys_user_role` | `SysUserRole` | 用户-角色关联表。 |
| `sys_role_dept` | `SysRoleDept` | 角色-部门关联表，用于自定义数据权限。 |

### 3.2 数据范围约定

`SysRole.data_scope` 目前保留数据库设计文档中的枚举语义：

| 值 | 含义 |
| --- | --- |
| `1` | 全部数据 |
| `2` | 本部门及以下 |
| `3` | 仅本部门 |
| `4` | 仅本人 |
| `5` | 自定义部门 |
| `6` | 按标签 |

当前服务层已校验 `data_scope` 必须在 `1` 到 `6` 之间，并保存 `data_scope_rule`。完整 ABAC SQL 动态拼接暂未实现，后续可基于 `dept_path`、`dept_tags`、`sys_role_dept` 和当前用户部门关系生成查询过滤条件。

### 3.3 核心服务

服务类：`SystemService`

已实现能力：

- 创建部门：`create_dept`
- 查询部门列表：`list_depts`
- 创建用户：`create_user`
- 查询用户列表：`list_users`
- 关联用户和部门：`assign_user_dept`
- 创建角色：`create_role`
- 查询角色列表：`list_roles`
- 创建菜单或资源：`create_menu`
- 查询菜单或资源列表：`list_menus`
- 关联角色和菜单资源：`assign_role_menu`
- 关联用户和角色：`assign_user_role`
- 关联角色和自定义数据权限部门：`assign_role_dept`
- 查询用户权限画像：`get_user_access_profile`

### 3.4 用户权限画像流程

`get_user_access_profile(user_id)` 用于聚合用户的组织与权限信息。

流程：

```text
校验用户存在
  -> 查询 sys_user_dept 获取用户所有部门
  -> 识别 is_primary = 1 的主部门
  -> 查询 sys_user_role + sys_role 获取用户有效角色
  -> 查询 sys_role_menu + sys_menu 获取权限标识
  -> 权限去重并排序
  -> 返回 UserAccessProfileResponse
```

返回内容：

- `user_id`
- `dept_ids`
- `primary_dept_id`
- `role_ids`
- `role_keys`
- `permissions`

### 3.5 API 路由

路由工厂：`create_system_router(db_dependency)`

该函数接收一个返回 `AsyncSession` 的 FastAPI 依赖，返回 `APIRouter`。项目入口可以在数据库初始化后注册它。

当前路由前缀：`/system`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/system/departments` | 创建部门 |
| `GET` | `/system/departments` | 查询部门列表 |
| `POST` | `/system/users` | 创建用户 |
| `GET` | `/system/users` | 查询用户列表 |
| `POST` | `/system/users/{user_id}/departments` | 关联用户和部门 |
| `POST` | `/system/roles` | 创建角色 |
| `GET` | `/system/roles` | 查询角色列表 |
| `POST` | `/system/menus` | 创建菜单或资源 |
| `GET` | `/system/menus` | 查询菜单或资源列表 |
| `POST` | `/system/roles/{role_id}/menus` | 关联角色和菜单资源 |
| `POST` | `/system/users/{user_id}/roles` | 关联用户和角色 |
| `POST` | `/system/roles/{role_id}/departments` | 关联角色和自定义数据权限部门 |
| `GET` | `/system/users/{user_id}/access-profile` | 查询用户权限画像 |

所有响应通过 `ApiResponse` 包装。所有请求和响应模型均继承 `BaseSchema`。

## 4. 业务空间与临时授权模块

模块路径：`app/workspace`

### 4.1 数据模型

当前实现的数据表：

| 表名 | ORM 模型 | 说明 |
| --- | --- | --- |
| `sys_workspace` | `SysWorkspace` | 业务空间表。 |
| `sys_workspace_member` | `SysWorkspaceMember` | 业务空间成员表。 |
| `sys_temp_auth` | `SysTempAuth` | 临时授权表。 |

### 4.2 业务空间成员

空间成员角色使用以下枚举：

- `OWNER`
- `ADMIN`
- `MEMBER`
- `GUEST`

`WorkspaceService.add_member()` 会校验空间存在，并校验角色必须属于以上枚举。

### 4.3 临时授权流程

临时授权用于跨部门协作、紧急处理等场景。

授权字段：

- `user_id`
- `resource_type`
- `resource_id`
- `permission`
- `start_time`
- `end_time`
- `grant_reason`

`WorkspaceService.grant_temp_auth()` 会校验 `end_time` 必须晚于 `start_time`。

### 4.4 临时授权校验流程

`WorkspaceService.has_valid_temp_auth()` 用于判断用户在指定时间点是否拥有临时权限。

流程：

```text
输入 user_id / resource_type / resource_id / permission
  -> 使用当前时间或传入 at_time
  -> 查询 sys_temp_auth
  -> 条件：
       user_id 匹配
       resource_type 匹配
       resource_id 匹配
       permission 匹配
       start_time <= at_time
       end_time >= at_time
  -> 命中返回 True，否则返回 False
```

当前临时授权校验尚未自动接入 `pkg/security` 权限依赖。后续可以在权限拦截流程中先检查常规 RBAC，再调用该服务做临时授权兜底。

### 4.5 API 路由

路由工厂：`create_workspace_router(db_dependency)`

当前路由前缀：`/workspaces`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/workspaces` | 创建业务空间 |
| `GET` | `/workspaces` | 查询业务空间列表 |
| `POST` | `/workspaces/{workspace_id}/members` | 添加空间成员 |
| `GET` | `/workspaces/{workspace_id}/members` | 查询空间成员 |
| `POST` | `/workspaces/temp-auth` | 授予临时权限 |
| `GET` | `/workspaces/temp-auth/check` | 校验临时权限是否有效 |

所有响应通过 `ApiResponse` 包装。所有请求和响应模型均继承 `BaseSchema`。

## 5. SQL 脚本

初始化 SQL 文件位于：

```text
scripts/2026_08_04_enterprise_permission_schema.sql
```

该脚本包含：

- 组织与用户表
- 角色与菜单资源表
- 用户、角色、部门、菜单关联表
- 临时授权表
- 业务空间和空间成员表

不包含知识库相关表。

## 6. 推荐接入方式

应用启动时完成数据库初始化后，可按以下方式注册路由：

```python
from app.system.routes import create_system_router
from app.workspace.routes import create_workspace_router
from pkg.database.dependencies import create_db_session_dependency

db_dependency = create_db_session_dependency(database_manager)
app.include_router(create_system_router(db_dependency))
app.include_router(create_workspace_router(db_dependency))
```

如果读接口希望不自动提交事务，可以使用只读 Session 依赖注册独立路由或调整路由工厂入参。

## 7. 尚未实现的能力

当前代码保留但尚未完整实现以下能力：

- 根据 `data_scope` 自动生成业务数据过滤 SQL。
- 基于 `dept_path` 的“本部门及以下”数据范围查询封装。
- 基于 `dept_tags` 与 `data_scope_rule` 的 ABAC 标签匹配。
- 临时授权自动接入统一权限依赖。
- 工作空间内资源级权限继承。
- 知识库空间、目录、文档和 ACL。

这些能力可以在当前模型和服务基础上继续增量实现。
