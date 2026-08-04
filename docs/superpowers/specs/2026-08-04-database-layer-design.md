# 数据库层设计

## 1. 背景

项目现有 `pkg/common/db_crud.py` 基于 SQLAlchemy 2.x 和 `AsyncSession` 实现通用 CRUD，数据库操作与 Session 的创建逻辑尚未形成完整的基础设施。本设计在保留异步 CRUD 使用方式的基础上，增加可切换数据库、连接池、事务管理和多运行入口支持。

数据库连接参数由用户配置模块提供，详见《用户配置模块设计》。数据库层不读取 YAML 或环境变量，只消费已经完成合并与校验的 `DatabaseSettings`。

## 2. 目标

- 一次进程启动只使用一个活动数据源。
- 数据库类型由配置选择，默认 MySQL，可切换到 PostgreSQL。
- 使用 SQLAlchemy 异步 Engine 及其连接池，不重复包装驱动连接池。
- 将连接管理、Session 生命周期、事务边界与 CRUD 操作分离。
- 同时适用于 FastAPI 请求、后台任务、消息消费者、定时任务和命令行入口。
- 当前只实现异步能力，同时为未来同步实现保留清晰边界。
- 尽量保持现有 `BaseCrud` 的调用形式和旧导入路径兼容。

## 3. 非目标

第一阶段不实现以下能力：

- 同一进程连接多个命名数据源。
- 读写分离、分库分表或跨库事务。
- 运行时切换数据库类型。
- 同步 Engine、同步 Session 和同步 CRUD。
- 数据库迁移工具和 Alembic 配置。
- 驱动级连接池与 SQLAlchemy 连接池叠加。

## 4. 技术决策

采用 SQLAlchemy 2.x 异步接口：

| 数据库类型 | SQLAlchemy URL 前缀 | 异步驱动 |
| --- | --- | --- |
| `mysql` | `mysql+asyncmy` | `asyncmy` |
| `postgresql` | `postgresql+asyncpg` | `asyncpg` |

数据库类型使用枚举约束。URL 使用 `sqlalchemy.engine.URL.create()` 构造，不通过字符串拼接用户名和密码，避免特殊字符转义错误。

`create_async_engine()` 创建的 Engine 负责连接池。标准池使用 SQLAlchemy 的 `AsyncAdaptedQueuePool`，不直接创建 `asyncmy` 或 `asyncpg` 自带的池。

## 5. 模块结构

```text
pkg/database/
├── __init__.py
├── base.py          # SQLAlchemy DeclarativeBase
├── dialects.py      # 数据库类型与异步驱动映射
├── url.py           # 连接参数与 URL 构造
├── manager.py       # Engine、连接池、SessionFactory 和上下文管理器
├── dependencies.py  # FastAPI Session 依赖适配器
└── crud.py          # 通用异步 BaseCrud
```

职责边界：

```text
DatabaseSettings
       ↓
AsyncDatabaseManager
       ↓
AsyncEngine + SQLAlchemy Pool
       ↓
async_sessionmaker
       ↓
AsyncSession
       ↓
BaseCrud / 业务 Repository
```

### 5.1 `base.py`

定义 SQLAlchemy 2.x 风格的 `DeclarativeBase`。通用模型和业务模型统一继承该 Base，避免在 CRUD 模块中创建独立 metadata。

### 5.2 `dialects.py`

定义数据库类型到异步 SQLAlchemy 驱动的映射。`DatabaseType` 由配置模块拥有，数据库层单向消费，避免配置模块反向依赖数据库实现。未来同步管理器可以基于同一个 `DatabaseType` 增加独立的同步驱动映射。

### 5.3 `url.py`

负责：

- 数据库类型到异步驱动的映射。
- MySQL 与 PostgreSQL 默认端口的选择。
- 基于 `DatabaseSettings` 构造 SQLAlchemy `URL`。
- 输出日志时生成脱敏后的连接描述。

### 5.4 `manager.py`

`AsyncDatabaseManager` 是数据库连接基础设施的核心，负责：

- 创建并持有一个 `AsyncEngine`。
- 创建并持有一个 `async_sessionmaker[AsyncSession]`。
- 提供普通 Session 和事务 Session 的异步上下文管理器。
- 提供启动连通性检查。
- 在应用关闭时释放连接池。

Manager 可以被应用生命周期长期持有，但它创建的 Session 只能在单个工作单元内使用。

### 5.5 `dependencies.py`

FastAPI 依赖只是 `AsyncDatabaseManager` 的适配层，不是 Session 的唯一创建入口。依赖函数从 Manager 创建事务 Session，并在请求结束时完成提交、回滚和关闭。

### 5.6 `crud.py`

承接现有 `BaseCrud`。CRUD 只接收调用方提供的 `AsyncSession`，不创建 Engine、连接或 Session，也不决定整个业务工作单元何时提交。

## 6. 配置契约

数据库层消费以下强类型配置，不关心配置来自哪个文件或环境变量：

```yaml
database:
  type: mysql
  host: 127.0.0.1
  username: root
  password: ""
  database: pythonbase
  echo: false
  connect_timeout: 10
  startup_check: true
  pool:
    size: 10
    max_overflow: 20
    timeout: 30
    recycle: 1800
    pre_ping: true
```

建议默认值：

| 配置项 | 默认值 | 说明 |
| --- | ---: | --- |
| `type` | `mysql` | 活动数据库类型 |
| `port` | `null` | 未配置时，MySQL 推导为 3306，PostgreSQL 推导为 5432 |
| `echo` | `false` | 是否输出 SQLAlchemy SQL 日志 |
| `connect_timeout` | `10` | 建立连接超时秒数 |
| `startup_check` | `true` | 启动时是否执行连通性检查 |
| `pool.size` | `10` | 常驻连接池容量 |
| `pool.max_overflow` | `20` | 池满时允许临时增加的连接数 |
| `pool.timeout` | `30` | 从池获取连接的等待秒数 |
| `pool.recycle` | `1800` | 连接回收秒数 |
| `pool.pre_ping` | `true` | 使用连接前检测有效性 |

`port` 未配置时，在所有 profile 和环境变量完成合并、数据库类型最终确定后再推导；显式配置时使用用户值。密码可以为空，但日志和异常不得输出密码或包含凭据的完整 URL。

## 7. 生命周期

### 7.1 初始化

应用先加载配置，再初始化数据库：

```text
ConfigManager.load()
  → DatabaseSettings
  → AsyncDatabaseManager.initialize()
  → AsyncEngine
  → async_sessionmaker
  → 可选 SELECT 1 检查
```

`initialize()` 应防止无意中重复创建 Engine。初始化失败时释放已经创建的资源，然后抛出数据库初始化异常。

### 7.2 关闭

应用关闭时调用 `dispose()`。该方法释放 Engine 的连接池，并且应当可以重复调用，以便处理部分启动失败和测试清理场景。

### 7.3 连接占用

创建 `AsyncSession` 不等于立即占用物理连接。Session 在首次执行数据库操作时从池中取得连接；上下文退出并结束事务后，连接归还池中。长时间后台任务只应在实际数据库操作阶段进入 Session 上下文，不能在网络等待或长时间计算期间持有事务。

## 8. Session 与事务接口

Manager 提供两个异步上下文管理器，语义必须明确区分。

### 8.1 普通 Session

```python
async with database.session() as session:
    user = await user_crud.get(session, user_id)
```

约定：

- 创建并最终关闭 Session。
- 不自动开启显式事务，不自动提交。
- 适合只读查询，或由调用方自行控制事务的高级场景。
- 上下文异常退出时，清理尚未结束的事务状态。

### 8.2 事务 Session

```python
async with database.transaction() as session:
    user = await user_crud.create(session, user_data)
    await audit_crud.create(session, {"user_id": user.id})
```

约定：

- 创建 Session 并开启事务。
- 正常退出时提交。
- 异常退出时回滚，并原样继续抛出原异常。
- 无论成功或失败都关闭 Session并将连接归还连接池。
- 同一上下文中的多个 CRUD 操作属于同一原子事务。

不允许跨并发协程共享同一个 `AsyncSession`。

## 9. FastAPI 与后台任务

### 9.1 FastAPI 请求

FastAPI 依赖通过 Manager 创建 Session：

```python
async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with database.transaction() as session:
        yield session
```

该依赖是便捷适配器。只读接口可以使用普通 Session 适配器，写接口默认使用事务 Session。

### 9.2 后台任务

后台任务不能捕获或复用请求依赖创建的 Session，因为请求结束后该 Session 会被关闭。后台任务只接收稳定的 Manager 或可重新获取 Manager 的应用上下文，并创建自己的工作单元：

```python
async def process_order(order_id: int) -> None:
    result = await call_external_service(order_id)

    async with database.transaction() as session:
        await order_crud.update(session, order_id, {"result": result})
```

消息消费者、定时任务和命令行脚本遵循同一规则。

## 10. CRUD 事务语义与兼容

现有 `BaseCrud.create()`、`update()` 和 `delete_by_id()` 会直接 `commit()`，这会使同一个业务流程中的多个写操作无法整体回滚。迁移后的 CRUD 应遵循以下规则：

- 查询方法只执行查询。
- 写方法调用 `flush()`，需要数据库生成值时再调用 `refresh()`。
- CRUD 不调用 `commit()` 或 `rollback()`。
- 提交和回滚由 `transaction()` 或显式事务调用方负责。

这一调整保持方法签名基本不变，但改变了写操作的提交时点。所有调用方必须位于事务上下文内，测试也必须验证上下文退出前后数据可见性。

迁移期可以让 `pkg/common/db_crud.py` 从 `pkg.database.crud` 重新导出 `BaseCrud`，保持旧导入路径可用。新代码统一使用 `pkg.database.crud`。

## 11. 错误与安全

需要定义数据库初始化类异常，覆盖以下场景：

- 不支持的数据库类型。
- 对应异步驱动未安装。
- 必填连接参数缺失。
- URL 或 Engine 创建失败。
- 启动连通性检查失败。

事务内的数据库异常不应被转换或吞掉；Manager 完成回滚和关闭后继续抛出，交由业务层或全局异常处理器决定响应。

日志只允许输出数据库类型、脱敏主机、端口和数据库名。密码、带密码 URL 及其他凭据不得进入日志。

## 12. 同步扩展边界

当前版本不定义尚未实现的同步方法，也不提供会在运行时失败的同步模式开关。未来同步支持通过独立 `SyncDatabaseManager`、`Engine`、`sessionmaker` 和必要时的 `SyncBaseCrud` 实现。

以下部分可直接复用：

- `DatabaseSettings` 和连接池配置。
- 配置模块定义的 `DatabaseType`。
- ORM `DeclarativeBase` 和模型。
- URL 参数与脱敏规则。

同步和异步 Engine 必须拥有各自的连接池，不能共享 Session 或物理连接。

## 13. 测试设计

### 13.1 单元测试

- MySQL/PostgreSQL 类型与异步驱动映射。
- 默认端口与显式端口覆盖。
- URL 构造及特殊字符密码处理。
- 日志连接信息脱敏。
- Engine 与 SessionFactory 只初始化一次。
- `session()` 创建、异常清理和关闭。
- `transaction()` 成功提交、异常回滚和最终关闭。
- `dispose()` 重复调用。
- 后台任务创建独立 Session。
- CRUD 查询、分页、写入和事务行为。
- 旧 `pkg.common.db_crud.BaseCrud` 导入路径兼容。

普通单元测试不依赖外部 MySQL 或 PostgreSQL。事务与 CRUD 测试可以使用独立的异步测试数据库或 mock，具体在实施计划中确定。

### 13.2 集成测试

MySQL 和 PostgreSQL 各提供一组可选集成测试，使用独立测试数据库，验证：

- 建立连接与 `SELECT 1`。
- 池参数被 Engine 接收。
- ORM 创建、查询、更新、删除和分页。
- 提交、回滚及连接归还。

集成测试通过环境变量显式启用，不属于默认无外部依赖的单元测试集合。

## 14. 验收标准

- 未指定数据库类型时使用 MySQL。
- 修改 profile 配置后，重启可切换到 PostgreSQL，业务 CRUD 接口无需修改。
- FastAPI 请求和非 FastAPI 后台任务都能创建独立 Session。
- 多个 CRUD 写操作可以在一个事务中整体提交或整体回滚。
- Session 关闭后连接归还 SQLAlchemy 连接池。
- 运行日志不泄露数据库凭据。
- 当前异步实现不被未来同步实现的接口设计阻塞。
