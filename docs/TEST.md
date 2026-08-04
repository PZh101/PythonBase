# 测试指南

## 运行测试

```bash
# 运行所有测试
pytest -v

# 运行指定测试文件
pytest tests/pkg/test_api.py -v

# 运行指定测试类
pytest tests/pkg/test_api.py::TestUserCreate -v

# 运行指定测试方法
pytest tests/pkg/test_api.py::TestSafeBigInt::test_serialize_int_to_str -v

# 按名称匹配（支持 and / or 表达式）
pytest tests/pkg/test_api.py -k "test_serialize or test_parse" -v

# 运行所有 E2E 测试
pytest tests/e2e/ -v

# 跳过 E2E 测试（仅运行单元测试）
pytest tests/pkg/ -v
```

## 显示 print 输出

```bash
pytest -v -s                    # -s = --capture=no，显示 print
pytest -v --capture=no          # 等价写法
```

## 目录结构

```
tests/
├── conftest.py              # 全局 fixture（暂未使用）
├── pkg/                     # 单元测试：镜像 pkg/ 的包结构
│   ├── test_api.py          # pkg/common/api.py 的单元测试
│   ├── test_exceptions.py   # pkg/common/exceptions.py 的单元测试
│   └── test_db_crud.py      # pkg/common/db_crud.py 的单元测试（待添加）
├── e2e/                     # 端到端测试：测试完整 HTTP 请求→响应链路
│   ├── conftest.py          # E2E 专属 fixture（TestClient、测试数据库）
│   ├── test_api_flow.py     # 正常业务流程的 E2E 测试
│   └── test_error_flow.py   # 异常场景的 E2E 测试
└── __init__.py
```

## 测试框架

- **pytest** 9.1.1
- 配置文件：`pytest.ini`（项目根目录）

## 编写单元测试规范

1. 测试文件放在 `tests/` 下，目录结构镜像 `pkg/` 和 `app/` 的包结构
2. 测试文件命名：`test_<模块名>.py`
3. 测试类命名：`Test<功能>`
4. 测试方法命名：`test_<场景>`
5. 每个测试方法写 docstring 说明测试意图

## 编写 E2E 测试规范

### 定位与原则

E2E 测试验证完整的 HTTP 请求→响应链路，确保各层组件（路由、中间件、异常处理、序列化）正确协作。

|维度|说明|
|-|-|
|测试范围|完整的请求-响应链路，包括状态码、响应头、响应体结构|
|技术栈|`httpx.AsyncClient` + FastAPI `TestClient`|
|数据库|需要真实或内存数据库，不 mock|
|运行方式|`pytest tests/e2e/ -v`|
|速度预期|秒级|

### 目录与命名规则

1. E2E 测试文件统一放在 `tests/e2e/` 目录下
2. 文件命名：`test_<业务场景>.py`（如 `test_api_flow.py`、`test_error_flow.py`）
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

1. 使用 `TestClient` 发起 HTTP 请求（同步或异步），**不直接调用业务函数**
2. 每个测试方法验证一个完整场景，包含 Arrange（准备）→ Act（请求）→ Assert（断言）
3. 对于异常场景，同时验证 HTTP 状态码和响应体中的业务码
4. 涉及数据库的测试需使用事务隔离，测试结束后回滚数据
5. 使用 `given-when-then` 注释风格标注测试步骤