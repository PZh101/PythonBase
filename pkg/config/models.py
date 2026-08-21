"""不可变的强类型配置模型。"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatabaseType(StrEnum):
    """支持的数据库类型。"""

    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class FrozenSettings(BaseModel):
    """禁止修改和额外字段的配置模型基类。"""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
        hide_input_in_errors=True,
    )


class ProfileSettings(FrozenSettings):
    """应用 profile 配置。"""

    active: str = "default"


class AppSettings(FrozenSettings):
    """应用基础配置。"""

    name: str = "pythonbase"
    profile: ProfileSettings = Field(default_factory=ProfileSettings)


class LoggingSettings(FrozenSettings):
    """日志输出配置。"""

    level: str = "INFO"
    format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[logger_name]}</cyan> | "
        "<level>{message}</level>"
    )
    serialize: bool = False
    enqueue: bool = False
    backtrace: bool = False
    diagnose: bool = False

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        """日志级别应为非空文本并统一为大写。"""
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


class PoolSettings(FrozenSettings):
    """数据库连接池配置。"""

    size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    timeout: float = Field(default=30, gt=0, allow_inf_nan=False)
    recycle: int = Field(default=1800, ge=0)
    pre_ping: bool = True

    @field_validator("size", "max_overflow", "timeout", "recycle", mode="before")
    @classmethod
    def reject_boolean_numeric_values(cls, value: object) -> object:
        """拒绝将布尔值隐式转换为连接池数值。"""
        if isinstance(value, bool):
            raise ValueError("不能是布尔值")
        return value


class DatabaseSettings(FrozenSettings):
    """数据库连接和启动检查配置。"""

    type: DatabaseType = DatabaseType.MYSQL
    host: str = "127.0.0.1"
    port: int = Field(default=3306, ge=1, le=65535)
    username: str = "root"
    password: str = Field(default="", repr=False)
    database: str = "pythonbase"
    echo: bool = False
    connect_timeout: float = Field(default=10, gt=0, allow_inf_nan=False)
    startup_check: bool = True
    pool: PoolSettings = Field(default_factory=PoolSettings)

    @model_validator(mode="before")
    @classmethod
    def resolve_default_port(cls, value: object) -> object:
        """按原始数据库类型补全省略或为空的端口。"""
        if not isinstance(value, Mapping):
            return value

        data = dict(value)
        if data.get("port") is not None:
            return data

        raw_database_type = data.get("type", DatabaseType.MYSQL)
        try:
            database_type = DatabaseType(raw_database_type)
        except (TypeError, ValueError):
            database_type = DatabaseType.MYSQL
        data["port"] = 5432 if database_type is DatabaseType.POSTGRESQL else 3306
        return data

    @field_validator("host", "username", "database")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        """拒绝只包含空白字符的连接文本。"""
        if not value.strip():
            raise ValueError("不能为空")
        return value

    @field_validator("password", mode="before")
    @classmethod
    def normalize_password(cls, value: object) -> str:
        """将标量密码规范化为文本，并拒绝空值或复合结构。"""
        if value is None:
            raise ValueError("不能为空")
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("必须是标量")
        return str(value)

    @field_validator("port", "connect_timeout", mode="before")
    @classmethod
    def reject_boolean_numeric_values(cls, value: object) -> object:
        """拒绝将布尔值隐式转换为数据库数值。"""
        if isinstance(value, bool):
            raise ValueError("不能是布尔值")
        return value


class PasswordPolicySettings(FrozenSettings):
    """密码哈希与锁定策略配置。"""

    algorithm: str = "pbkdf2_sha256"
    iterations: int = Field(default=600_000, ge=1_000)
    max_failed_attempts: int = Field(default=5, ge=1)
    lock_duration_seconds: int = Field(default=900, ge=0)


class AuthMode(StrEnum):
    """请求认证模式：决定依赖哪个请求头解析主体。

    - ``HEADER``：从 ``X-User-Id`` / ``X-Tenant-Id`` 头读取，忽略 ``Authorization``。
    - ``JWT``：从 ``Authorization: Bearer <jwt>`` 头解析，忽略 X- 头。
    """

    HEADER = "header"
    JWT = "jwt"


class TokenSettings(FrozenSettings):
    """JWT 签发与生命周期配置。"""

    issuer: str = "pythonbase"
    secret: str = Field(default="", repr=False)
    algorithm: str = "HS256"
    access_token_ttl_seconds: int = Field(default=3600, ge=1)
    refresh_token_ttl_seconds: int = Field(default=86_400, ge=1)
    clock_skew_seconds: int = Field(default=30, ge=0)


class SecuritySettings(FrozenSettings):
    """认证安全总配置，聚合密码策略与 token 配置。"""

    password: PasswordPolicySettings = Field(default_factory=PasswordPolicySettings)
    token: TokenSettings = Field(default_factory=TokenSettings)
    enable_password_login: bool = False
    auth_mode: AuthMode = AuthMode.HEADER

    @model_validator(mode="after")
    def validate_security_requirements(self) -> "SecuritySettings":
        """校验认证相关字段的互斥与必填关系。

        - 启用密码登录时必须提供 token 签名密钥。
        - ``auth_mode=jwt`` 时必须提供 token 签名密钥。

        Raises:
            ValueError: 必填条件未满足。
        """
        secret_missing = not self.token.secret.strip()
        if self.enable_password_login and secret_missing:
            raise ValueError("启用密码登录时必须配置 security.token.secret")
        if self.auth_mode is AuthMode.JWT and secret_missing:
            raise ValueError("auth_mode=jwt 时必须配置 security.token.secret")
        return self


# ──────────────────────────────────────────────
# Celery 异步任务配置
# ──────────────────────────────────────────────

_CRON_FIELD_RANGES: tuple[tuple[int, int], ...] = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
_CRON_FIELD_NAMES: tuple[str, ...] = ("分", "时", "日", "月", "周")


class BeatScheduleItem(FrozenSettings):
    """单条定时任务定义（5 字段 cron：分 时 日 月 周）。"""

    task: str
    schedule: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        """定时任务名称不应为空。"""
        if not value.strip():
            raise ValueError("不能为空")
        return value

    @field_validator("schedule")
    @classmethod
    def validate_cron_schedule(cls, value: str) -> str:
        """cron 表达式应为 5 个空白分隔字段，且各字段在合法范围内。

        支持 ``*``、单值 ``5``、逗号列表 ``0,15,30``、范围 ``9-18``、
        步进 ``*/5``、范围步进 ``9-18/2``。
        """
        parts = value.split()
        if len(parts) != 5:
            raise ValueError("cron 表达式必须是 5 个字段：分 时 日 月 周")
        for part, (low, high), name in zip(parts, _CRON_FIELD_RANGES, _CRON_FIELD_NAMES):
            cls._validate_cron_field(part, low, high, name)
        return value

    @classmethod
    def _validate_cron_field(cls, part: str, low: int, high: int, name: str) -> None:
        """校验单个 cron 字段的语法与取值范围。"""
        for element in part.split(","):
            if element == "*":
                continue
            range_part, _, step_part = element.partition("/")
            if step_part and not step_part.isdigit():
                raise ValueError(f"{name} 字段步进必须为数字，收到: {step_part!r}")
            if range_part == "*":
                if not step_part:
                    raise ValueError(f"{name} 字段缺少步进值")
                continue
            if "-" in range_part:
                start_text, _, end_text = range_part.partition("-")
                try:
                    start, end = int(start_text), int(end_text)
                except ValueError as exc:
                    raise ValueError(f"{name} 字段范围必须为数字，收到: {range_part!r}") from exc
                if not (low <= start <= high and low <= end <= high):
                    raise ValueError(f"{name} 字段范围超出 {low}-{high}，收到: {range_part}")
                if start > end:
                    raise ValueError(f"{name} 字段范围起始大于结束，收到: {range_part}")
                continue
            try:
                number = int(range_part)
            except ValueError as exc:
                raise ValueError(f"{name} 字段必须为数字或 *，收到: {range_part!r}") from exc
            if not low <= number <= high:
                raise ValueError(f"{name} 字段超出范围 {low}-{high}，收到: {number}")


class BeatSettings(FrozenSettings):
    """定时调度（beat）开关与任务表。"""

    enabled: bool = False
    schedules: tuple[BeatScheduleItem, ...] = ()


class CelerySettings(FrozenSettings):
    """Celery worker 与调度配置。"""

    enabled: bool = True
    broker_url: str = "redis://127.0.0.1:6379/0"
    result_backend: str | None = "redis://127.0.0.1:6379/1"
    task_serializer: str = "json"
    timezone: str = "Asia/Shanghai"
    enable_utc: bool = False
    worker_pool: str | None = None
    worker_concurrency: int | None = Field(default=None, ge=1)
    worker_prefetch_multiplier: int = Field(default=1, ge=1)
    task_acks_late: bool = True
    task_reject_on_worker_lost: bool = True
    task_track_started: bool = True
    task_always_eager: bool = False
    task_eager_propagates: bool = False
    task_store_eager_result: bool = True
    broker_connection_retry_on_startup: bool = True
    result_expires_seconds: int = Field(default=86_400, ge=1)
    max_retries: int = Field(default=3, ge=0)
    retry_backoff: bool = True
    retry_backoff_max: int = Field(default=600, ge=1)
    retry_jitter: bool = True
    beat: BeatSettings = Field(default_factory=BeatSettings)
    include: list[str] = Field(default_factory=lambda: ["pkg.celery.tasks"])

    @field_validator("broker_url")
    @classmethod
    def validate_broker_url(cls, value: str) -> str:
        """broker 地址不应为空。"""
        if not value.strip():
            raise ValueError("不能为空")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """时区必须是 zoneinfo 支持的合法名称。"""
        if not value.strip():
            raise ValueError("不能为空")
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"未知时区: {value!r}") from exc
        return value

    @field_validator("result_backend", mode="before")
    @classmethod
    def normalize_result_backend(cls, value: object) -> object:
        """空字符串结果后端视为禁用（None）。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "worker_concurrency",
        "worker_prefetch_multiplier",
        "result_expires_seconds",
        "max_retries",
        "retry_backoff_max",
        mode="before",
    )
    @classmethod
    def reject_boolean_numeric_values(cls, value: object) -> object:
        """拒绝将布尔值隐式转换为 Celery 数值配置。"""
        if isinstance(value, bool):
            raise ValueError("不能是布尔值")
        return value


class RuntimeSettings(FrozenSettings):
    """运行时根配置，允许保留业务自定义的顶层配置段。"""

    model_config = ConfigDict(frozen=True, extra="allow", validate_default=True)

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
