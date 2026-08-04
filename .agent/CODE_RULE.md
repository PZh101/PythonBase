# PythonBase 代码规范

## 目录结构约定

```
PythonBase/
├── app/          # 应用代码（业务逻辑）
├── pkg/          # 框架/全局/通用代码（基础库、工具类、中间件等）
├── docs/         # 文档
├── scripts/      # 脚本（数据库、Docker、K8s、运维等）
├── tests/        # 测试文件
│   ├── app/      # 应用测试
│   └── pkg/      # 通用模块测试
├── .agent/       # AI 智能体配置与规范
├── main.py       # 项目入口
├── pyproject.toml # 项目配置与依赖管理
├── pytest.ini    # pytest 配置
├── uv.lock       # uv 依赖锁定文件
└── AGENT.md      # AI 智能体引导提示词
```

---

## 1. Python 编码规范

### 1.1 代码风格

- 遵循 [PEP 8](https://peps.python.org/pep-0008/) 编码规范
- 使用 4 空格缩进（不使用 Tab）
- 行宽不超过 120 字符
- 使用 `ruff` 或 `black` 进行代码格式化（推荐）
- 使用 `isort` 或 `ruff` 进行 import 排序（标准库 → 第三方库 → 本地模块）

### 1.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 变量/函数/方法 | snake_case | `user_name`, `get_user()` |
| 类 | PascalCase | `UserService`, `UserCreate` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| 私有属性/方法 | 前导下划线 | `_internal_helper()` |
| 模块名 | snake_case | `user_service.py` |
| 包名 | 简短小写，不使用下划线 | `app`, `pkg` |

### 1.3 类型注解

- 所有函数参数和返回值必须标注类型
- 所有类属性必须标注类型
- 使用 `typing` 模块提供的高级类型（`Optional`, `List`, `Dict` 等，Python 3.9+ 可使用内置泛型）
- 复杂类型使用 `TypeAlias` 或 `Annotated` 定义别名

```python
# ✅ 正确
def get_user(user_id: int) -> UserResponse | None: ...

# ❌ 错误
def get_user(user_id): ...
```

### 1.4 文档注释

- 公共函数、类、方法需要写 docstring
- 使用 Google 风格或 reStructuredText 风格
- 测试方法必须写单行 docstring 说明测试意图
- 模块级别 docstring 说明模块用途

```python
def get_user(user_id: int) -> UserResponse | None:
    """根据用户 ID 获取用户信息。

    Args:
        user_id: 用户 ID

    Returns:
        用户响应对象，不存在时返回 None
    """
    ...
```

### 1.5 异常处理

- 不要捕获通用 Exception，指定具体的异常类型
- 使用自定义异常类继承 `Exception`
- 异常信息使用中文描述（面向运维/API 消费者）

---

## 2. FastAPI 框架规范

### 2.1 请求与响应模型

**所有 FastAPI 的请求体和响应体必须使用 Pydantic 模型定义，且必须继承 `pkg.common.api.BaseSchema`。**

```python
from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime

# ✅ 请求模型
class UserCreateRequest(BaseSchema):
    user_name: str
    email: str

# ✅ 响应模型
class UserResponse(BaseSchema):
    user_id: SafeBigInt
    user_name: str
    created_at: SafeDatetime
```

### 2.2 BaseSchema 提供的全局能力

继承 `BaseSchema` 后自动获得：

| 能力 | 说明 |
|------|------|
| **驼峰转换** | 入站时自动将 snake_case 字段名映射为 camelCase，出站时序列化为 camelCase |
| **双向兼容** | 入站同时支持 `snake_case` 和 `camelCase` 输入 |
| `SafeBigInt` | 大整数在 JSON 序列化时自动转为字符串，避免 JavaScript 精度丢失 |
| `SafeDatetime` | 时间类型统一格式 `"%Y-%m-%d %H:%M:%S"`，入站自动解析字符串，出站自动格式化 |

### 2.3 路由定义

- 路由函数放在 `app/` 目录下，按模块组织
- 路由函数使用依赖注入获取服务层实例
- 使用 `@router` 而非 `@app` 定义路由，统一在 `app/__init__.py` 中注册

```python
from fastapi import APIRouter, Depends
from pkg.common.api import BaseSchema, SafeBigInt

router = APIRouter(prefix="/users", tags=["用户"])

class UserCreateRequest(BaseSchema):
    user_name: str
    email: str

class UserResponse(BaseSchema):
    user_id: SafeBigInt
    user_name: str

@router.post("/", response_model=UserResponse)
def create_user(body: UserCreateRequest):
    ...
```

### 2.4 统一响应格式

- 所有接口返回统一的 JSON 结构
- 使用 `pkg.common.response`（如存在）或 FastAPI 的 `response_model` 确保响应类型安全

### 2.5 错误处理

- 使用 `pkg.common.exceptions`（如存在）或 HTTPException 抛出自定义错误
- 定义全局异常处理器，统一错误响应格式

---

## 3. 测试规范

### 3.1 目录结构

```
tests/
├── pkg/           # 对应 pkg/ 包的测试
│   └── test_api.py
├── app/           # 对应 app/ 包的测试
│   └── test_*.py
└── conftest.py    # 全局 fixture（可选）
```

### 3.2 命名规范

| 要素 | 规范 | 示例 |
|------|------|------|
| 测试文件 | `test_<模块名>.py` | `test_api.py`, `test_user_service.py` |
| 测试类 | `Test<功能>` | `TestUserCreate`, `TestUserResponse` |
| 测试方法 | `test_<场景>` | `test_create_with_int_id`, `test_json_by_alias` |
| 测试方法 docstring | 单行说明测试意图 | `"""UserCreate 应接受 int 类型的 user_id"""` |

### 3.3 编写原则

- 每个测试方法只测试一个行为
- 使用描述性的方法名和 docstring
- 测试数据在方法内部或类级定义，避免全局共享可变状态
- 使用 `pytest` 的 `parametrize` 测试多组输入
- 测试 JSON 序列化时同时验证 `by_alias=True` 和 `by_alias=False` 两种模式

### 3.4 运行测试

```bash
# 运行所有测试
pytest -v

# 运行指定文件
pytest tests/pkg/test_api.py -v

# 运行指定类或方法
pytest tests/pkg/test_api.py::TestUserCreate -v
pytest tests/pkg/test_api.py::TestUserCreate::test_json_by_alias -v

# 按名称匹配
pytest tests/pkg/test_api.py -k "test_serialize or test_parse" -v

# 显示 print 输出
pytest -v -s
```

### 3.5 测试数据库

- 单元测试使用 mock 或内存数据库（如 SQLite `:memory:`）
- 集成测试使用独立的测试数据库
- 测试前后清理数据，确保测试隔离

---

## 4. 项目管理规范

### 4.1 依赖管理

- 使用 `uv` 进行依赖管理，不使用 `pip` 或 `poetry`
- 生产依赖写在 `pyproject.toml` 的 `[project.dependencies]` 中
- 开发依赖写在 `pyproject.toml` 的 `[dependency-groups] dev` 中

```bash
uv add <package>              # 添加生产依赖
uv add --dev <package>        # 添加开发依赖
uv sync                       # 同步依赖
uv run <command>              # 在虚拟环境中运行命令
```

### 4.2 代码组织

- `app/`：业务逻辑代码，按功能模块分包（如 `app/user/`, `app/order/`）
- `pkg/`：通用框架代码，按功能分包（如 `pkg/common/`, `pkg/database/`）
- `pkg/` 中的代码不应依赖 `app/` 中的代码
- 每个包必须有 `__init__.py` 文件

### 4.3 数据库规范

- 使用 SQLAlchemy 2.0 风格的声明式映射
- 模型定义放在 `pkg/database/models.py` 或 `app/*/models.py` 中
- 使用 Alembic 进行数据库迁移（脚本放在 `scripts/` 下）

---

## 5. 特殊类型说明

### 5.1 SafeBigInt

```python
from pkg.common.api import SafeBigInt

class OrderResponse(BaseSchema):
    order_id: SafeBigInt  # JSON 序列化时自动转为字符串
```

- 入站：接受 `int` 或 `str`，自动转为 `int`
- 出站：JSON 序列化时自动转为 `str`（避免 JavaScript Number 精度丢失）
- Python 内部始终为 `int` 类型

### 5.2 SafeDatetime

```python
from pkg.common.api import SafeDatetime

class UserResponse(BaseSchema):
    created_at: SafeDatetime  # 统一格式 "%Y-%m-%d %H:%M:%S"
```

- 入站：接受 `datetime` 对象或 `"2026-01-01 09:30:14"` 格式字符串，自动解析
- 出站：JSON 序列化时自动格式化为 `"2026-01-01 09:30:14"` 字符串
- Python 内部始终为 `datetime` 类型