"""不可变的强类型配置模型。"""

from collections.abc import Mapping
from enum import StrEnum

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


class RuntimeSettings(FrozenSettings):
    """运行时根配置，允许保留业务自定义的顶层配置段。"""

    model_config = ConfigDict(frozen=True, extra="allow", validate_default=True)

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
