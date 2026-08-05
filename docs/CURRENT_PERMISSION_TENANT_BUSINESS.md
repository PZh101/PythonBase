# 当前权限、租户与资源隔离业务逻辑梳理

## 1. 文档范围

本文整理当前项目已经落地的权限、租户、组织、业务空间与临时授权逻辑，重点说明模块职责、数据关系、请求流程和当前边界。

本文只描述当前代码状态，不包含知识库相关业务。

## 2. 总体分层

当前权限与租户能力分为三层：

```text
通用框架层 pkg/
  -> pkg/security：认证主体、授权上下文、权限校验依赖
  -> pkg/tenant：租户上下文、租户字段约定、租户解析
  -> pkg/database：通用 CRUD、租户感知 CRUD

基础 IAM 层 app/iam
  -> 用户、租户、租户成员、租户内角色、权限码、角色权限关系
  -> 按用户和当前租户加载 AuthContext

企业业务权限层 app/system、app/workspace
  -> app/system：部门、用户、角色、菜单/API 权限、数据权限范围
  -> app/workspace：业务空间、空间成员、临时授权
```

依赖方向保持为：

```text
app/* -> pkg/*
pkg/* 不依赖 app/*
```

`pkg/security.providers.AuthContextProvider` 是框架层与应用层之间的边界协议。框架只知道“如何使用 AuthContext”，不知道用户、角色、权限具体存在哪些表中。

## 3. 通用租户与权限上下文

### 3.1 当前认证主体

`pkg/security/context.py` 中的 `Principal` 表示当前登录用户：

| 字段 | 说明 |
| --- | --- |
| `user_id` | 当前用户 ID。 |
| `username` | 用户名或展示名。 |
| `is_platform_admin` | 是否平台管理员。 |
| `authenticated` | 是否已认证。 |

平台管理员在当前通用权限判断中可以绕过角色和权限码校验。

### 3.2 当前租户

`pkg/tenant/context.py` 中的 `TenantContext` 表示当前请求所在租户：

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 当前租户 ID。 |
| `tenant_code` | 租户编码。 |
| `tenant_name` | 租户名称。 |
| `tenant_status` | 租户状态。 |
| `is_required` | 当前上下文是否要求租户。 |

当前租户由请求头传入：

```text
X-Tenant-Id: 10001
```

当前用户由请求头传入：

```text
X-User-Id: 20001
```

### 3.3 授权上下文

`AuthContext` 是一次请求内的认证与授权快照：

| 字段 | 说明 |
| --- | --- |
| `principal` | 当前认证主体。 |
| `tenant` | 当前租户上下文，可为空。 |
| `member_id` | 用户在当前租户内的成员 ID，可为空。 |
| `roles` | 当前租户下的角色编码集合。 |
| `permissions` | 当前租户下的权限码集合。 |

权限集合当前只支持精确字符串匹配，例如：

```text
system:user:add
role:assign
tenant:settings:update
```

尚未实现通配符、表达式或 ABAC 规则引擎。

## 4. IAM 租户 RBAC 逻辑

模块路径：`app/iam`

### 4.1 数据模型

| 模型 | 表 | 作用 |
| --- | --- | --- |
| `IamUser` | `iam_users` | 平台用户。 |
| `IamTenant` | `iam_tenants` | 租户。 |
| `IamTenantMember` | `iam_tenant_members` | 用户在租户内的成员身份。 |
| `IamRole` | `iam_roles` | 租户内角色。 |
| `IamPermission` | `iam_permissions` | 系统权限定义。 |
| `IamTenantMemberRole` | `iam_tenant_member_roles` | 成员和角色关系。 |
| `IamRolePermission` | `iam_role_permissions` | 角色和权限关系。 |

核心关系：

```text
IamUser
  -> IamTenantMember
  -> IamTenant

IamTenantMember
  -> IamTenantMemberRole
  -> IamRole
  -> IamRolePermission
  -> IamPermission
```

角色归属于租户，`iam_roles` 使用 `(tenant_id, code)` 保证同一租户内角色编码唯一。权限码是系统级定义，角色通过关系表绑定权限。

### 4.2 加载授权上下文流程

服务：`app/iam/service.py` 中的 `IamAuthContextService`

```text
读取 X-User-Id 和 X-Tenant-Id
  -> 查询启用状态用户
  -> 构造 Principal
  -> 如果没有 X-Tenant-Id：
       返回不带租户、不带成员、不带角色权限的 AuthContext
  -> 如果有 X-Tenant-Id：
       查询 active 租户
       查询用户在该租户内的 active 成员身份
       非平台管理员且成员不存在时拒绝访问
       查询成员角色编码
       查询成员权限编码
       返回完整 AuthContext
```

异常语义：

| 场景 | 行为 |
| --- | --- |
| 未传 `X-User-Id` | 抛出认证失败异常。 |
| 用户不存在或未启用 | 抛出认证失败异常。 |
| 租户不存在或非 active | 抛出租户访问拒绝异常。 |
| 用户不是租户成员且不是平台管理员 | 抛出租户访问拒绝异常。 |
| 平台管理员进入租户但没有成员身份 | 允许生成租户上下文，角色和权限为空。 |

### 4.3 FastAPI 权限依赖流程

`pkg/security/dependencies.py` 提供依赖工厂：

| 依赖 | 作用 |
| --- | --- |
| `create_auth_context_dependency(provider)` | 从请求头加载 `AuthContext` 并写入 `request.state.auth_context`。 |
| `require_tenant()` | 要求当前请求存在租户和成员身份。 |
| `require_permission(permission)` | 要求拥有指定权限。 |
| `require_any_permission(*permissions)` | 要求拥有任意一个权限。 |
| `require_role(role)` | 要求拥有指定角色。 |

典型接口流程：

```text
HTTP 请求
  -> create_auth_context_dependency 加载 AuthContext
  -> require_tenant 校验租户上下文
  -> require_permission 校验权限码
  -> 路由执行业务逻辑
```

当前权限判断规则：

```text
如果 principal.is_platform_admin = True：
  角色和权限校验直接通过
否则：
  按 AuthContext.roles / AuthContext.permissions 精确匹配
```

注意：`require_tenant()` 当前要求同时存在 `tenant` 和 `member_id`。因此平台管理员如果没有租户成员身份，虽然可以绕过角色和权限校验，但不能通过 `require_tenant()`。

## 5. 租户数据隔离逻辑

### 5.1 ORM 约定

`pkg/tenant/mixins.py` 提供 `TenantMixin`：

```text
tenant_id: bigint
```

需要租户隔离的业务表应带有 `tenant_id` 字段。平台级基础表不需要带 `tenant_id`，例如用户表、租户表、权限定义表。

### 5.2 租户感知 CRUD

`pkg/database/tenant_crud.py` 中的 `TenantAwareCrud` 会在常用数据操作中强制附加 `tenant_id`：

| 方法 | 租户隔离行为 |
| --- | --- |
| `get(db, tenant_id, id)` | 按 `tenant_id + 主键` 查询。 |
| `create(db, tenant_id, obj_in)` | 创建时自动写入 `tenant_id`。 |
| `update(db, tenant_id, id, obj_update)` | 只更新当前租户内记录，并忽略外部传入的 `tenant_id`。 |
| `delete_by_id(db, tenant_id, id)` | 只删除当前租户内记录。 |
| `list_page(db, tenant_id, ...)` | 分页查询自动附加租户过滤。 |
| `count(db, tenant_id, ...)` | 统计自动附加租户过滤。 |

推荐业务数据访问流程：

```text
AuthContext.tenant.tenant_id
  -> 传入 TenantAwareCrud
  -> 查询、更新、删除自动附加 tenant_id
  -> 避免跨租户读取或修改
```

当前项目已提供租户感知 CRUD 基础能力，但新增业务模型是否接入该基类，需要按业务模块逐步落地。

## 6. 企业组织权限逻辑

模块路径：`app/system`

### 6.1 数据模型

| 模型 | 表 | 作用 |
| --- | --- | --- |
| `SysDept` | `sys_dept` | 部门，支持父子层级、路径和标签。 |
| `SysUser` | `sys_user` | 企业用户基础信息。 |
| `SysUserDept` | `sys_user_dept` | 用户和部门关系，支持主部门。 |
| `SysRole` | `sys_role` | 企业角色，包含数据权限范围。 |
| `SysMenu` | `sys_menu` | 菜单、按钮、API 资源。 |
| `SysRoleMenu` | `sys_role_menu` | 角色和菜单/API 权限关系。 |
| `SysUserRole` | `sys_user_role` | 用户和角色关系。 |
| `SysRoleDept` | `sys_role_dept` | 角色自定义数据权限部门。 |

### 6.2 功能权限流程

功能权限以 `sys_menu.permission` 作为权限标识，由角色绑定菜单或 API 资源得到。

```text
创建菜单/API 资源
  -> 创建角色
  -> 角色绑定菜单/API 资源
  -> 用户绑定角色
  -> get_user_access_profile 聚合权限码
```

`SystemService.get_user_access_profile(user_id)` 聚合结果包括：

| 字段 | 说明 |
| --- | --- |
| `user_id` | 用户 ID。 |
| `dept_ids` | 用户所属部门 ID 列表。 |
| `primary_dept_id` | 用户主部门 ID。 |
| `role_ids` | 用户角色 ID 列表。 |
| `role_keys` | 用户角色编码列表。 |
| `permissions` | 由角色菜单关系聚合出的权限码列表。 |

聚合流程：

```text
校验用户存在
  -> 查询用户部门关系
  -> 查询用户角色
  -> 根据角色查询菜单/API 权限码
  -> 权限去重和排序
  -> 返回用户权限画像
```

### 6.3 数据权限范围

`SysRole.data_scope` 当前保留以下枚举：

| 值 | 含义 |
| --- | --- |
| `1` | 全部数据 |
| `2` | 本部门及以下 |
| `3` | 仅本部门 |
| `4` | 仅本人 |
| `5` | 自定义部门 |
| `6` | 按标签 |

当前已实现的逻辑：

- 创建角色时校验 `data_scope` 必须在 `1` 到 `6` 之间。
- 支持保存 `data_scope_rule`。
- 支持通过 `SysRoleDept` 维护角色自定义部门范围。

当前尚未实现的逻辑：

- 尚未根据 `data_scope` 自动生成业务 SQL 过滤条件。
- 尚未基于 `dept_path` 自动处理“本部门及以下”。
- 尚未基于 `dept_tags` 和 `data_scope_rule` 实现标签式 ABAC 过滤。

## 7. 业务空间与临时授权逻辑

模块路径：`app/workspace`

### 7.1 数据模型

| 模型 | 表 | 作用 |
| --- | --- | --- |
| `SysWorkspace` | `sys_workspace` | 业务空间。 |
| `SysWorkspaceMember` | `sys_workspace_member` | 空间成员和空间角色。 |
| `SysTempAuth` | `sys_temp_auth` | 指定用户、资源、权限和时间窗口的临时授权。 |

### 7.2 空间成员流程

空间成员角色：

```text
OWNER
ADMIN
MEMBER
GUEST
```

添加成员流程：

```text
校验业务空间存在
  -> 校验角色值属于 OWNER / ADMIN / MEMBER / GUEST
  -> 写入 sys_workspace_member
```

当前空间成员角色尚未自动接入 `pkg/security` 的 `require_role()` 或 `require_permission()` 依赖。

### 7.3 临时授权流程

临时授权用于跨部门协作、应急处理或短期资源访问。

授予流程：

```text
接收 user_id / resource_type / resource_id / permission / start_time / end_time
  -> 校验 end_time 晚于 start_time
  -> 写入 sys_temp_auth
```

校验流程：

```text
输入 user_id / resource_type / resource_id / permission / at_time
  -> 查询 sys_temp_auth
  -> 条件：
       user_id 相等
       resource_type 相等
       resource_id 相等
       permission 相等
       start_time <= at_time
       end_time >= at_time
  -> 命中返回 True，否则返回 False
```

当前临时授权是独立服务能力，尚未自动作为统一权限依赖的兜底逻辑。

## 8. 当前 API 边界

### 8.1 System 路由

路由工厂：`create_system_router(db_dependency)`

前缀：`/system`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/system/departments` | 创建部门。 |
| `GET` | `/system/departments` | 查询部门列表。 |
| `POST` | `/system/users` | 创建用户。 |
| `GET` | `/system/users` | 查询用户列表。 |
| `POST` | `/system/users/{user_id}/departments` | 关联用户和部门。 |
| `POST` | `/system/roles` | 创建角色。 |
| `GET` | `/system/roles` | 查询角色列表。 |
| `POST` | `/system/menus` | 创建菜单/API 资源。 |
| `GET` | `/system/menus` | 查询菜单/API 资源列表。 |
| `POST` | `/system/roles/{role_id}/menus` | 关联角色和菜单/API 资源。 |
| `POST` | `/system/users/{user_id}/roles` | 关联用户和角色。 |
| `POST` | `/system/roles/{role_id}/departments` | 关联角色和自定义数据权限部门。 |
| `GET` | `/system/users/{user_id}/access-profile` | 查询用户权限画像。 |

### 8.2 Workspace 路由

路由工厂：`create_workspace_router(db_dependency)`

前缀：`/workspaces`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/workspaces` | 创建业务空间。 |
| `GET` | `/workspaces` | 查询业务空间列表。 |
| `POST` | `/workspaces/{workspace_id}/members` | 添加空间成员。 |
| `GET` | `/workspaces/{workspace_id}/members` | 查询空间成员。 |
| `POST` | `/workspaces/temp-auth` | 授予临时权限。 |
| `GET` | `/workspaces/temp-auth/check` | 校验临时权限是否有效。 |

当前这些路由通过工厂函数暴露，尚未在 `main.py` 中统一注册。

## 9. 当前完整业务链路示例

### 9.1 租户内接口访问

```text
前端发起请求，携带 X-User-Id 和 X-Tenant-Id
  -> FastAPI 认证依赖调用 IamAuthContextService
  -> IAM 仓储查询用户、租户、成员、角色、权限
  -> 生成 AuthContext 并放入 request.state
  -> 权限依赖读取 AuthContext 并校验租户、角色或权限
  -> 业务服务处理请求
  -> 租户业务数据应通过 tenant_id 做行级隔离
```

### 9.2 企业用户权限画像

```text
管理员创建部门、用户、角色和菜单/API 资源
  -> 给用户绑定部门
  -> 给角色绑定菜单/API 资源
  -> 给用户绑定角色
  -> 查询用户权限画像
  -> 前端或调用方获得部门、角色和权限码集合
```

### 9.3 自定义数据权限

```text
创建角色时设置 data_scope = 5
  -> 通过 sys_role_dept 绑定可访问部门
  -> 后续业务查询根据角色部门范围生成过滤条件
```

当前只完成数据结构和关系维护，过滤条件生成仍需后续实现。

### 9.4 临时资源授权

```text
授权人创建临时授权
  -> 指定用户、资源类型、资源 ID、权限码和有效期
  -> 访问资源前调用 has_valid_temp_auth
  -> 在有效时间窗口内返回 True
```

后续可将该逻辑接入统一权限拦截：

```text
先校验常规 RBAC 权限
  -> 不通过时检查有效临时授权
  -> 仍不通过则返回权限不足
```

## 10. 与 SQL 脚本的关系

当前企业权限与资源隔离 SQL 文件：

```text
scripts/2026_08_04_enterprise_permission_schema.sql
```

脚本包含：

- 企业组织、用户、部门关系。
- 角色、菜单/API 资源、角色菜单关系。
- 用户角色关系、角色自定义部门关系。
- 业务空间、空间成员、临时授权。

脚本不包含知识库相关表。

## 11. 当前边界与后续可扩展点

当前已具备：

- 通用 `AuthContext`。
- 请求头用户和租户识别。
- 租户内 RBAC 上下文加载。
- FastAPI 权限依赖工厂。
- 租户感知 CRUD 基类。
- 企业部门、用户、角色、菜单/API 权限关系。
- 用户权限画像聚合。
- 业务空间成员和临时授权。
- `app.web.create_app()` 已统一注册 `app/system` 和 `app/workspace` 路由。
- 对应 SQL 初始化脚本。

当前尚未完整打通：

- `app/system` 与 `app/iam` 是两套权限数据模型，当前尚未统一到同一个授权来源。
- `app/system`、`app/workspace` 路由尚未强制接入 `pkg/security` 统一鉴权依赖。
- 企业角色 `data_scope` 尚未转换为实际业务查询过滤条件。
- 临时授权尚未接入 `pkg/security` 统一权限依赖。
- 空间成员角色尚未接入统一权限依赖。
- 审计日志、权限缓存、权限变更失效机制尚未实现。

建议后续演进顺序：

```text
先明确 app/iam 与 app/system 的主授权模型
  -> 将 system/workspace 接口接入 require_permission / require_tenant
  -> 实现 data_scope 查询过滤器
  -> 将临时授权作为权限兜底策略接入
  -> 增加审计与缓存
```
