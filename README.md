# PythonBase

PythonBase 是一个基于 FastAPI、Pydantic v2、SQLAlchemy Async 和 uv 的 Python 后端基础项目。项目当前已经从纯基础框架扩展为一套带企业组织权限、租户 RBAC、业务空间、临时授权以及基于 JWT 的认证登录示例的 API 骨架。

项目目标是提供一套可复用的后端工程底座：

- 用 `pkg/` 沉淀通用能力，包括统一 API 模型、异常处理、配置解析、异步数据库、租户上下文、权限依赖、JWT 签发解析、PBKDF2 密码哈希。
- 用 `app/` 承载业务模块，目前包含 IAM（含密码登录）、企业组织权限和业务空间示例。
- 用 `app.web.create_app()` 统一创建 FastAPI 应用、管理数据库生命周期、注册异常处理器和业务路由。
- 用 `scripts/` 和 `docs/` 记录数据库结构、权限租户逻辑和开发约定。

## 当前系统能力

### Web 应用入口

`main.py` 暴露 FastAPI 应用实例：

```python
from app.web import create_app

app = create_app()
```

`app/web.py` 负责：

- 从 `application.yml`、profile 配置和 `APP_` 环境变量加载 `RuntimeSettings`。
- 创建并初始化 `AsyncDatabaseManager`。
- 使用 FastAPI `lifespan` 管理数据库连接池启动和释放。
- 注册全局异常处理器。
- 根据 `SecuritySettings.auth_mode` 选择 HEADER 或 JWT 认证路径，并注册 `/system`、`/workspaces`、`/iam` 业务路由。
- 在启用 `enable_password_login` 时额外挂载 `/iam/auth` 登录认证路由。

### 企业组织与权限

模块路径：`app/system`

已提供部门、用户、角色、菜单/API 资源和关系维护能力：

- 部门：`sys_dept`
- 用户：`sys_user`
- 用户部门关系：`sys_user_dept`
- 角色：`sys_role`
- 菜单/API 资源：`sys_menu`
- 角色资源关系：`sys_role_menu`
- 用户角色关系：`sys_user_role`
- 角色自定义数据权限部门：`sys_role_dept`

路由前缀为 `/system`，支持创建和查询部门、用户、角色、菜单资源，以及维护用户部门、用户角色、角色资源、角色部门关系。`GET /system/users/{user_id}/access-profile` 可聚合用户部门、角色和权限码画像。

### 业务空间与临时授权

模块路径：`app/workspace`

已提供业务空间、空间成员和临时授权能力：

- 业务空间：`sys_workspace`
- 空间成员：`sys_workspace_member`
- 临时授权：`sys_temp_auth`

路由前缀为 `/workspaces`，支持创建空间、查询空间、添加空间成员、查询成员、授予临时权限和校验临时权限是否有效。

### 通用租户 RBAC 基础能力

模块路径：`pkg/security`、`pkg/tenant`、`app/iam`

项目保留一套通用租户 RBAC 基础能力：

- `Principal` 表示当前用户。
- `TenantContext` 表示当前租户。
- `AuthContext` 聚合用户、租户、成员、角色和权限。
- `create_auth_context_dependency()` 支持 `AuthMode.HEADER`（从 `X-User-Id`、`X-Tenant-Id` 头加载）和 `AuthMode.JWT`（从 `Authorization: Bearer <token>` 加载）两种互斥模式。
- `require_tenant()`、`require_permission()`、`require_any_permission()`、`require_role()` 提供 FastAPI 权限依赖。
- `TenantAwareCrud` 为带 `tenant_id` 的业务表提供租户隔离 CRUD。
- `TokenService` 与 `JwtTokenResolver` 提供基于 HS256 的 JWT 签发与解析（无第三方依赖）。
- `PasswordHasher` 基于 PBKDF2-HMAC-SHA256 实现密码哈希和校验。

当前 `app/system` 与 `app/workspace` 已注册为业务 API，但尚未把所有接口强制接入通用权限依赖；后续可按业务需要逐步打通。

### 账号密码登录与 JWT 认证

模块路径：`app/iam/auth_routes.py`、`app/iam/auth_service.py`

当 `security.enable_password_login=true` 时，`app.web.create_app()` 会自动挂载以下路由：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/iam/auth/login` | 账号密码登录，签发访问令牌和刷新令牌。 |
| `POST` | `/iam/auth/refresh` | 使用刷新令牌换取新的 token 对。 |
| `POST` | `/iam/auth/logout` | 登出当前用户，使历史 token 全部失效。 |
| `POST` | `/iam/auth/password` | 修改当前用户密码并重新签发 token。 |

- 密码使用 PBKDF2-HMAC-SHA256（OWASP 推荐 600000 次迭代）哈希后存储在 `iam_user_credentials.password_hash`。
- `iam_user_credentials.token_version` 在登出或重置密码时 +1，所有版本号低于新值的访问 token 立即失效。
- `iam_user_credentials.failed_attempts` / `locked_until` 实现连续失败锁定，由 `PasswordPolicySettings.max_failed_attempts` / `lock_duration_seconds` 控制。
- 启用密码登录或 `auth_mode=jwt` 时必须配置 `security.token.secret`。

## 技术栈

- Python >= 3.12
- FastAPI：Web 框架、依赖注入和 OpenAPI 文档
- Pydantic v2：请求、响应和配置模型校验
- SQLAlchemy 2.x Async：异步 ORM、Engine、Session 和事务管理
- asyncpg / asyncmy：PostgreSQL / MySQL 异步驱动
- Loguru：统一应用日志输出
- PyYAML：环境变量值解析
- PyJWT（项目自带 HS256 实现，标准库 hmac + hashlib）：访问令牌与刷新令牌签发
- PBKDF2-HMAC-SHA256（标准库 hashlib）：密码哈希
- pytest：测试框架
- uv：依赖管理和命令运行

## 快速开始

```bash
# 同步依赖
uv sync

# 启动 HTTP 服务
uv run python main.py

# 访问接口文档
# http://127.0.0.1:8000/docs
```

常用测试命令：

```bash
# 运行所有测试
uv run pytest -v

# 运行基础能力测试
uv run pytest tests/pkg/config tests/pkg/database tests/pkg/security tests/pkg/tenant -v

# 运行当前业务模块测试
uv run pytest tests/app/test_web.py tests/app/system tests/app/workspace tests/app/iam -v
```

> 注意：如果全量测试在收集阶段出现同名测试模块冲突或尚未实现模块导入错误，请优先按上面的分组命令验证当前关注模块。

## 配置

项目默认读取根目录 `application.yml`，并通过 `APP_` 前缀环境变量覆盖配置。双下划线表示嵌套层级，单下划线保留为字段名。

根目录提供 [application.example.yml](application.example.yml) 作为 YAML 配置示例，可按需复制或对照调整本地 `application.yml`。

```text
APP_PROFILE=dev
APP_APP__NAME=pythonbase
APP_DATABASE__TYPE=postgresql
APP_DATABASE__HOST=127.0.0.1
APP_DATABASE__PORT=5432
APP_DATABASE__NAME=pythonbase
APP_DATABASE__USERNAME=postgres
APP_DATABASE__PASSWORD=postgres
APP_DATABASE__POOL__SIZE=20
APP_DATABASE__POOL__PRE_PING=false
APP_LOGGING__LEVEL=INFO
APP_LOGGING__SERIALIZE=false
APP_SECURITY__AUTH__MODE=header
APP_SECURITY__ENABLE__PASSWORD__LOGIN=false
APP_SECURITY__TOKEN__SECRET=please-replace-with-a-long-random-string
APP_SECURITY__TOKEN__ACCESS__TOKEN__TTL__SECONDS=3600
APP_SECURITY__TOKEN__REFRESH__TOKEN__TTL__SECONDS=86400
APP_SECURITY__PASSWORD__ITERATIONS=600000
```

配置合并优先级为：`application.yml` 公共配置 < `profiles.<active>` < `application-<active>.yml` < `APP_` 环境变量。环境变量值会优先按 YAML 标量解析，因此可以表达布尔值、数字、列表和字典。

## 日志

项目使用 Loguru 作为统一日志框架。应用创建时会根据 `RuntimeSettings.logging` 调用 `configure_logging()`，并桥接标准库 `logging`，让 uvicorn、SQLAlchemy 和业务日志尽量走同一套输出。

业务代码推荐使用：

```python
from pkg.common.logging import get_logger

logger = get_logger(__name__)
```

日志配置支持：

- `level`：日志级别，默认 `INFO`。
- `format`：控制台输出格式。
- `serialize`：是否输出 JSON 日志。
- `enqueue`：是否启用异步安全队列。
- `backtrace`、`diagnose`：异常诊断开关。

## 数据库脚本

当前企业权限与业务空间表结构脚本：

```text
scripts/2026_08_04_enterprise_permission_schema.sql
```

脚本包含企业组织、用户、角色、菜单/API 资源、业务空间、空间成员和临时授权相关表结构。

## 项目结构

```text
PythonBase/
├── app/                  # 应用业务模块
│   ├── iam/              # 租户 IAM、AuthContext 加载、账号密码登录
│   ├── system/           # 企业组织、用户、角色、菜单/API 权限
│   ├── workspace/        # 业务空间、空间成员、临时授权
│   └── web.py            # FastAPI 应用创建和路由注册
├── docs/                 # 项目文档
├── pkg/                  # 通用框架能力
│   ├── common/           # BaseSchema、ApiResponse、异常处理
│   ├── config/           # 配置模型和环境变量解析
│   ├── database/         # SQLAlchemy Async 基础设施和 CRUD
│   ├── security/         # 认证上下文、JWT、PBKDF2、权限依赖
│   └── tenant/           # 租户上下文、解析器和 TenantMixin
├── scripts/              # 数据库和运维脚本
├── tests/                # 测试文件
├── main.py               # HTTP 服务入口
├── pyproject.toml        # 项目元数据和依赖
├── pytest.ini            # pytest 配置
└── uv.lock               # uv 锁定文件
```

## 核心开发约束

所有 FastAPI 接口的请求体和响应体必须使用 Pydantic 模型定义，并且必须继承 `pkg.common.api.BaseSchema`。

```python
from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime


class UserResponse(BaseSchema):
    """用户响应模型。"""

    id: SafeBigInt
    username: str
    created_at: SafeDatetime
```

`BaseSchema` 提供：

- 入站同时支持 `snake_case` 和 `camelCase` 字段名。
- 出站默认序列化为 `camelCase`。
- `SafeBigInt` 在 JSON 序列化时输出字符串，避免 JavaScript 大整数精度丢失。
- `SafeDatetime` 使用统一时间格式 `%Y-%m-%d %H:%M:%S` 解析和序列化。

## 相关文档

- [开发说明](docs/DEVELOPMENT.md)
- [架构文档](docs/ARCHITECTURE.md)：包含 Mermaid 总体架构图、启动流程图、请求时序图和权限数据关系图。
- [测试指南](docs/TEST.md)
- [权限租户流程](docs/PERMISSION_TENANT_FLOW.md)
- [当前权限、租户与资源隔离业务逻辑](docs/CURRENT_PERMISSION_TENANT_BUSINESS.md)
- [用户配置模块设计](docs/superpowers/specs/2026-08-04-user-configuration-design.md)
- [数据库层设计](docs/superpowers/specs/2026-08-04-database-layer-design.md)
- [多租户角色权限框架设计](docs/superpowers/specs/2026-08-04-tenant-rbac-design.md)
