# 测试指南

## 运行测试

```bash
# 运行所有测试
uv run pytest -v

# 按包/模块运行
uv run pytest tests/pkg/config -v
uv run pytest tests/pkg/database -v
uv run pytest tests/pkg/security -v
uv run pytest tests/pkg/tenant -v
uv run pytest tests/pkg -v
uv run pytest tests/app/test_web.py tests/app/iam tests/app/system tests/app/workspace -v
uv run pytest tests/e2e -v
```

常用过滤参数：

```bash
# 按名称匹配（支持 and / or 表达式）
uv run pytest tests/pkg/security -k "test_bearer or test_token" -v

# 显示 print 输出
uv run pytest tests/pkg -v -s
```

## 目录结构

```text
tests/
├── app/                     # 应用层测试
│   ├── test_web.py          # FastAPI 应用创建、路由注册、异常处理
│   ├── iam/                 # IAM（含账号密码登录）
│   │   ├── test_models.py
│   │   ├── test_schemas.py
│   │   ├── test_service.py
│   │   ├── test_auth_service.py
│   │   └── test_auth_routes.py
│   ├── system/              # 企业组织权限
│   │   ├── test_models.py
│   │   ├── test_schemas.py
│   │   └── test_service.py
│   └── workspace/           # 业务空间与临时授权
│       ├── test_models.py
│       ├── test_schemas.py
│       └── test_service.py
├── pkg/                     # 框架层测试
│   ├── test_api.py          # pkg/common/api.py（Pydantic 基础类型）
│   ├── test_exceptions.py   # pkg/common/exceptions.py（异常类与处理器）
│   ├── test_logging.py      # pkg/common/logging.py（Loguru 配置）
│   ├── config/              # pkg/config 全部模块
│   │   ├── test_environment.py
│   │   ├── test_loader.py
│   │   └── test_models.py
│   ├── database/            # pkg/database 基础设施
│   │   ├── test_crud.py
│   │   ├── test_manager.py
│   │   ├── test_tenant_crud.py
│   │   └── test_url.py
│   ├── security/            # pkg/security 认证与授权
│   │   ├── test_bearer_extractor.py
│   │   ├── test_context.py
│   │   ├── test_dependencies.py
│   │   ├── test_password_hasher.py
│   │   ├── test_permissions.py
│   │   └── test_token_service.py
│   ├── tenant/              # pkg/tenant
│   │   └── test_resolver.py
│   └── celery/              # pkg/celery 异步任务
│       ├── conftest.py      # eager 模式 fixture
│       ├── test_config.py
│       ├── test_factory.py
│       ├── test_runner.py
│       └── test_tasks.py
└── e2e/
    ├── __init__.py
    └── conftest.py          # E2E 专属 fixture（数据库、TestClient）
```

> 根 `pkg/common/db_crud.py` 仅为三行兼容导出文件（重导出 `pkg.database.base.Base` 和 `pkg.database.crud.BaseCrud`），其真实实现位于 `pkg/database/crud.py`，测试在 `tests/pkg/database/test_crud.py`。

## 测试框架

- **pytest**：通过 `pyproject.toml` 与 `pytest.ini` 配置
- **httpx / FastAPI TestClient**：用于 E2E 和 web 层测试
- 框架层测试大量使用 mock，不需要真实数据库；`tests/pkg/database/test_*.py` 与 `tests/app/**` 中的 service / repository 测试通常使用事务回滚或内存数据库

## Celery 任务测试

Celery 测试位于 `tests/pkg/celery`，在 **eager 模式**下运行，**不需要真实 Redis**。

- `conftest.py` 提供三个 fixture：
  - `celery_settings`：`task_always_eager=True`、`task_store_eager_result=True`、`task_eager_propagates=False`、`result_backend=None`。
  - `celery_app`：构建测试 Celery 应用，测试前后重置进程级持有器并重载 `pkg.celery.tasks`。
  - `task_db_manager`：桩数据库管理器，通过 `calls` 列表断言调用序列。
- 任务测试直接调用 `.delay()` 返回 `EagerResult`，用 `.get()` / `.state` / `.result` 断言。
- 重试测试依赖 `task_store_eager_result=True`：eager 下保存重试状态，可断言超过 `max_retries` 后任务 `FAILURE`。
- `run_async_in_task` 测试通过桩管理器验证 `initialize → transaction/session → dispose` 调用顺序。

## 编写单元测试规范

1. 测试文件放在 `tests/` 下，目录结构镜像 `pkg/` 和 `app/` 的包结构
2. 测试文件命名：`test_<模块名>.py`（如 `test_auth_service.py` 对应 `app/iam/auth_service.py`）
3. 测试类命名：`Test<功能>`
4. 测试方法命名：`test_<场景>`
5. 每个测试方法写 docstring 说明测试意图
6. 测试方法使用中文 docstring

```python
def test_create_role_rejects_invalid_data_scope() -> None:
    """创建角色应拒绝非法数据范围。"""
```

## E2E 测试规范

### 定位与原则

E2E 测试验证完整的 HTTP 请求→响应链路，确保各层组件（路由、中间件、异常处理、序列化）正确协作。

| 维度 | 说明 |
| --- | --- |
| 测试范围 | 完整的请求-响应链路，包括状态码、响应头、响应体结构 |
| 技术栈 | FastAPI `TestClient` |
| 数据库 | 真实或内存数据库，不 mock |
| 运行方式 | `uv run pytest tests/e2e -v` |

### 目录与命名规则

1. E2E 测试文件统一放在 `tests/e2e/` 目录下
2. 文件命名：`test_<业务场景>.py`
3. 类命名：`Test<业务场景>`
4. 方法命名：`test_<前置条件_预期行为>`

### 响应结构校验

所有 E2E 测试必须验证响应符合 `ApiResponse` 标准结构：

```json
{
    "code": 0,
    "msg": "success",
    "data": null
}
```

- 正常请求：验证 `code == 0`、`msg == "success"`、`data` 包含预期字段
- 异常请求：验证 `code` 为非零业务码、`msg` 为错误描述、`data` 为 `null` 或附加信息

### 编写规范

1. 使用 `TestClient` 发起 HTTP 请求，**不直接调用业务函数**
2. 每个测试方法验证一个完整场景，包含 Arrange（准备）→ Act（请求）→ Assert（断言）
3. 对于异常场景，同时验证 HTTP 状态码和响应体中的业务码
4. 涉及数据库的测试需使用事务隔离，测试结束后回滚数据
5. 使用 given-when-then 注释风格标注测试步骤
