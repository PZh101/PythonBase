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
```
