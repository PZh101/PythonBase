# 用户配置模块设计

## 1. 背景

项目需要从 `application.yml` 读取用户配置，将其转换为应用可稳定访问的运行时配置，并支持多个 profile。数据库层是该配置模块的首个消费者，但配置模块必须保持通用，不依赖数据库实现，也允许业务模块增加自定义配置段。

本设计采用 PyYAML 负责 YAML 解析和 Pydantic 负责已知配置的类型校验。配置加载、profile 选择、文件合并、环境变量覆盖和运行时访问集中在统一模块中完成。

## 2. 目标

- 支持 `application.yml` 公共配置。
- 支持主文件内的 `profiles.<name>` 配置段。
- 支持 `application-<profile>.yml` 独立 profile 文件。
- 支持显式参数、环境变量和主配置指定活动 profile。
- 支持 `APP_` 前缀环境变量覆盖任意配置路径。
- 对 `app`、`database` 等基础配置提供强类型访问和启动时校验。
- 对用户自定义配置段提供通用路径访问。
- 生成不可变的运行时配置快照，保证不同协程读取一致。
- 错误信息能够定位配置文件和配置路径，同时保护敏感值。

## 3. 非目标

第一阶段不实现：

- 运行时热加载配置文件。
- 进程内动态切换 profile。
- 远程配置中心。
- YAML 文件写回。
- 密钥托管或加密服务。
- 自动监听文件变化。

profile 或配置发生变化后，需要重启进程。

## 4. 技术决策

采用 `PyYAML + Pydantic`：

- PyYAML 使用 `safe_load()`，不允许 YAML 构造任意 Python 对象。
- 加载器显式实现 profile 解析与深度合并，合并顺序可测试、可解释。
- Pydantic 对已知基础配置执行类型转换、默认值补全和约束校验。
- 顶层允许额外配置段，业务模块不需要修改核心加载器。

不采用 Dynaconf，避免引入一套额外运行时约定；不直接依赖 `pydantic-settings` 的自定义 Source，以保持多文件合并过程透明。

## 5. 模块结构

```text
pkg/config/
├── __init__.py
├── models.py       # 强类型基础配置模型
├── loader.py       # 文件发现、YAML 读取、深度合并和 profile 解析
├── environment.py  # APP_ 环境变量转换
├── manager.py      # ConfigManager、ConfigSnapshot 和访问入口
└── exceptions.py   # 配置加载与校验异常
```

### 5.1 `models.py`

定义以下基础模型：

- `ProfileSettings`：活动 profile。
- `AppSettings`：应用级基础配置。
- `PoolSettings`：数据库连接池参数。
- `DatabaseType`：数据库类型枚举，当前为 `mysql` 和 `postgresql`。
- `DatabaseSettings`：数据库类型、连接参数和池参数。
- `RuntimeSettings`：已知基础配置的根模型，并保留额外顶层配置。

数据库模型只描述数据，不导入 SQLAlchemy 或数据库 Manager。

### 5.2 `loader.py`

负责查找配置文件、读取 YAML、校验 YAML 根节点、提取 profile、执行深度合并并返回普通字典。该层不保存全局状态。

### 5.3 `environment.py`

负责将受控的 `APP_` 环境变量转换成嵌套字典。`APP_PROFILE` 是选择 profile 的保留变量，不作为普通配置项参与映射。

### 5.4 `manager.py`

`ConfigManager` 负责完整加载流程并持有一个 `ConfigSnapshot`。应用可以显式传递 Manager；同时提供初始化后的全局只读访问入口，供基础设施和简单模块读取。

测试可以创建独立 Manager，并指定临时目录、profile 和环境变量集合，不依赖全局实例。

## 6. 配置文件组织

项目根目录默认支持：

```text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
```

`application.yml` 示例：

```yaml
app:
  name: pythonbase
  profile:
    active: dev

database:
  type: mysql
  host: 127.0.0.1
  username: root
  password: ""
  database: pythonbase
  echo: false
  pool:
    size: 10
    max_overflow: 20
    timeout: 30
    recycle: 1800
    pre_ping: true

features:
  order_timeout: 30

profiles:
  dev:
    database:
      echo: true
  postgresql:
    database:
      type: postgresql
      port: 5432
```

`application-prod.yml` 示例：

```yaml
database:
  host: db.internal
  pool:
    size: 30
    max_overflow: 40
```

profile 文件只写差异项，不需要重复公共配置。

## 7. profile 选择

活动 profile 按以下优先级确定，命中后停止：

1. 代码显式传入 `load(profile="test")`。
2. 环境变量 `APP_PROFILE`。
3. `application.yml` 中的 `app.profile.active`。
4. 默认 profile `default`。

`default` 表示只加载公共配置和可选的 `profiles.default`、`application-default.yml`，并不隐含 `dev`。

profile 名必须限制为安全的文件名片段，例如只允许字母、数字、下划线和连字符，禁止路径分隔符及 `..`，避免配置文件路径穿越。

如果显式选择的 profile 在主文件配置段和独立文件中都不存在，加载器应报错。`default` 可以没有专属配置，因为公共配置本身就是有效默认值。

## 8. 合并顺序与规则

最终配置按从低到高的优先级合并：

1. Pydantic 模型默认值。
2. `application.yml` 公共配置。
3. `application.yml` 中的 `profiles.<active>`。
4. `application-<active>.yml`。
5. `APP_` 环境变量覆盖。

公共配置是 `application.yml` 移除顶层 `profiles` 后的内容。`profiles` 只参与加载过程，不出现在最终运行时配置中。

深度合并规则：

- 字典与字典按键递归合并。
- 标量覆盖旧值。
- 列表整体替换，不按索引或元素合并。
- 显式 `null` 覆盖旧值，随后由 Pydantic 判断目标字段是否允许为空。
- 类型冲突时高优先级值覆盖，最终统一进入 Pydantic 校验。
- YAML 空文件视为空字典。
- YAML 根节点不是字典时立即报错。

该规则保证连接池局部覆盖时不会丢失其他公共池参数，同时避免列表合并产生不明确行为。

## 9. 环境变量覆盖

所有普通覆盖变量必须以 `APP_` 开头，使用双下划线表示配置层级：

```text
APP_DATABASE__HOST=127.0.0.1
APP_DATABASE__PORT=5432
APP_DATABASE__POOL__SIZE=20
APP_DATABASE__POOL__PRE_PING=true
APP_FEATURES__ALLOWED_REGIONS=[cn-east, cn-south]
```

转换结果：

```yaml
database:
  host: 127.0.0.1
  port: 5432
  pool:
    size: 20
    pre_ping: true
features:
  allowed_regions:
    - cn-east
    - cn-south
```

环境变量名称去掉前缀后统一转为小写。单下划线属于字段名，只有双下划线表示层级。

环境变量值使用安全的 YAML 标量解析支持布尔值、数字、列表和字典，然后由 Pydantic 对已知字段做最终转换。无法解析为结构值时保留字符串。密码等字符串字段最终必须由配置模型规范为字符串。

`APP_PROFILE` 只用于选择活动 profile，不映射为 `profile` 顶层配置。加载完成后，实际活动 profile 应写入运行时 `app.profile.active`，保证读取结果与实际加载行为一致。

## 10. 运行时模型与访问方式

### 10.1 强类型访问

基础设施和已知配置使用属性访问：

```python
settings = config.settings
database_type = settings.database.type
pool_size = settings.database.pool.size
```

`DatabaseSettings` 必须校验：

- 数据库类型只能是 `mysql` 或 `postgresql`。
- host、username 和 database 等必填字段非空。
- 端口范围为 1 到 65535。
- 端口未配置时，在合并和类型校验完成后按最终数据库类型推导默认值。
- 连接池容量、超时和回收时间符合合理的非负范围。
- `max_overflow` 可以为 0，但不能为负数。

### 10.2 通用路径访问

用户自定义配置使用点分隔路径：

```python
timeout = config.get("features.order_timeout", default=30)
```

约定：

- 路径存在时返回对应只读值。
- 路径不存在且提供默认值时返回默认值。
- 路径不存在且未提供默认值时抛出明确的配置键异常。
- 空字符串不是路径缺失。
- `get()` 不负责隐式类型转换；类型转换在加载阶段完成。

业务模块如需严格校验自定义配置，可以从指定路径取得字典，再使用自己的 Pydantic 模型校验。核心配置模块不感知业务模型。

### 10.3 不可变快照

加载成功后生成 `ConfigSnapshot`。调用方不能原地修改配置；需要不同配置时创建新 Manager 或重启应用。这样后台任务和并发请求始终看到同一版本。

快照至少记录：

- 实际活动 profile。
- 主配置文件路径。
- 已加载的 profile 文件路径（如存在）。
- 强类型 `RuntimeSettings`。
- 用于通用访问的只读合并结果。

## 11. 初始化与访问

应用启动时显式初始化一次：

```text
ConfigManager.load()
  → 选择 profile
  → 读取 YAML
  → 深度合并
  → 应用环境变量
  → Pydantic 校验
  → ConfigSnapshot
```

全局访问器在初始化前被调用时必须抛出明确异常，不能隐式使用空配置。重复初始化默认拒绝，测试或明确的应用重建场景可以创建新的独立 Manager，而不是修改已有快照。

数据库启动顺序必须为：

```text
配置加载成功 → 取得 DatabaseSettings → 数据库 Manager 初始化
```

配置模块不导入数据库模块，因此依赖方向保持单向。

## 12. 错误处理

配置异常至少区分：

- 主配置文件不存在。
- YAML 语法错误。
- YAML 根节点类型错误。
- profile 名非法。
- 显式 profile 不存在。
- 环境变量路径非法。
- Pydantic 字段校验失败。
- 运行时配置键不存在。
- 全局配置尚未初始化。

异常消息应包含文件路径、profile 和配置键路径等定位信息。异常和日志不得输出密码、token、secret、完整数据库 URL 等敏感值。

敏感键识别至少覆盖大小写不敏感的 `password`、`passwd`、`token`、`secret`、`api_key`、`access_key` 和 `private_key`。日志中的嵌套结构应递归脱敏。

## 13. 测试设计

### 13.1 文件与 profile

- 只存在 `application.yml`。
- 使用主文件中的 profile 段。
- 使用独立 profile 文件。
- 同时存在 profile 段和独立文件时的覆盖顺序。
- 显式参数、`APP_PROFILE`、主文件和默认值的选择优先级。
- 非法 profile 名和不存在的显式 profile。
- 空 YAML、非法 YAML 和非字典根节点。

### 13.2 合并

- 嵌套字典递归合并。
- 标量覆盖。
- 列表整体替换。
- `null` 覆盖及后续校验。
- 顶层 `profiles` 不进入最终快照。

### 13.3 环境变量

- 双下划线路径转换。
- 字段名中的单下划线保留。
- 字符串、整数、布尔值、列表和字典解析。
- 环境变量优先于 profile 文件。
- `APP_PROFILE` 不作为普通配置项注入。
- 不带 `APP_` 前缀的变量被忽略。

### 13.4 运行时访问

- 基础配置类型校验与默认值。
- 自定义配置段保留。
- `get()` 的存在、缺失、默认值和空字符串场景。
- 快照不可修改。
- 初始化前访问和重复初始化错误。
- 敏感字段递归脱敏。

所有配置单元测试使用临时目录和显式环境变量字典，不读取开发者机器的真实配置或环境，保证测试隔离。

## 14. 验收标准

- 无 profile 参数时能按约定选择活动 profile。
- 公共配置、主文件 profile、独立 profile 文件和环境变量按固定顺序合并。
- `APP_DATABASE__TYPE=postgresql` 可以在启动时切换活动数据库类型。
- 基础配置可通过 Pydantic 强类型属性读取。
- 用户自定义配置可通过通用路径读取。
- 非法配置在应用启动阶段失败，并给出可定位且不泄密的错误。
- 运行时配置不可变，不支持热切换。
- 数据库层只消费 `DatabaseSettings`，配置模块保持独立。
