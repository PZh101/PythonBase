# PythonBase

PythonBase 是一个面向 FastAPI 项目的 Python 基础框架，聚焦接口模型规范、统一响应、配置管理、异步数据库基础设施和可测试的项目结构。项目使用 `uv` 管理依赖，核心代码按 `app/` 业务层和 `pkg/` 通用基础能力分离。

> 当前 `app/` 目录主要包含 IAM 业务基础模型；通用基础能力沉淀在 `pkg/common`、`pkg/config`、`pkg/database`、`pkg/security` 和 `pkg/tenant` 中。

## 技术栈

- Python >= 3.12
- FastAPI：Web 框架与依赖注入
- Pydantic v2：请求、响应和配置模型校验
- SQLAlchemy 2.x Async：异步 ORM、Engine、Session 和事务管理
- PyYAML：环境变量结构值解析与配置设计基础
- pytest：单元测试与 E2E 测试组织
- uv：项目依赖与命令运行

## 快速开始

```bash
# 同步依赖
uv sync

# 运行入口脚本
uv run python main.py

# 运行测试
uv run pytest -v

# 运行当前已实现基础模块测试
uv run pytest tests/pkg/test_api.py tests/pkg/test_exceptions.py tests/pkg/config/test_environment.py tests/pkg/config/test_models.py tests/pkg/database tests/pkg/security tests/pkg/tenant tests/app/iam -v
```

依赖管理统一使用 `uv`：

```bash
uv add <package>        # 添加生产依赖
uv add --dev <package>  # 添加开发依赖
uv sync                 # 同步 pyproject.toml 与 uv.lock
uv run <command>        # 在项目环境中运行命令
```

## 项目结构

```text
PythonBase/
├── app/                  # 应用代码，按业务模块组织
│   └── iam/              # 用户、租户、成员、角色、权限业务模型与服务
├── docs/                 # 项目文档、测试指南、设计与实施计划
├── pkg/                  # 通用框架代码
│   ├── common/           # API 基础模型、统一响应、业务异常
│   ├── config/           # 配置模型、环境变量解析、配置异常
│   ├── database/         # 异步数据库 Engine、Session、CRUD 与租户 CRUD
│   ├── security/         # 认证上下文、权限校验、FastAPI 依赖
│   └── tenant/           # 租户上下文、请求头解析、TenantMixin
├── scripts/              # 运维、数据库、部署等脚本
├── tests/                # 测试文件
│   ├── app/              # 应用测试
│   ├── e2e/              # 端到端测试
│   └── pkg/              # 通用模块单元测试
├── main.py               # 当前入口脚本
├── pyproject.toml        # 项目元数据与依赖声明
├── pytest.ini            # pytest 配置
└── uv.lock               # uv 锁定文件
```

## 核心约束

所有 FastAPI 接口的请求体和响应体必须使用 Pydantic 模型定义，并且必须继承 `pkg.common.api.BaseSchema`。

```python
from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime


class UserResponse(BaseSchema):
    """用户响应模型。"""

    user_id: SafeBigInt
    user_name: str
    created_at: SafeDatetime
```

`BaseSchema` 提供：

- 入站同时支持 `snake_case` 和 `camelCase` 字段名。
- 出站默认序列化为 `camelCase`。
- `SafeBigInt` 在 JSON 序列化时输出字符串，避免 JavaScript 大整数精度丢失。
- `SafeDatetime` 使用统一时间格式 `%Y-%m-%d %H:%M:%S` 解析和序列化。

## 通用 API 能力

`pkg/common/api.py` 提供接口层常用基础模型：

- `BaseSchema`：项目统一 Pydantic 基类。
- `SafeBigInt`：安全大整数类型。
- `SafeDatetime`：统一时间类型。
- `ApiResponse[T]`：统一 `{code, msg, data}` 响应结构。
- `PageParams`：分页请求参数。
- `PageData[T]`：分页响应数据结构。

`pkg/common/exceptions.py` 提供业务异常和 FastAPI 全局异常处理器：

- `AppException`：业务异常基类。
- `BadRequestException`、`UnauthorizedException`、`ForbiddenException`、`NotFoundException`、`ConflictException`、`ValidationException`、`InternalServerException`。
- `register_exception_handlers(app)`：将业务异常和兜底异常统一转换为 `ApiResponse`。

## 配置模块

`pkg/config` 当前提供强类型配置模型、环境变量解析和配置异常：

- `RuntimeSettings`：运行时根配置，允许保留业务自定义顶层配置段。
- `AppSettings`、`ProfileSettings`：应用与 profile 配置。
- `DatabaseSettings`、`PoolSettings`、`DatabaseType`：数据库连接与连接池配置。
- `parse_environment()`：将 `APP_` 前缀环境变量解析为嵌套配置字典。
- `get_environment_profile()`：读取并规范化 `APP_PROFILE`。

环境变量示例：

```text
APP_PROFILE=dev
APP_APP__NAME=pythonbase
APP_DATABASE__TYPE=postgresql
APP_DATABASE__HOST=127.0.0.1
APP_DATABASE__PORT=5432
APP_DATABASE__POOL__SIZE=20
APP_DATABASE__POOL__PRE_PING=false
```

双下划线表示层级，单下划线保留为字段名。环境变量值会优先按 YAML 标量解析，因此可以表达布尔值、数字、列表和字典。

## 数据库模块

`pkg/database` 提供 SQLAlchemy 2.x 异步数据库基础设施：

- `Base`：统一 SQLAlchemy `DeclarativeBase`。
- `DatabaseType` 到异步驱动的映射：MySQL 使用 `asyncmy`，PostgreSQL 使用 `asyncpg`。
- `build_async_database_url()`：基于 `DatabaseSettings` 安全构造 SQLAlchemy URL。
- `AsyncDatabaseManager`：管理异步 Engine、SessionFactory、启动连通性检查和连接池释放。
- `session()`：普通 Session 上下文，不自动提交。
- `transaction()`：事务 Session 上下文，正常提交，异常回滚。
- `create_db_session_dependency()`：FastAPI 写接口事务 Session 依赖。
- `create_readonly_db_session_dependency()`：FastAPI 只读 Session 依赖。
- `BaseCrud`：通用异步 CRUD，写操作只 `flush` / `refresh`，事务提交由调用方控制。
- `TenantAwareCrud`：租户感知 CRUD，默认按 `tenant_id` 隔离查询、更新和删除。

推荐使用方式：

```python
from pkg.config import DatabaseSettings
from pkg.database import BaseCrud, create_manager


database = create_manager(DatabaseSettings(startup_check=False))


async def create_user(user_crud: BaseCrud, data: dict) -> object:
    """在一个事务中创建用户。"""

    async with database.transaction() as session:
        return await user_crud.create(session, data)
```

## 多租户与权限

项目提供可复用的租户 RBAC 基础能力：

- 一个用户可以加入多个租户。
- 用户在不同租户内可以拥有不同角色。
- 当前租户通过 `X-Tenant-Id` 请求头解析。
- 权限通过 `require_permission()`、`require_role()` 等 FastAPI 依赖校验。
- 租户业务数据通过 `TenantAwareCrud` 按 `tenant_id` 隔离。

核心模块：

```text
pkg/security/   # 认证上下文、权限校验、FastAPI 依赖
pkg/tenant/     # 租户上下文、请求头解析、TenantMixin
pkg/database/   # BaseCrud、TenantAwareCrud
app/iam/        # 用户、租户、成员、角色、权限业务模型与服务
```

## 测试

测试配置位于 `pytest.ini`，默认测试目录为 `tests/`。

```bash
uv run pytest -v
uv run pytest tests/pkg/test_api.py -v
uv run pytest tests/pkg/config/test_environment.py tests/pkg/config/test_models.py -v
uv run pytest tests/pkg/database tests/pkg/security tests/pkg/tenant tests/app/iam -v
uv run pytest tests/e2e -v
```

当前工作区中 `tests/pkg/config/test_loader.py` 已包含配置加载器相关测试；在 `pkg.config.loader` 实现前，全量测试会在收集阶段报 `ModuleNotFoundError`。需要验证已实现基础模块时，可以先运行：

```bash
uv run pytest tests/pkg/test_api.py tests/pkg/test_exceptions.py tests/pkg/config/test_environment.py tests/pkg/config/test_models.py tests/pkg/database tests/pkg/security tests/pkg/tenant tests/app/iam -v
```

更多测试约定见 [docs/TEST.md](docs/TEST.md)。

## 开发规范

新增代码请先阅读 [.agent/CODE_RULE.md](.agent/CODE_RULE.md)。特别注意：

- FastAPI 请求/响应模型必须继承 `BaseSchema`。
- 代码注释、docstring 和测试意图说明使用中文。
- `pkg/` 不能依赖 `app/`。
- 公共函数、类和重要方法需要类型注解与 docstring。
- 测试文件放在 `tests/` 下，并尽量镜像被测包结构。

## 相关文档

- [测试指南](docs/TEST.md)
- [用户配置模块设计](docs/superpowers/specs/2026-08-04-user-configuration-design.md)
- [数据库层设计](docs/superpowers/specs/2026-08-04-database-layer-design.md)
- [多租户角色权限框架设计](docs/superpowers/specs/2026-08-04-tenant-rbac-design.md)
