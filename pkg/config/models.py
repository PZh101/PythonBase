"""不可变的强类型配置模型。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatabaseType(StrEnum):
    """支持的数据库类型。"""

    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class FrozenSettings(BaseModel):
    """禁止修改和额外字段的配置模型基类。"""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


class ProfileSettings(FrozenSettings):
    """应用 profile 配置。"""

    active: str = "default"


class AppSettings(FrozenSettings):
    """应用基础配置。"""

    name: str = "pythonbase"
    profile: ProfileSettings = Field(default_factory=ProfileSettings)


class PoolSettings(FrozenSettings):
    """数据库连接池配置。"""

    size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    timeout: float = Field(default=30, gt=0)
    recycle: int = Field(default=1800, ge=0)
    pre_ping: bool = True


class DatabaseSettings(FrozenSettings):
    """数据库连接和启动检查配置。"""

    type: DatabaseType = DatabaseType.MYSQL
    host: str = "127.0.0.1"
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str = "root"
    password: str = ""
    database: str = "pythonbase"
    echo: bool = False
    connect_timeout: float = Field(default=10, gt=0)
    startup_check: bool = True
    pool: PoolSettings = Field(default_factory=PoolSettings)

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

    @model_validator(mode="after")
    def resolve_default_port(self) -> "DatabaseSettings":
        """按最终数据库类型补全未指定的端口。"""
        if self.port is None:
            port = 3306 if self.type is DatabaseType.MYSQL else 5432
            object.__setattr__(self, "port", port)
        return self


class RuntimeSettings(FrozenSettings):
    """运行时根配置，允许保留业务自定义的顶层配置段。"""

    model_config = ConfigDict(frozen=True, extra="allow", validate_default=True)

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
