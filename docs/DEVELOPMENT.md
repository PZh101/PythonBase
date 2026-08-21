# 开发说明

## 文档范围

本文面向 PythonBase 的日常开发，说明如何启动项目、配置环境、扩展业务模块、编写接口模型、使用数据库会话、编写测试和维护脚本。

编码规范以项目根目录 `.agent/CODE_RULE.md` 为准。新增代码前请先阅读该文件。

## 本地启动

### 同步依赖

```bash
uv sync
```

### 启动服务

```bash
uv run python main.py
```

服务默认监听：

```text
http://127.0.0.1:8000
```

FastAPI 文档地址：

```text
http://127.0.0.1:8000/docs
```

### 运行测试

```bash
uv run pytest -v
```

按模块运行：

```bash
uv run pytest tests/pkg/database -v
uv run pytest tests/pkg/security tests/pkg/tenant -v
uv run pytest tests/app/system tests/app/workspace -v
uv run pytest tests/app/test_web.py -v
```

如果全量测试在收集阶段出现同名测试文件模块冲突，可以优先运行当前开发模块对应的测试目录。

## 配置约定

配置入口位于 `pkg/config`：

- `RuntimeSettings`：运行时根配置。
- `AppSettings`：应用名称和 profile。
- `ProfileSettings`：profile 配置（`active` 字段）。
- `DatabaseSettings`：数据库类型、连接参数和连接池配置。
- `LoggingSettings`：Loguru 日志级别、格式和输出模式配置。
- `SecuritySettings`：认证安全总配置。
- `PasswordPolicySettings`：密码哈希算法、迭代次数、失败上限、锁定时长。
- `TokenSettings`：JWT 签发配置（`issuer`、`secret`、`algorithm`、`access_token_ttl_seconds`、`refresh_token_ttl_seconds`、`clock_skew_seconds`）。
- `AuthMode` 枚举：决定走 `HEADER`（X- 头）还是 `JWT`（`Authorization: Bearer`）解析路径。
- `load_configuration()`：读取 `application.yml`、profile 配置和环境变量覆盖。
- `parse_environment()`：解析 `APP_` 前缀环境变量。
- `get_environment_profile()`：读取 `APP_PROFILE`。

根目录提供了 [application.example.yml](../application.example.yml) 作为 YAML 配置示例。运行时默认读取项目根目录 `application.yml`，并允许用 `APP_` 环境变量覆盖任意配置项。

配置合并优先级：

```text
application.yml 公共配置
  -> profiles.<active>
  -> application-<active>.yml
  -> APP_ 环境变量
```

环境变量命名规则：

```text
APP_DATABASE__POOL__SIZE=20
```

表示：

```python
{
    "database": {
        "pool": {
            "size": 20
        }
    }
}
```

### 认证安全配置

`SecuritySettings`（`security` 段）汇总认证相关配置：

| 字段 | 说明 |
| --- | --- |
| `enable_password_login` | 是否挂载 `/iam/auth/*` 路由（登录、刷新、登出、改密）。 |
| `auth_mode` | `AuthMode.HEADER` 或 `AuthMode.JWT`。 |
| `password` | `PasswordPolicySettings`：算法（默认 `pbkdf2_sha256`）、迭代次数、失败上限、锁定时长。 |
| `token` | `TokenSettings`：JWT 签名密钥、算法、访问/刷新 token TTL、时钟漂移容忍秒数。 |

`SecuritySettings` 在 `model_validator(mode="after")` 阶段校验：

- `enable_password_login=true` 时 `token.secret` 必填。
- `auth_mode=jwt` 时 `token.secret` 必填。

应用启动后，`app.web.create_app()` 会读取 `security.auth_mode`：

- `HEADER`（默认）：`create_auth_dependency` 走 `X-User-Id` / `X-Tenant-Id` 头解析。
- `JWT`：`create_auth_dependency` 走 `Authorization: Bearer <jwt>` 解析；启动时若未提供 `token_resolver` 会抛 `RuntimeError` 兜底。

启用密码登录或 JWT 模式时，建议通过环境变量配置 `secret`：

```text
APP_SECURITY__ENABLE__PASSWORD__LOGIN=true
APP_SECURITY__AUTH__MODE=jwt
APP_SECURITY__TOKEN__SECRET=please-replace-with-a-long-random-string
APP_SECURITY__TOKEN__ACCESS__TOKEN__TTL__SECONDS=3600
APP_SECURITY__TOKEN__REFRESH__TOKEN__TTL__SECONDS=86400
APP_SECURITY__PASSWORD__ITERATIONS=600000
```

## 应用入口与路由注册

项目通过 `app.web.create_app()` 创建 FastAPI 应用：

```python
from app.web import create_app

app = create_app()
```

`create_app()` 会完成：

1. 加载运行时配置。
2. 创建数据库管理器。
3. 使用 `lifespan` 初始化和释放数据库连接池。
4. 注册全局异常处理器。
5. 注册业务路由。

新增业务模块时，推荐提供一个路由工厂：

```python
def create_example_router(db_dependency: Callable[..., object]) -> APIRouter:
    """创建示例业务路由。"""
    router = APIRouter(prefix="/examples", tags=["示例业务"])
    return router
```

然后在 `app/web.py` 的 `register_routes()` 中统一注册：

```python
app.include_router(create_example_router(db_dependency))
```

## 业务模块目录约定

业务模块放在 `app/` 下，按领域拆分：

```text
app/example/
├── __init__.py
├── models.py       # SQLAlchemy ORM 模型
├── repository.py   # 数据访问
├── schemas.py      # 请求和响应模型
├── service.py      # 业务规则
└── routes.py       # FastAPI 路由
```

职责划分：

- `models.py` 只定义数据库表映射。
- `schemas.py` 只定义 API 入参和出参。
- `repository.py` 只处理数据库查询和持久化。
- `service.py` 放业务校验、编排和异常语义。
- `routes.py` 负责 HTTP 参数、依赖注入和响应包装。

`pkg/` 是通用基础层，不允许依赖 `app/`。

## API 模型规范

所有 FastAPI 请求体和响应体必须继承 `BaseSchema`。

```python
from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime


class ExampleCreateRequest(BaseSchema):
    """创建示例请求。"""

    example_name: str


class ExampleResponse(BaseSchema):
    """示例响应。"""

    id: SafeBigInt
    example_name: str
    created_at: SafeDatetime
```

接口响应推荐使用 `ApiResponse[T]`：

```python
@router.post("", response_model=ApiResponse[ExampleResponse])
async def create_example(body: ExampleCreateRequest) -> ApiResponse[ExampleResponse]:
    """创建示例。"""
    return ApiResponse(data=ExampleResponse(...))
```

注意事项：

- 不要直接使用 `pydantic.BaseModel` 作为接口模型。
- 大整数 ID 使用 `SafeBigInt`。
- 时间字段使用 `SafeDatetime`。
- 代码注释、docstring 和测试意图说明使用中文。

## 数据库开发

### ORM 模型

ORM 模型继承 `pkg.database.Base`：

```python
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database import Base


class Example(Base):
    """示例表。"""

    __tablename__ = "example"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
```

需要租户隔离的业务表应包含 `tenant_id`，并优先复用 `pkg.tenant.TenantMixin`。

### 会话和事务

`AsyncDatabaseManager` 提供两种上下文：

- `session()`：创建会话，不自动提交。
- `transaction()`：创建事务边界，正常结束提交，异常回滚。

FastAPI 写接口默认通过 `create_db_session_dependency(manager)` 注入事务会话。仓储层写操作应只执行 `flush()` 和必要的 `refresh()`，不要自行提交事务。

### 仓储层写法

仓储层接收 `AsyncSession`：

```python
class ExampleRepository:
    """示例数据访问。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
```

查询使用 SQLAlchemy 2.x 风格：

```python
result = await self.db.execute(select(Example).where(Example.id == example_id))
return result.scalars().first()
```

## 异常处理

业务异常使用 `pkg.common.exceptions`：

- `BadRequestException`
- `UnauthorizedException`
- `ForbiddenException`
- `NotFoundException`
- `ConflictException`
- `ValidationException`
- `InternalServerException`

`register_exception_handlers(app)` 会把业务异常转换为统一响应结构：

```json
{
  "code": 40000,
  "msg": "错误信息",
  "data": null
}
```

服务层负责抛出业务异常，路由层不应直接拼接错误响应。

## 日志开发

项目统一使用 Loguru。应用启动时，`app.web.create_app()` 会调用 `configure_logging(runtime_settings.logging)` 完成日志配置。

业务模块中请使用统一入口：

```python
from pkg.common.logging import get_logger

logger = get_logger(__name__)
```

不要在业务代码中直接调用 `logging.basicConfig()` 或重新配置 loguru sink。需要调整日志级别、JSON 输出或诊断开关时，应通过 `LoggingSettings` 或 `APP_LOGGING__*` 环境变量完成。

常用环境变量：

```text
APP_LOGGING__LEVEL=DEBUG
APP_LOGGING__SERIALIZE=false
APP_LOGGING__ENQUEUE=false
APP_LOGGING__BACKTRACE=false
APP_LOGGING__DIAGNOSE=false
```

## 异步任务开发（Celery）

> 想从零加一个业务任务？请直接阅读 [docs/CELERY_EXTENSION.md](CELERY_EXTENSION.md) —— 手把手的任务扩展教程。本节为配置字段与命令参考。

### 启动方式

Celery worker 是独立进程，先启动 Redis，再启动 worker：

```bash
# 启动 Redis（如已安装可跳过）
docker run -d -p 6379:6379 redis:7-alpine

# 启动 worker（不启用定时调度）
uv run python celery_worker.py

# 同时启动 beat 定时调度
APP_CELERY__BEAT_ENABLED=true uv run python celery_worker.py

# 也可以使用标准 CLI（不注入任务数据库管理器）
uv run celery -A pkg.celery.app:celery_app worker --loglevel=INFO
```

注意：Windows 本地开发自动回退 `solo` 池（`prefork` 在 Windows 不可用）；生产 Linux 建议使用默认 `prefork`。

### 配置字段

`CelerySettings`（`celery` 段）字段与对应 Celery conf 键：

| 字段 | 含义 | Celery conf 键 |
| --- | --- | --- |
| `enabled` | 是否启用 worker 与 `/task-demo` 路由 | - |
| `broker_url` | broker 地址（默认 `redis://127.0.0.1:6379/0`） | `broker_url` |
| `result_backend` | 结果后端地址；为空/`null` 表示禁用 | `result_backend` |
| `task_serializer` | 任务序列化方式 | `task_serializer` |
| `timezone` / `enable_utc` | 定时调度时区（默认 `Asia/Shanghai`、关闭 UTC） | `timezone` / `enable_utc` |
| `worker_pool` / `worker_concurrency` | worker 池与并发数；为空交给 Celery 默认 | `worker_pool` / `worker_concurrency` |
| `worker_prefetch_multiplier` | 每个进程预取任务数 | `worker_prefetch_multiplier` |
| `task_acks_late` / `task_reject_on_worker_lost` / `task_track_started` | 任务可靠性开关 | 同名 conf 键 |
| `task_always_eager` / `task_eager_propagates` / `task_store_eager_result` | eager 模式开关（测试用） | 同名 conf 键 |
| `max_retries` / `retry_backoff` / `retry_backoff_max` / `retry_jitter` | 默认重试策略 | `task_default_max_retries` / `task_retry_backoff` / `task_retry_backoff_max` / `task_retry_jitter` |
| `beat` | 定时调度开关与任务表 | `beat_schedule` |
| `include` | 需要注册的任务模块列表 | `include` |

### 如何编写任务

任务通过进程级 Celery 应用注册，默认注册模块为 `pkg.celery.tasks`：

```python
from pkg.celery.app import get_celery_app

_celery = get_celery_app()


@_celery.task(name="demo.echo")
def demo_echo(payload: str) -> str:
    """回显示例任务。"""
    return f"echo:{payload}"
```

新增任务模块时，把模块路径追加到 `celery.include`，例如：

```yaml
celery:
  include:
    - pkg.celery.tasks
    - app.example.tasks
```

### 重试与退避

任务内使用 `self.retry(countdown=...)` 触发重试，`retry_backoff` 自动按指数退避：

```python
@_celery.task(
    name="demo.flaky",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def demo_flaky(self, attempts_until_success: int = 2) -> str:
    """指数退避重试演示：第 N 次尝试成功。"""
    attempt = self.request.retries + 1
    if attempt < attempts_until_success:
        raise self.retry(countdown=2 ** self.request.retries)
    return f"success-after-{attempt}-attempts"
```

### 异步数据库访问

Celery 任务是同步函数，需要通过 `run_async_in_task` 复用任务进程内的 `AsyncDatabaseManager` 执行异步逻辑：

```python
from pkg.celery.runner import run_async_in_task


@_celery.task(name="demo.db.write")
def demo_db_write() -> None:
    """在事务边界内执行异步数据库例程。"""
    async def _write(db: AsyncSession) -> None:
        await db.execute(text("..."))   # 写操作，结束由 transaction() 提交

    run_async_in_task(_write)
```

要点：

- 任务数据库管理器由 `celery_worker.py` 启动时装配一次，任务内复用同一 manager。
- 异步 engine 绑定创建它的事件循环，而 `asyncio.run` 每次新建事件循环，因此每次任务执行后 manager 会释放引擎，下次任务在新循环上重建。
- `transaction=False` 时走只读 `session()` 边界。
- 不要从已运行的异步上下文（如 FastAPI 依赖）中调用 `run_async_in_task`。

### 从 FastAPI 投递与读取结果

```python
async_result = demo_echo.apply_async(args=["hello"])   # 等价于 demo_echo.delay("hello")
task_id = async_result.id

result = app.AsyncResult(task_id)
result.state    # PENDING / STARTED / SUCCESS / FAILURE ...
result.result   # 任务返回值（配置了 result_backend 时可用）
```

未配置 `result_backend` 时无法查询结果，`/task-demo/result/{task_id}` 会返回业务错误（`eager` 模式下结果保存在进程内，同样不通过结果后端查询）。

### 测试约定

Celery 测试在 eager 模式下运行，不需要真实 Redis：

- `tests/pkg/celery/conftest.py` 提供 `celery_settings`（`task_always_eager=True`）、`celery_app`（测试隔离）与 `task_db_manager`（桩数据库管理器）fixture。
- 任务直接调用 `.delay()` 返回 `EagerResult`，`result.state` / `result.get()` 即可断言。
- 重试测试依赖 `task_store_eager_result=True`（eager 下保存重试状态与结果）。

## 权限与租户开发

通用权限能力位于 `pkg/security`：

- `create_auth_context_dependency(provider, *, auth_mode, token_resolver=None)`：按 `AuthMode` 加载认证上下文。
- `require_tenant()`：要求租户上下文。
- `require_permission("permission:code")`：要求指定权限码。
- `require_role("role_code")`：要求指定角色。
- `TokenService` / `JwtTokenResolver`：HS256 JWT 签发与解析（无第三方依赖）。
- `PasswordHasher`：PBKDF2-HMAC-SHA256 密码哈希与校验。
- `extract_bearer_token(authorization_header)`：从 `Authorization` 头提取 Bearer token。

租户上下文能力位于 `pkg/tenant`：

- `TenantContext`
- `TenantMixin`
- `resolve_tenant_id_from_header()`

当前 `app/system` 与 `app/workspace` 实现企业权限数据结构和业务空间能力，并与 `app/iam` 一起通过 `app.web.register_routes()` 统一注册：路由统一挂载基于 `IamAuthContextService` 的认证依赖，并按接口接入 `require_tenant()` / `require_permission()` 强制鉴权。新增业务接口时，应在路由上声明对应权限码依赖。

启用 `security.enable_password_login=true` 时，`register_routes()` 还会挂载 `/iam/auth/*` 路由：登录、刷新无需认证，登出与改密走认证依赖。开发账号密码登录相关接口时直接调用 `app.iam.auth_routes:create_iam_auth_router` 即可，无需关心 HEADER / JWT 的差异——认证模式由 `SecuritySettings.auth_mode` 在启动期决定。

## 数据库脚本维护

数据库脚本放在 `scripts/` 下。当前企业权限和空间相关脚本为：

```text
scripts/2026_08_04_enterprise_permission_schema.sql
```

新增或调整表结构时，请同步更新：

- ORM 模型。
- API 模型。
- 仓储查询。
- 测试用例。
- 对应 SQL 脚本或迁移脚本。

## 测试规范

测试文件放在 `tests/` 下，并尽量镜像源码结构：

```text
tests/app/system/test_service.py
tests/app/workspace/test_service.py
tests/pkg/database/test_manager.py
```

测试方法必须写中文 docstring 说明测试意图：

```python
def test_create_role_rejects_invalid_data_scope() -> None:
    """创建角色应拒绝非法数据范围。"""
```

测试建议：

- Schema 测试覆盖 `snake_case` 和 `camelCase`。
- Service 测试覆盖业务校验和异常。
- Repository 测试覆盖关键查询条件。
- Web 测试覆盖路由注册、异常处理和响应结构。

## 开发检查清单

新增接口前确认：

- 请求和响应模型继承 `BaseSchema`。
- 响应使用 `ApiResponse[T]` 或明确的 `response_model`。
- 路由通过工厂函数创建，并在 `app/web.py` 注册。
- 业务校验放在 Service 层。
- 数据访问放在 Repository 层。
- 写操作不在 Repository 中直接 `commit()`。
- 需要租户隔离的数据按 `tenant_id` 过滤。
- 新增逻辑有对应测试。
- README 或 docs 中相关说明保持同步。
