# 多租户角色权限框架设计

## 1. 背景

PythonBase 当前已经具备统一 API 模型、统一异常响应、异步数据库管理器和通用 CRUD 基础能力。下一阶段如果要支持用户、角色、权限和租户隔离，应优先沉淀一套可复用的基础框架，而不是把权限判断散落在业务接口中。

本设计采用“多租户成员身份 + 租户内 RBAC + 行级租户隔离”的模型。一个用户可以加入多个租户，并且在不同租户内拥有不同角色。每个请求先确定当前租户，再基于用户在该租户中的成员身份聚合权限。

## 2. 目标

- 支持一个用户加入多个租户。
- 支持用户在不同租户中拥有不同角色。
- 支持租户内角色、权限和成员关系管理。
- 支持平台管理员跨租户管理。
- 支持 FastAPI 依赖式权限校验。
- 支持业务数据按 `tenant_id` 行级隔离。
- 支持框架层提供通用上下文、校验器和租户感知数据访问工具。
- 保持 `pkg/` 不依赖 `app/`，业务实现可替换。

## 3. 非目标

第一阶段不实现：

- 每租户独立数据库。
- 每租户独立 schema。
- PostgreSQL Row Level Security。
- 完整 ABAC 规则引擎。
- 组织架构、部门、岗位、数据范围等复杂授权。
- OAuth2、OIDC、SSO、第三方身份源。
- 权限实时推送和分布式缓存失效。

这些能力可以在 RBAC 和租户上下文稳定后逐步扩展。

## 4. 推荐模型

采用一个用户多租户成员关系：

```text
User
  ↓
TenantMember
  ↓
Tenant
```

角色挂在成员身份上，而不是直接挂在用户上：

```text
User
Tenant
TenantMember(user_id, tenant_id, status)
Role
Permission
TenantMemberRole(member_id, role_id)
RolePermission(role_id, permission_id)
```

同一个用户可以在不同租户下具备不同身份：

```text
用户 A 在租户 1: owner
用户 A 在租户 2: developer
用户 A 在租户 3: viewer
```

## 5. 模块边界

建议将通用机制和业务实体分开。

```text
pkg/
├── security/
│   ├── context.py        # AuthContext、Principal、PermissionSet
│   ├── permissions.py    # 权限码、权限匹配、权限依赖工厂
│   ├── dependencies.py   # FastAPI 认证与授权依赖
│   └── exceptions.py     # 认证与授权异常
├── tenant/
│   ├── context.py        # TenantContext
│   ├── resolver.py       # 当前租户解析
│   └── mixins.py         # TenantMixin、租户字段约定
└── database/
    └── tenant_crud.py    # 可选：租户感知 CRUD 基类

app/
└── iam/
    ├── models.py         # 用户、租户、成员、角色、权限 ORM 模型
    ├── schemas.py        # 请求与响应模型，继承 BaseSchema
    ├── repository.py     # IAM 数据访问
    ├── service.py        # 成员、角色、权限业务逻辑
    └── routes.py         # 管理接口
```

`pkg/security` 和 `pkg/tenant` 只定义协议、上下文、依赖工厂和通用校验逻辑。具体用户表、角色表、Token 解析和权限查询由 `app/iam` 或应用注入的 Provider 实现。

## 6. 上下文设计

### 6.1 `Principal`

表示已认证主体：

- `user_id`
- `username` 或展示名
- `is_platform_admin`
- `authenticated`

### 6.2 `TenantContext`

表示当前租户：

- `tenant_id`
- `tenant_code`
- `tenant_name`
- `tenant_status`
- `is_required`

### 6.3 `AuthContext`

表示一次请求的完整身份与授权快照：

- `principal`
- `tenant`
- `member_id`
- `roles`
- `permissions`
- `is_platform_admin`

`AuthContext` 应是只读数据结构，避免请求处理中被业务代码原地修改。

## 7. 当前租户解析

第一阶段推荐从请求头读取当前租户：

```text
X-Tenant-Id: 123456789
```

选择理由：

- 前端切换工作空间时可以显式传入。
- 后端路由不需要把所有接口都设计成 `/tenants/{tenant_id}/...`。
- 测试时容易构造请求。
- 适合普通 SaaS 控制台和管理后台。

约定：

- 需要租户上下文的接口必须提供 `X-Tenant-Id`。
- 平台级接口可以显式标记为不需要租户。
- 如果用户不是该租户成员，返回 403。
- 如果租户不存在或已禁用，返回明确业务错误。
- 平台管理员可以访问跨租户管理接口，但是否允许进入租户业务上下文仍需明确规则。

后续可以扩展支持从域名、路径参数或 Token 默认租户解析，但第一阶段只保留一个主解析来源，降低歧义。

## 8. 权限模型

权限使用稳定字符串编码：

```text
user:read
user:create
user:update
user:delete
role:read
role:assign
tenant:settings:update
```

权限判断以租户为边界：

```text
用户 + 当前租户 → 成员身份 → 角色集合 → 权限集合
```

FastAPI 依赖示例语义：

```python
require_login()
require_tenant()
require_permission("user:create")
require_any_permission("user:update", "user:delete")
require_role("owner")
```

第一阶段权限匹配建议只支持精确匹配。通配符如 `user:*` 可以保留为后续扩展，避免一开始就引入过度授权风险。

## 9. 平台管理员

平台管理员是跨租户管理能力，不应简单等同于所有租户内的 owner。

建议规则：

- 平台管理员可以访问平台级接口，例如租户列表、租户启停、系统角色模板管理。
- 平台管理员进入某个租户业务接口时，应生成明确的审计上下文。
- 是否绕过租户内权限检查由接口显式声明，默认不绕过。
- 所有平台管理员跨租户操作必须记录操作人和目标租户。

这样可以避免“平台管理员无意中拥有所有租户业务数据最高权限”的隐性风险。

## 10. 数据隔离

第一阶段采用共享数据库、共享表、业务表带 `tenant_id` 的行级隔离。

业务 ORM 模型如需租户隔离，应实现统一约定：

```text
tenant_id: bigint
```

查询、更新和删除必须默认带当前 `tenant_id` 条件。建议提供租户感知 CRUD 或查询辅助工具：

```text
TenantAwareCrud.get(db, tenant_id, id)
TenantAwareCrud.list_page(db, tenant_id, ...)
TenantAwareCrud.update(db, tenant_id, id, ...)
TenantAwareCrud.delete_by_id(db, tenant_id, id)
```

约定：

- 租户业务表必须包含 `tenant_id`。
- 平台级表不包含 `tenant_id`，例如用户表、租户表、系统权限表。
- 租户内唯一约束应包含 `tenant_id`，例如 `(tenant_id, code)`。
- 业务代码不得通过普通 CRUD 绕过租户过滤访问租户表数据。

## 11. 请求流程

典型请求流程：

```text
HTTP 请求
  → 认证依赖解析用户
  → 租户解析器读取 X-Tenant-Id
  → IAM Provider 查询成员身份
  → 聚合角色和权限
  → 生成 AuthContext
  → 权限依赖检查 required_permission
  → 路由处理业务
  → 租户感知 CRUD 自动附加 tenant_id
```

认证失败返回 401，租户缺失、成员不存在或权限不足返回 403，租户不存在或状态不可用可按业务错误码返回 404 或 403。

## 12. 错误处理

建议错误类型：

- `AuthenticationRequiredException`：未登录。
- `InvalidCredentialException`：认证凭据无效。
- `TenantRequiredException`：接口需要租户但请求未提供。
- `TenantAccessDeniedException`：用户不是租户成员。
- `PermissionDeniedException`：权限不足。
- `RoleAssignmentException`：角色分配非法。

所有异常最终转换为 `ApiResponse`，响应中不输出 Token、密码、内部权限查询细节。

## 13. 缓存策略

第一阶段可以不做分布式缓存，只在单次请求内缓存 `AuthContext`。

后续如需性能优化，可以缓存：

- 用户在租户内的角色集合。
- 角色到权限的映射。
- 租户状态。

缓存 key 必须包含 `tenant_id` 和 `user_id`。角色或权限变更后，需要明确失效策略。

## 14. 审计

涉及权限和租户的关键操作应保留审计事件：

- 创建租户。
- 修改租户状态。
- 邀请或移除成员。
- 分配或移除角色。
- 修改角色权限。
- 平台管理员跨租户操作。

审计字段至少包含：

- 操作人 `actor_user_id`
- 目标租户 `tenant_id`
- 操作类型 `action`
- 目标资源 `resource_type` 和 `resource_id`
- 操作时间
- 请求来源信息

## 15. 测试设计

### 15.1 单元测试

- 用户在不同租户拥有不同角色。
- 同一权限码在不同租户下独立生效。
- 未提供 `X-Tenant-Id` 时需要租户的接口被拒绝。
- 非成员访问租户被拒绝。
- 权限不足被拒绝。
- 平台管理员访问平台级接口成功。
- 平台管理员进入租户业务接口时遵守显式规则。
- 租户感知 CRUD 自动附加 `tenant_id` 条件。
- 写入租户业务数据时自动带入当前租户。

### 15.2 E2E 测试

- 用户登录后选择租户并访问租户内资源。
- 同一用户切换租户后权限不同。
- 一个租户的数据不会在另一个租户接口中出现。
- 租户管理员可以分配角色，普通成员不能分配角色。
- 权限变更后新请求立即按新权限判断。

## 16. 分阶段实施

### 阶段一：框架骨架

- 定义 `Principal`、`TenantContext`、`AuthContext`。
- 定义租户解析器，从 `X-Tenant-Id` 获取当前租户。
- 定义权限依赖工厂和异常。
- 定义 `TenantMixin` 或租户字段约定。

### 阶段二：IAM 业务模型

- 实现用户、租户、成员、角色、权限关系表。
- 实现成员角色分配和角色权限分配。
- 实现基础管理接口。

### 阶段三：数据隔离

- 实现租户感知 CRUD。
- 业务模型接入 `tenant_id`。
- 测试跨租户数据不可见。

### 阶段四：审计与优化

- 增加审计事件。
- 增加请求内缓存。
- 评估是否需要角色权限缓存。

## 17. 验收标准

- 同一用户可以属于多个租户。
- 用户在不同租户内可以拥有不同角色和权限。
- 需要租户的接口必须通过 `X-Tenant-Id` 确定当前租户。
- 非租户成员不能访问该租户数据。
- 权限不足时返回统一错误响应。
- 租户业务数据默认按 `tenant_id` 隔离。
- 平台管理员能力与租户内 owner 能力边界清晰。
- 通用能力位于 `pkg/`，具体 IAM 业务位于 `app/`，依赖方向保持单向。
