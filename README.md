# PythonBase

Python 项目基础框架。

## 项目结构

```text
PythonBase/
├── app/          # 应用代码（业务逻辑）
├── docs/         # 文档
├── pkg/          # 框架/全局/通用代码（基础库、工具类、中间件等）
├── scripts/      # 脚本（数据库、Docker、K8s、运维等）
├── tests/        # 测试文件
│   ├── app/      # 应用测试
│   └── pkg/      # 通用模块测试
├── main.py       # 项目入口
├── pyproject.toml # 项目配置与依赖管理
├── pytest.ini    # pytest 配置
└── uv.lock       # uv 依赖锁定文件
```

## 技术栈

- Python >= 3.12
- FastAPI — Web 框架
- Pydantic — 数据校验
- SQLAlchemy — ORM
- pytest — 测试框架

## 多租户与权限

项目提供可复用的租户 RBAC 基础能力：

- 一个用户可以加入多个租户
- 用户在不同租户内可以拥有不同角色
- 当前租户通过 `X-Tenant-Id` 请求头解析
- 权限通过 `require_permission()`、`require_role()` 等 FastAPI 依赖校验
- 租户业务数据通过 `TenantAwareCrud` 按 `tenant_id` 隔离

核心模块：

```text
pkg/security/   # 认证上下文、权限校验、FastAPI 依赖
pkg/tenant/     # 租户上下文、请求头解析、TenantMixin
pkg/database/   # BaseCrud、TenantAwareCrud
app/iam/        # 用户、租户、成员、角色、权限业务模型与服务
```

## 项目管理

本项目使用 [uv](https://docs.astral.sh/uv/) 进行项目管理。

```bash
# 安装依赖
uv sync

# 添加依赖
uv add <package>

# 添加开发依赖
uv add --dev <package>

# 运行测试
uv run pytest

# 运行多租户 RBAC 测试
uv run pytest tests/pkg/security tests/pkg/tenant tests/pkg/database/test_tenant_crud.py tests/app/iam -v
```
