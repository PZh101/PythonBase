# PythonBase CRUD 开发规范

## 1. 文档说明

### 1.1 目的

本文定义 PythonBase 项目中面向普通业务表的统一 CRUD 开发规范，覆盖：

- 数据库表、字段、索引和注释规范。
- 基于 Pydantic 的请求、响应及安全类型规范。
- 固定的新增、查询、更新、删除、分页查询接口。
- 模糊检索、结构化过滤和多字段排序规范。
- SQLAlchemy 异步数据库连接、Repository、Service 和事务规范。
- JWT 身份传递、租户隔离、权限校验和当前用户获取。
- 全局异常、Trace ID、应用日志和操作审计。
- HTTP 接口向 MCP Tool 映射的约定。

本文中的“必须”表示强制要求，“应”表示无特殊原因必须遵循，“可以”表示可选能力。

### 1.2 适用范围

本规范适用于包含租户和审计字段的普通业务主表。树结构、流水表、时序数据、超大明细、批处理、导入导出等场景可以扩展，但不得破坏租户隔离、权限、事务、异常和审计要求。

基础 CRUD 固定使用命令式 POST 接口，以便 HTTP JSON 请求与 MCP Tool 结构化参数直接映射：

```text
POST /{resource}/create
POST /{resource}/get
POST /{resource}/update
POST /{resource}/delete
POST /{resource}/page
```

### 1.3 核心原则

1. 数据库、ORM 和 Python 字段统一使用全小写 `snake_case`。
2. JSON 接口字段统一使用 `camelCase`，转换由 Pydantic 完成。
3. 所有接口请求体和响应体必须使用 Pydantic 模型，并继承 `BaseSchema`。
4. 所有 `BIGINT` 响应字段必须使用 `SafeBigInt`；请求中的雪花 ID 必须使用严格的 `SafeId`，JSON 只接受十进制字符串。
5. 所有业务时间接口字段必须使用 `SafeDatetime`。
6. `tenant_id` 和当前用户信息从已验证的 JWT 上下文获取，不信任请求体传值。
7. 查询、更新和删除必须包含租户条件。
8. 客户端传入的字段名不能直接拼接为 SQL、排序表达式或 ORM 属性。
9. 写操作由接口事务统一提交或回滚，Repository 不得自行 `commit()`。
10. 新增、更新、删除和敏感查询必须记录审计日志。

---

## 2. 数据库表规范

### 2.1 命名和注释

- 表名、字段名、索引名、约束名必须全小写并使用 `snake_case`。
- 表名应表达业务实体，避免 `data`、`info`、`table1` 等无业务含义的名称。
- 关系表建议使用两个实体名称，例如 `sys_user_role`。
- 每张表必须有中文表注释，每个字段必须有中文字段注释。
- 索引建议使用 `pk_`、`uk_`、`idx_` 前缀。
- 不得使用数据库关键字作为表名或字段名。
- 不得仅依赖 ORM 定义表结构；ORM、迁移脚本和数据库结构必须同步维护。

正例：

```sql
CREATE TABLE biz_customer_order (...)
COMMENT = '客户订单表';
```

反例：

```sql
CREATE TABLE CustomerOrder (...); -- 包含大写和驼峰
CREATE TABLE data (...);          -- 名称无业务含义
CREATE TABLE order (...);         -- 使用数据库关键字且没有注释
```

### 2.2 固定基础字段

普通租户业务表必须包含以下字段：

| 字段 | MySQL 建议类型 | PostgreSQL 建议类型 | 是否为空 | 默认值 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `id` | `BIGINT` | `BIGINT` | 否 | 无 | 雪花算法生成的主键 ID |
| `tenant_id` | `BIGINT` | `BIGINT` | 否 | 无 | 租户 ID |
| `version` | `INT` | `INTEGER` | 否 | `1` | 乐观锁版本号 |
| `status` | `SMALLINT` | `SMALLINT` | 否 | `1` | 数据状态，具体枚举由业务表说明 |
| `created_by` | `BIGINT` | `BIGINT` | 否 | 无 | 创建人用户 ID，系统任务使用 `0` |
| `created_at` | `DATETIME(6)` | `TIMESTAMP(6)` | 否 | 无 | 创建时间 |
| `updated_by` | `BIGINT` | `BIGINT` | 否 | 无 | 最后更新人用户 ID，系统任务使用 `0` |
| `updated_at` | `DATETIME(6)` | `TIMESTAMP(6)` | 否 | 无 | 最后更新时间 |

约束如下：

- `id` 由应用侧雪花算法生成，数据库不得使用自增、序列或触发器覆盖。
- `tenant_id` 不得由普通业务请求体提交，必须取自当前认证上下文。
- `version` 创建时为 `1`，每次成功更新后加 `1`。
- `status` 不能承担逻辑删除含义。建议 `0` 表示停用、`1` 表示启用，其他状态由业务枚举定义。
- `created_by`、`created_at` 创建后不得修改。
- `updated_by`、`updated_at` 由服务端在每次成功更新时重写。
- 本项目基础删除为物理删除，不设置 `deleted`、`deleted_at` 等逻辑删除字段。

### 2.3 建表示例

以下为 MySQL 8 示例；PostgreSQL 应将时间类型和注释语法替换为对应方言：

```sql
CREATE TABLE biz_customer (
    id BIGINT NOT NULL COMMENT '雪花算法生成的客户 ID',
    tenant_id BIGINT NOT NULL COMMENT '租户 ID',
    customer_name VARCHAR(100) NOT NULL COMMENT '客户名称',
    customer_code VARCHAR(64) NOT NULL COMMENT '租户内客户编码',
    description VARCHAR(1000) NULL COMMENT '客户说明',
    version INT NOT NULL DEFAULT 1 COMMENT '乐观锁版本号',
    status SMALLINT NOT NULL DEFAULT 1 COMMENT '状态：0-停用，1-启用',
    created_by BIGINT NOT NULL COMMENT '创建人用户 ID，系统任务为 0',
    created_at DATETIME(6) NOT NULL COMMENT '创建时间',
    updated_by BIGINT NOT NULL COMMENT '最后更新人用户 ID，系统任务为 0',
    updated_at DATETIME(6) NOT NULL COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_biz_customer_tenant_code (tenant_id, customer_code),
    KEY idx_biz_customer_tenant_status_created (tenant_id, status, created_at, id)
) COMMENT = '客户主表';
```

反例：

```sql
CREATE TABLE BizCustomer (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY, -- 大写、自增，不符合雪花 ID 规范
    tenantId BIGINT,                     -- 驼峰且允许为空
    content LONGTEXT,                    -- 未评估就使用 LONGTEXT
    version INT,                         -- 缺少默认值和注释
    createdAt DATETIME                   -- 驼峰、精度和审计字段不完整
);                                      -- 缺少表注释和租户索引
```

### 2.4 雪花 ID

- 雪花 ID 生成器必须作为进程级依赖注入，不得在每次请求中重新创建。
- 数据中心编号、节点编号必须通过配置分配，同一时刻不得重复。
- 生成器必须检测时钟回拨。发生不可容忍的回拨时应拒绝生成并告警，不能静默产生重复 ID。
- ID 在 Python 和数据库内部为 `int`，在 JSON 和 JWT 中使用十进制字符串。请求不得接受 JSON Number 形式的雪花 ID，防止调用方在序列化前已经丢失精度。
- 不得从雪花 ID 推导权限或租户归属；租户归属始终以数据库字段为准。

正例：

```python
entity_id = id_generator.next_id()
customer = Customer(id=entity_id, tenant_id=current_user.tenant_id, ...)
```

反例：

```python
entity_id = int(time.time() * 1000)  # 并发时可能重复
entity_id = random.randint(1, 9999)  # 无唯一性保证
```

### 2.5 索引和约束

- 主键固定为 `id`。
- 租户内唯一约束必须包含 `tenant_id`，除非字段明确为全平台唯一。
- 常用查询索引通常以 `tenant_id` 开头，再按等值过滤、范围过滤和排序字段排列。
- 分页默认按 `created_at DESC, id DESC` 时，应评估 `(tenant_id, created_at, id)` 联合索引。
- 外键是否落数据库由项目统一决定；不使用外键时，Service 必须校验引用对象并提供数据一致性巡检。
- 不得为每个字段盲目建立单列索引；新增索引必须对应明确查询并检查执行计划。
- 唯一性必须由数据库唯一约束兜底，不能只做“先查询再新增”。

反例：

```sql
UNIQUE KEY uk_customer_code (customer_code); -- 错误地限制成全平台唯一
KEY idx_status (status);                      -- 低区分度且没有租户前缀
```

### 2.6 字段类型和大字段

- 短文本使用有明确上限的 `VARCHAR`。
- 金额使用 `DECIMAL(precision, scale)`，禁止使用 `FLOAT`、`DOUBLE` 保存金额。
- 状态使用 `SMALLINT` 并在注释和代码枚举中定义含义。
- 结构化且需要查询的数据优先拆分成字段或子表，不应全部塞入 JSON。
- 文件、图片、音视频不得以 Base64 或 BLOB 放入普通业务主表，应保存到对象存储，数据库只存对象键、摘要、大小和内容类型。
- 应少用 `TEXT`，原则上不在主表使用 `LONGTEXT`。大文本拆到一对一扩展表，大量明细拆到一对多子表。
- 确需使用 JSON/TEXT 时，必须说明容量上限、是否检索、索引方案、归档策略和脱敏要求。

正例：

```text
biz_article                 保存标题、状态等高频字段
biz_article_content         保存正文，一对一按需加载
biz_article_attachment      保存对象存储引用，一对多
```

反例：

```sql
payload LONGTEXT COMMENT '所有数据'; -- 无边界、无法约束、难以索引和归档
```

### 2.7 字符集和时间语义

- MySQL 业务库、表和连接统一使用 `utf8mb4`；排序规则由项目统一选择，不得由单表随意改变。
- PostgreSQL 数据库使用 UTF-8 编码。
- 当前 `SafeDatetime` 输出不携带时区偏移，因此所有服务、数据库 Session 和异步任务必须使用同一个应用时区，项目默认 `Asia/Shanghai`。
- 不得在同一系统中混用 UTC、服务器本地时间和业务时区。若未来切换为 UTC 存储，必须同步升级 `SafeDatetime` 为携带时区偏移的格式，并提供存量数据迁移方案。
- 获取当前时间应依赖统一时钟组件，便于测试；禁止在业务代码中散落不同的时间生成方式。

正例：

```python
now = clock.now()  # 返回项目统一业务时区的 datetime
```

反例：

```python
created_at = datetime.now()
updated_at = datetime.utcnow()  # 同一条数据混用两种时间语义
```

---

## 3. Pydantic 模型与字段转换规范

### 3.1 固定转换链路

字段转换链路必须保持单向、可追踪：

```text
数据库 snake_case
  → SQLAlchemy ORM snake_case
  → Pydantic Python 字段 snake_case
  → JSON camelCase
```

| 数据库字段 | ORM/Pydantic 字段 | JSON 字段 | Pydantic 类型 |
| --- | --- | --- | --- |
| `id` | `id` | `id` | 请求使用 `SafeId`，响应使用 `SafeBigInt` |
| `tenant_id` | `tenant_id` | `tenantId` | `SafeBigInt` |
| `version` | `version` | `version` | `int` |
| `status` | `status` | `status` | `int` 或业务枚举 |
| `created_by` | `created_by` | `createdBy` | `SafeBigInt` |
| `created_at` | `created_at` | `createdAt` | `SafeDatetime` |
| `updated_by` | `updated_by` | `updatedBy` | `SafeBigInt` |
| `updated_at` | `updated_at` | `updatedAt` | `SafeDatetime` |

请求可以兼容 `snake_case` 与 `camelCase`；对外响应必须统一输出 `camelCase`。

### 3.2 BaseSchema 和安全类型

接口模型不得直接继承 `pydantic.BaseModel`，必须继承 `pkg.common.api.BaseSchema`：

```python
from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime


class CustomerResponse(BaseSchema):
    """客户响应。"""

    id: SafeBigInt
    tenant_id: SafeBigInt
    customer_name: str
    version: int
    status: int
    created_by: SafeBigInt
    created_at: SafeDatetime
    updated_by: SafeBigInt
    updated_at: SafeDatetime
```

安全类型含义：

- `SafeBigInt` 基于 Pydantic `Annotated` 和序列化器定义。它兼容整数入站，Python 内部为 `int`，JSON 出站为字符串，适合 ORM 到响应模型的转换。
- `SafeId` 是面向外部请求的严格雪花 ID 类型，只接受由数字字符组成的 JSON 字符串；解析后必须满足 `0 < id <= 9223372036854775807`。它用于 Get、Update、Delete 请求中的 `id` 及其他外部雪花 ID。禁止直接用当前宽松的 `SafeBigInt` 接收这些请求字段，因为 JavaScript Number 可能在到达服务端前已被舍入。
- `SafeDatetime` 基于 Pydantic `BeforeValidator` 和序列化器定义。Python 内部为 `datetime`，接口格式统一为 `YYYY-MM-DD HH:mm:ss`。
- `Field` 用于长度、数值范围、列表数量等边界校验。
- `Literal` 或 `Enum` 用于排序方向、状态、过滤操作符等有限集合。

`SafeId` 也必须基于 Pydantic 定义：

```python
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema


SIGNED_BIGINT_MAX = 9_223_372_036_854_775_807


def parse_safe_id(value: object) -> int:
    """只接受有符号 BIGINT 正数范围内的十进制字符串。"""
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError("ID 必须是十进制字符串")
    parsed = int(value)
    if not 0 < parsed <= SIGNED_BIGINT_MAX:
        raise ValueError("ID 超出 BIGINT 正数范围")
    return parsed


SAFE_ID_JSON_SCHEMA = {
    "type": "string",
    "pattern": "^[0-9]+$",
    "minLength": 1,
    "maxLength": 19,
    "description": "有符号 BIGINT 正数范围内的十进制字符串",
}

SafeId = Annotated[
    int,
    BeforeValidator(parse_safe_id, json_schema_input_type=str),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
    WithJsonSchema(SAFE_ID_JSON_SCHEMA, mode="validation"),
    WithJsonSchema(SAFE_ID_JSON_SCHEMA, mode="serialization"),
]
```

这样生成的 OpenAPI/MCP validation schema 和 serialization schema 都是 `string`，不会诱导客户端发送 JSON Number。响应实体字段继续使用 `SafeBigInt`，请求 ID 使用 `SafeId`。

普通 `BaseSchema` 当前会兼容额外字段。面向写操作的请求应增加严格请求基类，防止伪造的系统字段被静默忽略：

```python
from pydantic import ConfigDict


class BaseRequestSchema(BaseSchema):
    """禁止未知字段的接口请求基类。"""

    model_config = ConfigDict(
        alias_generator=BaseSchema.model_config["alias_generator"],
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )
```

Create、Get、Update、Delete 和 Page 五类 Request 均应继承 `BaseRequestSchema`。响应模型继续继承 `BaseSchema`。如果项目决定直接把 `extra="forbid"` 加入全局 `BaseSchema`，必须先评估现有接口兼容性。

正例：

```python
class CustomerCreateRequest(BaseRequestSchema):
    """创建客户请求。"""

    customer_name: str = Field(min_length=1, max_length=100)
    customer_code: str = Field(min_length=1, max_length=64)
    status: int = Field(default=1, ge=0, le=1)
```

反例：

```python
class CustomerResponse(BaseModel):
    id: int             # JSON 大整数可能丢失精度
    created_at: str     # 没有统一的解析、格式和类型约束
    tenantId: int       # Python 代码中错误地使用 camelCase
```

### 3.3 模型职责分离

每个资源至少定义以下模型：

```text
CustomerCreateRequest
CustomerGetRequest
CustomerUpdateRequest
CustomerDeleteRequest
CustomerPageFilter
CustomerPageRequest
CustomerResponse
CustomerDeleteResponse
```

- Create Request 只包含允许客户端创建的业务字段。
- Update Request 包含 `id`、`version` 和可更新业务字段。
- Response 可以包含租户、版本和完整审计字段。
- ORM 模型不能直接作为 FastAPI 请求或响应模型。
- ORM 转响应统一使用 `model_validate(entity, from_attributes=True)`。
- `tenant_id`、`created_by`、`created_at`、`updated_by`、`updated_at` 不得出现在 Create/Update Request。

---

## 4. 固定接口规范

### 4.1 接口清单

以客户资源 `customers` 为例：

| 功能 | 方法和路径 | 权限码 | 是否写事务 |
| --- | --- | --- | --- |
| 新增 | `POST /customers/create` | `customer:create` | 是 |
| 按 ID 查询 | `POST /customers/get` | `customer:get` | 否 |
| 更新 | `POST /customers/update` | `customer:update` | 是 |
| 物理删除 | `POST /customers/delete` | `customer:delete` | 是 |
| 分页查询 | `POST /customers/page` | `customer:page` | 否 |

接口路径使用复数资源名，动作使用固定小写单词。不得混用 `/queryPage`、`/list-page`、`/remove` 等其他写法。

### 4.2 公共请求头

| 请求头 | 是否必需 | 含义 |
| --- | --- | --- |
| `Authorization` | 是 | `Bearer <access-token>` |
| `Content-Type` | 是 | `application/json` |
| `X-Trace-Id` | 否 | 调用方提供的追踪 ID；不合法时服务端重新生成 |
| `X-Idempotency-Key` | Create 建议 | 新增请求幂等键，同一租户内唯一 |

服务端必须在所有成功和失败响应中返回：

```http
X-Trace-Id: 4bf92f3577b34da6a3ce929d0e0e4736
```

### 4.3 统一响应

成功响应：

```json
{
  "code": 0,
  "msg": "success",
  "data": {}
}
```

失败响应：

```json
{
  "code": 40901,
  "msg": "数据已被其他用户修改，请刷新后重试",
  "data": null
}
```

- HTTP 状态码表达传输和协议语义，`code` 表达稳定的业务错误语义。
- `code = 0` 表示成功，非零表示失败。
- Trace ID 只放响应头，不重复放入响应体。
- 不得直接返回 ORM 对象、裸列表、字符串或 FastAPI 默认错误结构。

反例：

```json
[ { "id": 1 } ]
```

```json
{ "success": false, "error": "SQLSyntaxError at ..." }
```

### 4.4 新增接口

请求：

```http
POST /customers/create
X-Idempotency-Key: 32f8d1c0-0b23-4b82-b319-1a9f0ce614d4
```

```json
{
  "customerName": "示例客户",
  "customerCode": "CUS-001",
  "description": "客户说明",
  "status": 1
}
```

服务端生成：`id`、`tenant_id`、`version`、`created_by`、`created_at`、`updated_by`、`updated_at`。

成功响应 `data` 返回完整资源。重复幂等键必须返回第一次成功结果，不能重复写入。幂等键应至少按 `tenant_id + user_id + resource + key` 建立数据库唯一约束，并设置合理过期策略。

服务端必须对规范化后的请求体计算请求指纹并与幂等记录一起保存：

- 相同键、相同请求指纹且首次请求已成功：返回首次响应。
- 相同键、不同请求指纹：返回 HTTP `409`，不得返回不相关的首次结果。
- 相同键且首次请求仍在处理中：返回明确的“请求处理中”冲突或等待既定短时窗口，不得并发执行两次。
- 幂等占位记录、业务新增和最终响应记录应在可证明原子的事务方案中完成。使用同一数据库时优先放在同一事务并依赖唯一约束竞争；跨存储实现必须说明锁、租约、失败恢复和过期规则。

反例：

```json
{
  "id": "100",
  "tenantId": "2",
  "createdBy": "3",
  "customerName": "越权指定系统字段"
}
```

### 4.5 按 ID 查询接口

请求：

```json
{
  "id": "1938172456172216320"
}
```

查询条件必须至少包含：

```sql
WHERE id = :id AND tenant_id = :tenant_id
```

不存在或不属于当前租户时统一返回资源不存在，不得泄露其他租户是否存在该 ID。

### 4.6 更新接口

请求：

```json
{
  "id": "1938172456172216320",
  "version": 3,
  "customerName": "修改后的名称",
  "status": 1
}
```

- `id` 和 `version` 必填。
- 业务字段可选，只更新请求中实际出现的字段。
- 至少提交一个可更新业务字段；该规则由 Pydantic 模型校验，空更新请求返回 `422` 和业务码 `42200`。
- 数据库非空字段可以不传，但不得显式传 `null`；只有数据库和业务模型都允许为空的字段才能使用 `null` 清空。
- 服务端必须移除或拒绝任何系统字段。
- 更新条件必须包含 `id + tenant_id + version`。
- 更新成功执行 `version = version + 1`，并更新 `updated_by`、`updated_at`。
- 版本不匹配返回 HTTP `409` 和业务码 `40901`。
- 成功响应返回更新后的完整资源和新版本号。

正例：

```python
update_data = body.model_dump(
    exclude={"id", "version"},
    exclude_unset=True,
)
```

反例：

```python
update_data = body.model_dump()
await db.execute(update(Customer).values(**update_data))  # 修改全部行且允许覆盖系统字段
```

### 4.7 物理删除接口

请求：

```json
{
  "id": "1938172456172216320",
  "version": 4
}
```

- 删除不可恢复，必须校验 `customer:delete` 权限。
- 删除条件必须包含 `id + tenant_id + version`。
- 删除前必须获取安全的业务快照并写入审计记录。
- 每个资源必须在设计时声明关联删除策略：`RESTRICT`、数据库 `CASCADE` 或 Service 显式事务删除，不能留到运行时临时决定。
- 默认使用 `RESTRICT`：存在有效子记录时返回 `409`，要求先处理子记录。只有生命周期完全依附主记录、无需单独保留的扩展数据才可以级联删除。
- 仅在删除前查询 `CASCADE` 对象不足以保证审计完整，因为查询后仍可能并发插入子记录。使用数据库 `CASCADE` 且要求逐条审计时，必须通过数据库审计触发器、可靠 CDC，或经验证的串行化事务与锁策略记录数据库实际删除集合；无法证明无漏审计时禁止使用 `CASCADE`。
- 使用显式事务删除时，应锁定主记录，按“最末级子表 → 关系表 → 扩展表 → 主表”顺序执行，并在同一事务内记录所有受影响资源 ID 和安全快照。并发新增子记录必须被约束阻止，或使最终主表删除失败并整体回滚。
- 不存在返回 `404`；版本不一致返回 `409`。
- 成功响应只返回被删除 ID：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "id": "1938172456172216320"
  }
}
```

反例：

```python
await db.execute(delete(Customer).where(Customer.id == body.id))
# 缺少 tenant_id、version、权限和审计
```

### 4.8 分页查询接口

请求：

```json
{
  "page": 1,
  "pageSize": 20,
  "keyword": "示例",
  "filters": {
    "status": 1,
    "createdAtStart": "2026-08-01 00:00:00",
    "createdAtEnd": "2026-09-01 00:00:00"
  },
  "sorts": [
    { "field": "createdAt", "direction": "desc" },
    { "field": "id", "direction": "asc" }
  ]
}
```

字段含义：

| 字段 | 必填 | 默认值 | 约束 | 含义 |
| --- | --- | --- | --- | --- |
| `page` | 否 | `1` | `>= 1` | 当前页码 |
| `pageSize` | 否 | `20` | `1..200` | 每页数量 |
| `keyword` | 否 | `null` | 最长 100，去除首尾空格 | 模糊检索关键词 |
| `filters` | 否 | `{}` | 每个资源定义强类型模型 | 结构化精确、范围筛选 |
| `sorts` | 否 | 默认排序 | 最多 3 项 | 多字段排序 |
| `sorts[].field` | 是 | 无 | 必须在资源排序白名单 | 对外排序字段 |
| `sorts[].direction` | 是 | 无 | `asc` 或 `desc` | 升序或降序 |

分页响应：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "items": [],
    "total": 125,
    "page": 1,
    "pageSize": 20,
    "totalPages": 7
  }
}
```

分页规则：

- `keyword` 只在每个资源预定义的文本字段中进行模糊匹配。例如客户只检索 `customer_name`、`customer_code`，不能检索所有列。
- 模糊查询必须转义 `%`、`_` 和转义字符本身。
- `filters` 使用具体资源的 Pydantic 模型，不接受任意字段、任意操作符或原始 SQL。
- 时间范围统一使用左闭右开区间 `[createdAtStart, createdAtEnd)`，查询条件为 `>= start AND < end`。结束时间传下一周期起点，避免数据库微秒精度高于接口秒精度时漏数。Pydantic 必须校验开始时间早于结束时间。
- 排序字段必须使用显式白名单映射。
- 默认排序为 `createdAt desc, id desc`。
- 如果客户端排序没有包含 `id`，服务端应在最后追加同方向或规定方向的 `id`，保证排序稳定。
- `COUNT` 查询与数据查询必须使用完全相同的租户和过滤条件。
- 深分页或超大数据量应增加游标分页专用接口，不能无限提高 `pageSize`。

排序字段转换正例：

```python
SORT_COLUMNS = {
    "id": Customer.id,
    "customerName": Customer.customer_name,
    "createdAt": Customer.created_at,
    "updatedAt": Customer.updated_at,
}

column = SORT_COLUMNS.get(sort_item.field)
if column is None:
    raise BadRequestException("不支持的排序字段")
order_expression = column.asc() if sort_item.direction == "asc" else column.desc()
```

反例：

```python
stmt = stmt.order_by(text(f"{body.sort_field} {body.sort_order}"))
# 客户端字段直接进入 SQL，存在 SQL 注入风险
```

---

## 5. 接口模型样例

```python
from typing import Annotated, Literal

from pydantic import Field, WithJsonSchema, field_validator, model_validator

from pkg.common.api import (
    BaseRequestSchema,
    BaseSchema,
    SafeBigInt,
    SafeDatetime,
    SafeId,
)


class SortItem(BaseRequestSchema):
    """分页排序项。"""

    field: str = Field(min_length=1, max_length=64)
    direction: Literal["asc", "desc"]


class CustomerCreateRequest(BaseRequestSchema):
    """创建客户请求。"""

    customer_name: str = Field(min_length=1, max_length=100)
    customer_code: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    status: int = Field(default=1, ge=0, le=1)


class CustomerGetRequest(BaseRequestSchema):
    """按 ID 查询客户请求。"""

    id: SafeId


UPDATE_CUSTOMER_NAME_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 100,
}
UPDATE_STATUS_SCHEMA = {
    "type": "integer",
    "minimum": 0,
    "maximum": 1,
}
UpdateCustomerName = Annotated[
    str | None,
    WithJsonSchema(UPDATE_CUSTOMER_NAME_SCHEMA, mode="validation"),
]
UpdateStatus = Annotated[
    int | None,
    WithJsonSchema(UPDATE_STATUS_SCHEMA, mode="validation"),
]


class CustomerUpdateRequest(BaseRequestSchema):
    """更新客户请求。"""

    id: SafeId
    version: int = Field(ge=1)
    # 默认 None 表示省略；WithJsonSchema 保证外部契约不声明 null 合法。
    customer_name: UpdateCustomerName = None
    description: str | None = Field(default=None, max_length=1000)
    status: UpdateStatus = None

    @field_validator("customer_name")
    @classmethod
    def validate_customer_name(cls, value: str | None) -> str:
        """校验更新客户名称的长度。"""
        if value is None:
            raise ValueError("客户名称不能设置为 null")
        if not 1 <= len(value) <= 100:
            raise ValueError("客户名称长度必须在 1 到 100 之间")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: int | None) -> int:
        """校验更新状态。"""
        if value is None:
            raise ValueError("状态不能设置为 null")
        if value not in (0, 1):
            raise ValueError("状态只能为 0 或 1")
        return value

    @model_validator(mode="after")
    def validate_update_fields(self) -> "CustomerUpdateRequest":
        """至少要求一个业务更新字段。"""
        fields = self.model_fields_set - {"id", "version"}
        if not fields:
            raise ValueError("至少提交一个需要更新的业务字段")
        return self


class CustomerDeleteRequest(BaseRequestSchema):
    """物理删除客户请求。"""

    id: SafeId
    version: int = Field(ge=1)


class CustomerPageFilter(BaseRequestSchema):
    """客户分页筛选条件。"""

    status: int | None = Field(default=None, ge=0, le=1)
    created_at_start: SafeDatetime | None = None
    created_at_end: SafeDatetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "CustomerPageFilter":
        """时间范围采用左闭右开区间，并要求开始早于结束。"""
        if (
            self.created_at_start is not None
            and self.created_at_end is not None
            and self.created_at_start >= self.created_at_end
        ):
            raise ValueError("createdAtStart 必须早于 createdAtEnd")
        return self


class CustomerPageRequest(BaseRequestSchema):
    """客户分页请求。"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    keyword: str | None = Field(default=None, max_length=100)
    filters: CustomerPageFilter = Field(default_factory=CustomerPageFilter)
    sorts: list[SortItem] = Field(default_factory=list, max_length=3)


class CustomerResponse(BaseSchema):
    """客户响应。"""

    id: SafeBigInt
    tenant_id: SafeBigInt
    customer_name: str
    customer_code: str
    description: str | None
    version: int
    status: int
    created_by: SafeBigInt
    created_at: SafeDatetime
    updated_by: SafeBigInt
    updated_at: SafeDatetime


class CustomerDeleteResponse(BaseSchema):
    """客户删除响应。"""

    id: SafeBigInt
```

说明：

- 对数据库非空字段，默认 `None` 仅作为“字段省略”的内部哨兵且默认值不参与校验；`WithJsonSchema(mode="validation")` 让 HTTP 请求和 MCP Tool 输入只声明真实的非空类型，`field_validator` 负责拒绝显式 `null` 并执行运行时边界校验。
- Update Request 是输入模型，不得作为接口响应模型。Service 提取更新数据必须使用 `model_dump(exclude_unset=True)`；如果测试或内部转发需要序列化请求模型，也必须使用 `exclude_unset=True`，不得依赖其普通 serialization schema 表达省略语义。
- 对 `description` 等真实可空字段，使用 `str | None`；如果业务需要将其显式更新为 `null`，必须使用 `model_fields_set` 区分“未传字段”和“明确传入 null”，不能简单过滤所有 `None`。

---

## 6. 数据库连接规范

### 6.1 配置和密钥

- 使用项目 `DatabaseSettings` 和 `AsyncDatabaseManager` 创建异步 Engine。
- 支持 MySQL `asyncmy` 和 PostgreSQL `asyncpg`，业务代码不得依赖具体驱动 API。
- 生产账号、密码和连接参数通过环境变量或密钥服务注入，禁止提交真实密码。
- 生产数据库账号使用最小权限；应用账号不得拥有建库、删库和用户管理权限。
- 生产连接应启用 TLS，并验证服务端证书。
- 应配置连接超时、连接池大小、溢出连接、回收时间和连接前探活。
- 应用启动可以执行 `SELECT 1` 健康检查，但健康检查不得执行写操作。

配置正例：

```yaml
database:
  type: mysql
  host: 127.0.0.1
  port: 3306
  username: app_user
  password: "${由环境或密钥服务注入}"
  database: pythonbase
  connect_timeout: 10
  startup_check: true
  pool:
    size: 10
    max_overflow: 20
    timeout: 30
    recycle: 1800
    pre_ping: true
```

反例：

```python
engine = create_async_engine("mysql+asyncmy://root:real-password@prod/db")
```

### 6.2 Session 类型

项目统一提供两种会话依赖：

```text
get/page                    → manager.session()，不自动提交
create/update/delete        → manager.transaction()，成功提交、异常回滚
```

- 同一请求中的 Route、Service、Repository 必须共享同一个 `AsyncSession`。
- 禁止在 Service 或 Repository 内重新创建 Engine 或 Session。
- Session 不能跨请求、跨线程或跨异步任务共享。
- Celery 任务使用任务进程提供的数据库管理器，不得复用 HTTP 请求 Session。

---

## 7. CRUD 分层和数据库操作规范

### 7.1 固定分层

```text
Route → Service → Repository/Crud → AsyncSession
```

| 层 | 负责 | 禁止 |
| --- | --- | --- |
| Route | 请求模型、依赖注入、权限声明、响应包装 | 直接写 SQL、提交事务、拼业务错误响应 |
| Service | 业务校验、租户和用户上下文、事务内编排、异常语义 | 创建数据库连接、返回裸 SQLAlchemy 异常 |
| Repository/Crud | SQLAlchemy 查询、`flush()`、`refresh()` | 鉴权、HTTP 语义、`commit()`、吞掉异常 |
| ORM Model | 表映射、约束和关系 | 作为接口请求/响应模型直接暴露 |

### 7.2 Repository 规范

- 使用 SQLAlchemy 2.x `select`、`insert`、`update`、`delete`。
- 所有租户数据访问方法必须显式接收 `tenant_id`，或使用 `TenantAwareCrud` 自动附加租户条件。
- 写操作只执行 `flush()` 和必要的 `refresh()`。
- 不捕获通用 `Exception` 后返回 `None`。
- 不在循环中逐条查询；优先集合查询、JOIN、`selectinload` 或批量写入。
- 客户端字段必须通过白名单映射为 ORM Column。
- 查询必须只选择所需字段和关系，禁止默认加载无关大字段。

正例：

```python
async def get_customer(self, *, tenant_id: int, customer_id: int) -> Customer | None:
    """按租户和 ID 查询客户。"""
    statement = select(Customer).where(
        Customer.id == customer_id,
        Customer.tenant_id == tenant_id,
    )
    result = await self.db.execute(statement)
    return result.scalars().first()
```

反例：

```python
async def get_customer(self, customer_id):
    sql = f"SELECT * FROM biz_customer WHERE id = {customer_id}"
    return await self.db.execute(text(sql))  # SQL 注入、无租户条件、无类型注解
```

### 7.3 Service 规范

Service 必须：

1. 从 `AuthContext` 获取用户和租户。
2. 校验资源操作权限。
3. 调用 Repository，并把预期数据库异常转换为业务异常。
4. 维护雪花 ID、版本和审计字段。
5. 返回领域对象或响应模型，不返回 `JSONResponse`。

更新伪代码：

```python
async def update_customer(
    self,
    body: CustomerUpdateRequest,
    current_user: CurrentUser,
) -> Customer:
    """使用租户和乐观锁更新客户。"""
    update_data = body.model_dump(
        exclude={"id", "version"},
        exclude_unset=True,
    )
    entity = await self.repository.update_customer(
        tenant_id=current_user.tenant_id,
        customer_id=body.id,
        expected_version=body.version,
        update_data=update_data,
        updated_by=current_user.user_id,
        updated_at=clock.now(),
    )
    if entity is not None:
        return entity

    existing = await self.repository.get_customer(
        tenant_id=current_user.tenant_id,
        customer_id=body.id,
    )
    if existing is None:
        raise NotFoundException("客户不存在")
    raise ConflictException("数据已被其他用户修改，请刷新后重试", code=40901)
```

### 7.4 事务规范

- 一个写接口对应一个事务边界。
- 正常返回时提交；抛出任何异常时回滚。
- Repository 不得提交，否则 Service 无法保证多个写操作原子性。
- 数据库事务不能覆盖 HTTP、消息队列、对象存储等外部系统。
- 需要“数据库写入后可靠发消息”时使用事务外盒；需要重试时设计幂等键。
- 禁止在事务中执行长时间网络调用，以免长期占用连接和锁。
- 捕获 `IntegrityError` 后不得继续使用失败事务执行其他 SQL，应转换异常并让事务边界回滚。

正例：

```python
async with manager.transaction() as db:
    customer = await customer_repository.create(...)
    await audit_repository.record_success(...)
# 离开上下文后一起提交
```

反例：

```python
await repository.create_customer(...)
await db.commit()
await repository.create_relation(...)
await db.commit()  # 第二步失败时第一步无法回滚
```

### 7.5 并发和乐观锁

更新 SQL 必须包含版本条件：

```sql
UPDATE biz_customer
SET customer_name = :customer_name,
    version = version + 1,
    updated_by = :updated_by,
    updated_at = :updated_at
WHERE id = :id
  AND tenant_id = :tenant_id
  AND version = :expected_version;
```

受影响行数：

- `1`：成功。
- `0` 且资源不存在：返回 `404`。
- `0` 且资源存在：版本冲突，返回 `409`。

物理删除同样校验版本，避免用户根据旧页面删除已经被他人修改的数据。

---

## 8. JWT、当前用户和权限规范

### 8.1 JWT 传递

统一使用：

```http
Authorization: Bearer <access-token>
```

访问令牌只包含最小身份信息。为兼容项目现有 `TokenService`，声明名称使用：

```json
{
  "iss": "pythonbase",
  "sub": "1938172456172216320",
  "tid": "1938172456172216301",
  "ver": 3,
  "type": "access",
  "iat": 1787900000,
  "exp": 1787903600,
  "jti": "a1b2c3d4e5f6"
}
```

- `sub`：用户 ID，使用字符串。
- `tid`：当前租户 ID，使用字符串；平台级令牌可以为空，但无 `tid` 的令牌不得调用本文定义的普通租户 CRUD。
- `ver`：令牌版本，用于登出、改密、封禁后吊销旧令牌。
- `type`：必须为 `access`；刷新令牌必须为 `refresh` 且不能调用业务接口。
- 必须校验算法、签名、`iss`、`exp`、`type` 和服务器保存的 token version。
- JWT 中不得保存密码、密钥、手机号、身份证号等敏感数据。
- 角色和权限默认不写入 JWT，避免权限变更后旧令牌继续拥有旧权限；验证身份后从数据库或短时缓存加载。

### 8.2 当前用户上下文

统一认证依赖把 JWT 转换为不可变的请求上下文：

```python
@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: int
    tenant_id: int
    username: str | None
    roles: frozenset[str]
    permissions: frozenset[str]
    token_version: int
```

- Route 和 Service 通过依赖注入获取上下文，不得自行解析 JWT。
- 普通 CRUD 的认证依赖必须要求非空 `tenant_id`；缺少租户上下文时返回明确的 `403`，不得因为 `tenant_id is None` 而省略租户查询条件。
- `tenant_id`、`created_by`、`updated_by` 必须取自上下文。
- 请求体出现这些只读字段时应由 Pydantic 禁止额外字段或显式拒绝，不能静默信任。
- 数据不存在和跨租户访问统一表现为“资源不存在”，避免泄露其他租户数据。

### 8.3 权限校验

权限码固定为 `资源:动作`：

```text
customer:create
customer:get
customer:update
customer:delete
customer:page
```

- 未提供或无法验证 JWT：HTTP `401`。
- 已认证但缺少权限：HTTP `403`。
- 平台管理员绕过规则必须在统一权限组件实现并记录审计，业务 Service 不得散落硬编码。平台管理员进行跨租户管理时必须使用独立的管理接口和“目标租户上下文解析”依赖：显式选择目标租户、校验平台级权限、确认目标租户存在，然后生成非空的作用域上下文。目标租户不得通过 `None` 或省略 `tenant_id` 条件来表达。
- 仅校验权限码不等于数据权限；Repository 仍必须附加租户和必要的数据范围条件。

反例：

```python
tenant_id = body.tenant_id
user_id = body.updated_by
# 客户端可以伪造租户和操作人
```

---

## 9. 全局异常处理规范

### 9.1 异常职责

- Pydantic 负责请求结构、类型和边界校验。
- Service 抛出业务异常。
- Repository 只转换明确且可稳定识别的数据库异常，或让 Service/全局层处理。
- 全局异常处理器将所有异常转换为 `ApiResponse`。
- 详细堆栈只写服务端日志，不返回调用方。

### 9.2 HTTP 状态和业务码

| 场景 | HTTP 状态 | 默认业务码 | 示例消息 |
| --- | --- | --- | --- |
| 参数错误 | 400 | 40000 | 请求参数错误 |
| 未认证 | 401 | 40100 | 请先登录 |
| 无权限 | 403 | 40300 | 无权限访问 |
| 资源不存在 | 404 | 40400 | 客户不存在 |
| 唯一约束冲突 | 409 | 40900 | 客户编码已存在 |
| 乐观锁冲突 | 409 | 40901 | 数据已被其他用户修改 |
| Pydantic 校验失败 | 422 | 42200 | 数据校验失败 |
| 未知服务器异常 | 500 | 50000 | 服务器内部错误，请稍后重试 |

全局处理器必须覆盖：

- `AppException` 及子类。
- `RequestValidationError`，转换 FastAPI 默认 `detail` 格式。
- Starlette/FastAPI HTTP 异常。
- 数据库连接、超时和完整性异常的安全兜底。
- 未捕获异常。

校验错误可以返回安全字段列表：

```json
{
  "code": 42200,
  "msg": "数据校验失败",
  "data": {
    "errors": [
      {
        "field": "customerName",
        "message": "字段长度不能小于 1"
      }
    ]
  }
}
```

反例：

```python
try:
    ...
except Exception as exc:
    return {"error": str(exc)}  # 泄露内部信息、破坏统一格式、可能错误提交事务
```

---

## 10. Trace ID 规范

### 10.1 生成和传递

Trace 中间件在请求最外层执行：

```text
读取 X-Trace-Id
  → 校验字符和长度
  → 缺失或非法时生成
  → 写入 ContextVar/request.state
  → 注入日志、审计和下游请求
  → 写入所有成功与异常响应头
```

- 推荐使用 32 位小写十六进制 Trace ID。
- 客户端值必须限制长度和字符集，防止日志注入。
- 所有响应必须返回 `X-Trace-Id`，包括 `401`、`403`、`404`、`422`、`500`。
- 接入 OpenTelemetry 时同时遵循 W3C `traceparent`；`X-Trace-Id` 作为便于前端、Agent 和运维查询的响应头。
- Trace ID 不放入统一响应体。

### 10.2 正反例

正例日志：

```json
{
  "level": "INFO",
  "message": "更新客户成功",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "tenant_id": "1938172456172216301",
  "user_id": "1938172456172216320",
  "resource_id": "1938172456172216400",
  "duration_ms": 18
}
```

反例：

```text
更新成功
```

该日志无法定位请求、租户、用户和资源。

---

## 11. 日志和操作审计规范

### 11.1 应用日志

- 使用项目统一 Loguru 入口，不得在业务模块重新配置 sink。
- 生产环境建议输出结构化 JSON。
- 日志必须包含 `trace_id`、模块、请求路径、耗时；认证后补充 `tenant_id`、`user_id`。
- 禁止打印 JWT、刷新令牌、密码、密钥、完整 Authorization 头和数据库连接串。
- 身份证号、手机号、邮箱等个人信息按字段策略脱敏。
- 预期业务异常记录 `WARNING` 或合适级别，未知异常记录堆栈和 `ERROR`。

### 11.2 审计日志字段

审计表至少包含：

| 字段 | 含义 |
| --- | --- |
| `id` | 雪花审计 ID |
| `tenant_id` | 操作租户 |
| `trace_id` | 请求追踪 ID |
| `user_id` | 操作用户 |
| `action` | `create/get/update/delete/page` |
| `resource_type` | 资源类型 |
| `resource_id` | 单资源 ID，可为空 |
| `request_path` | 请求路径 |
| `client_ip` | 客户端 IP，需按可信代理规则解析 |
| `user_agent` | 调用端标识 |
| `result` | `success/failure` |
| `error_code` | 失败业务码，可为空 |
| `duration_ms` | 处理耗时 |
| `before_data` | 更新/删除前的脱敏快照或差异 |
| `after_data` | 新增/更新后的脱敏快照或差异 |
| `created_at` | 审计发生时间 |

### 11.3 审计行为

- 新增、更新、删除必须审计。
- 查询敏感数据、导出、批量操作和权限变更必须审计。
- 普通分页是否逐次审计可以按资源敏感级别配置，但必须有访问日志和指标。
- 更新审计记录变更字段及前后值；物理删除记录删除前快照。
- 成功审计与业务写入在同一事务提交，确保业务成功必有审计。
- 失败审计在业务事务回滚后通过独立事务或可靠异步通道写入。
- 审计存储必须采用追加写（append-only）权限模型。普通业务代码不得执行审计记录的更新和删除；归档/清理只能由独立运维身份按审批策略执行。
- 高合规场景应使用独立审计账号或独立存储、集中式不可变日志、对象锁/WORM 或哈希链等防篡改措施，不能只依赖应用代码约定。
- 必须监控审计写入失败并告警。新增、更新、删除属于强制审计操作，无法生成成功审计时必须阻止业务事务提交（fail-closed）。风险分级只适用于普通查询等可选审计事件。
- 审计记录对普通业务账号只读，按合规要求定义保留、分区和归档周期。
- `before_data`、`after_data` 不应无边界存储完整大对象；优先记录字段差异，大内容保存摘要或安全引用。

反例：

```python
logger.info("request=%s", body.model_dump())
# 可能把密码、令牌、个人信息和大文本完整写入日志
```

---

## 12. FastAPI 路由实现样例

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from pkg.common.api import ApiResponse, PageData
from pkg.security import require_permission

router = APIRouter(prefix="/customers", tags=["客户管理"])


@router.post(
    "/create",
    response_model=ApiResponse[CustomerResponse],
    dependencies=[Depends(require_permission("customer:create"))],
)
async def create_customer(
    body: CustomerCreateRequest,
    service: Annotated[CustomerService, Depends(get_write_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[CustomerResponse]:
    """创建客户。"""
    entity = await service.create(body, current_user=current_user)
    return ApiResponse(data=CustomerResponse.model_validate(entity, from_attributes=True))


@router.post(
    "/get",
    response_model=ApiResponse[CustomerResponse],
    dependencies=[Depends(require_permission("customer:get"))],
)
async def get_customer(
    body: CustomerGetRequest,
    service: Annotated[CustomerService, Depends(get_read_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[CustomerResponse]:
    """按 ID 查询客户。"""
    entity = await service.get(body.id, current_user=current_user)
    return ApiResponse(data=CustomerResponse.model_validate(entity, from_attributes=True))


@router.post(
    "/update",
    response_model=ApiResponse[CustomerResponse],
    dependencies=[Depends(require_permission("customer:update"))],
)
async def update_customer(
    body: CustomerUpdateRequest,
    service: Annotated[CustomerService, Depends(get_write_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[CustomerResponse]:
    """更新客户。"""
    entity = await service.update(body, current_user=current_user)
    return ApiResponse(data=CustomerResponse.model_validate(entity, from_attributes=True))


@router.post(
    "/delete",
    response_model=ApiResponse[CustomerDeleteResponse],
    dependencies=[Depends(require_permission("customer:delete"))],
)
async def delete_customer(
    body: CustomerDeleteRequest,
    service: Annotated[CustomerService, Depends(get_write_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[CustomerDeleteResponse]:
    """物理删除客户。"""
    await service.delete(body, current_user=current_user)
    return ApiResponse(data=CustomerDeleteResponse(id=body.id))


@router.post(
    "/page",
    response_model=ApiResponse[PageData[CustomerResponse]],
    dependencies=[Depends(require_permission("customer:page"))],
)
async def page_customers(
    body: CustomerPageRequest,
    service: Annotated[CustomerService, Depends(get_read_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[PageData[CustomerResponse]]:
    """分页查询客户。"""
    result = await service.page(body, current_user=current_user)
    return ApiResponse(data=result)
```

注意：当前项目 `PageData` 只有 `items/total/page/pageSize`。落实本规范时应增加只读计算字段 `total_pages`，并统一 `PageParams.page_size` 与 `BaseCrud.list_page().size` 的名称、默认值和最大值。

---

## 13. MCP Tool 映射规范

命令式接口可以一一映射为 MCP Tool：

| HTTP 接口 | MCP Tool 建议名称 | JSON 入参模型 |
| --- | --- | --- |
| `/customers/create` | `customer_create` | `CustomerCreateRequest` |
| `/customers/get` | `customer_get` | `CustomerGetRequest` |
| `/customers/update` | `customer_update` | `CustomerUpdateRequest` |
| `/customers/delete` | `customer_delete` | `CustomerDeleteRequest` |
| `/customers/page` | `customer_page` | `CustomerPageRequest` |

- MCP Tool Schema 应由同一份 Pydantic 请求模型生成，避免 HTTP 与 Tool 参数漂移。
- Tool 描述必须明确字段含义、权限、物理删除不可恢复和乐观锁要求。
- Tool 调用仍必须带认证上下文，不能因为调用者是 Agent 就跳过权限和租户过滤。
- Agent 重试 Create Tool 时必须复用同一个幂等键。
- 分页 Tool 的排序和筛选仍使用白名单，不接受 Agent 生成的 SQL。
- 物理删除 Tool 应在上层交互中要求明确确认；服务端仍执行权限、版本和审计校验。

---

## 14. 测试规范

每个 CRUD 资源至少覆盖以下测试：

### 14.1 Pydantic 模型测试

- 请求同时接受 `snake_case` 和 `camelCase`。
- 响应默认输出 `camelCase`。
- `SafeId` 只接受合法十进制字符串，并拒绝 JSON Number、非正数和超出有符号 BIGINT 的值。
- `SafeId` 的 validation/serialization JSON Schema 均声明为带数字正则的 `string`，OpenAPI 和 MCP Tool Schema 不得显示为 `integer`。
- `SafeBigInt` 用于响应时将 Python `int` 输出为 JSON 字符串。
- `SafeDatetime` 正确解析和格式化。
- 字段长度、状态范围、页码、每页数量和排序方向校验。
- Update 至少包含一个业务更新字段。
- Create、Get、Update、Delete、Page 五类请求均拒绝未知字段；Create/Update 拒绝系统字段。
- Update 非空业务字段显式传 `null` 时返回 422，可空字段允许用 `null` 清空。
- Update 的 OpenAPI/MCP Schema 中，非空业务字段可省略但不包含 `null` 类型。
- 分页时间范围必须满足开始早于结束，并按左闭右开区间查询。

### 14.2 Service 测试

- 自动写入雪花 ID、租户和审计字段。
- 跨租户查询、更新和删除均不可见。
- 无权限返回 `403`。
- 资源不存在返回 `404`。
- 乐观锁版本冲突返回 `40901`。
- 唯一约束冲突转换为稳定业务异常。
- 物理删除写入删除前审计快照。
- 存在关联数据时按资源声明的 RESTRICT/CASCADE/显式删除策略执行，并覆盖所有受影响对象的审计。

### 14.3 Repository 和分页测试

- `COUNT` 与数据查询过滤条件一致。
- 关键词只检索白名单字段并正确转义 `%`、`_`。
- 结构化过滤的等值和时间范围正确。
- 单字段、多字段、默认排序正确且顺序稳定。
- 非法排序字段不会进入 SQL。
- `pageSize > 200` 被 Pydantic 拒绝。
- 写操作只 `flush/refresh`，不自行提交。

### 14.4 Web 和中间件测试

- 五个固定接口的路径、请求和响应结构正确。
- 成功、校验失败、认证失败、权限失败和 500 响应均包含 `X-Trace-Id`。
- FastAPI 默认 422 已转换为 `ApiResponse`。
- 日志和审计不包含密码、JWT 和敏感字段原文。
- 相同幂等键不会重复新增。
- 相同幂等键但请求指纹不同返回冲突。

---

## 15. 迁移、性能和运维补充

- 表结构变化必须通过迁移脚本管理，并经过向前、回滚和数据兼容评审。
- 新增索引前检查典型查询的执行计划，避免重复和无效索引。
- 分页接口必须设置超时、最大页大小和慢查询告警。
- 对频繁模糊检索的大数据表，应评估全文索引或独立搜索引擎，不能长期依赖 `%keyword%` 全表扫描。
- 批量新增、更新、删除不属于五个基础接口，必须单独设计最大数量、幂等、权限、事务和审计策略。
- 数据导出、导入和异步任务必须复用同一租户与权限规则。
- 定期监控连接池使用率、查询耗时、冲突率、错误码分布和审计写入失败。
- 敏感配置不得提交 Git；示例配置只能使用占位值。

---

## 16. 开发检查清单

### 数据库

- [ ] 表名和字段名全小写 `snake_case`。
- [ ] 表和所有字段有中文注释。
- [ ] 包含八个固定基础字段。
- [ ] 主键使用应用侧雪花 ID。
- [ ] 租户唯一约束包含 `tenant_id`。
- [ ] 未无边界使用 `LONGTEXT`、JSON、BLOB 或 Base64。
- [ ] 索引对应实际查询并检查执行计划。

### Pydantic 和接口

- [ ] 所有请求、响应模型继承 `BaseSchema`。
- [ ] 请求雪花 ID 使用严格 `SafeId`，BIGINT 响应使用 `SafeBigInt`，时间使用 `SafeDatetime`。
- [ ] 五类请求全部继承 `BaseRequestSchema` 并拒绝未知字段。
- [ ] 数据库/Python 使用 `snake_case`，JSON 输出 `camelCase`。
- [ ] 提供固定五个 POST 接口。
- [ ] 系统字段不在 Create/Update 请求中。
- [ ] 分页支持强类型过滤、白名单模糊检索和白名单排序。
- [ ] 响应统一为 `code/msg/data`。

### 数据和事务

- [ ] 所有查询、更新、删除附加 `tenant_id`。
- [ ] 更新和删除校验 `version`。
- [ ] Repository 不调用 `commit()`。
- [ ] 写接口在一个事务中完成并可整体回滚。
- [ ] 没有字符串拼接 SQL、N+1 或无界查询。

### 安全和可观测性

- [ ] JWT 完整校验并通过统一依赖生成 CurrentUser。
- [ ] 每个接口声明权限码。
- [ ] 所有响应头包含 `X-Trace-Id`。
- [ ] 全局处理 Pydantic、业务、HTTP、数据库和未知异常。
- [ ] 新增、更新、删除写入安全审计。
- [ ] 日志不包含 JWT、密码、密钥和未脱敏敏感信息。

---

## 17. 与项目现状的落地差异

本文是目标 CRUD 规范。当前 PythonBase 已具备 `BaseSchema`、`SafeBigInt`、`SafeDatetime`、`ApiResponse`、`PageParams`、`PageData`、`BaseCrud`、`TenantAwareCrud`、事务 Session、JWT 和权限依赖，但正式落地前仍需处理：

1. 将现有列表接口逐步改为固定 `/page` POST 接口。
2. 在公共 API 层增加 `BaseRequestSchema`，用 Pydantic 拒绝请求中的未知字段。
3. 增加只接受十进制字符串并校验有符号 BIGINT 范围的 `SafeId` 请求类型。
4. 将 `PageParams.page_size` 最大值 `1000` 与 `BaseCrud` 最大值 `200` 统一为 `200`。
5. 统一公共层的 `sort_by/sort_order` 与接口层 `sorts` 多字段模型。
6. 给 `PageData` 增加 `total_pages`。
7. 注册 `RequestValidationError` 处理器，统一 FastAPI 422 响应。
8. 增加 Trace ID 中间件并确保异常响应也返回响应头。
9. 增加雪花 ID、固定审计字段、审计表和审计服务。
10. 将 JWT 的 `sub/tid` 序列化规范统一为字符串，并继续在解析后转换为 Python `int`。
11. 明确并统一数据库 Session、应用服务和 Celery 的时区配置。
12. 为普通业务资源提供可复用的分页过滤、排序白名单和 CRUD Service 模板。
13. 增加带请求指纹和唯一约束的新增幂等组件。
14. 新增一个完整示例模块验证本文所有约定。

这些变化应通过独立实施计划、数据库迁移和测试逐步完成，不应在没有兼容评估的情况下直接修改现有生产接口。
