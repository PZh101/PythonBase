"""配置异常和强类型模型测试。"""

import pytest
from pydantic import Field, ValidationError

from pkg.config.exceptions import (
    ConfigAlreadyInitializedError,
    ConfigEnvironmentError,
    ConfigError,
    ConfigFileNotFoundError,
    ConfigKeyError,
    ConfigNotInitializedError,
    ConfigParseError,
    ConfigValidationError,
    InvalidProfileError,
    ProfileNotFoundError,
)
from pkg.config.models import (
    AppSettings,
    DatabaseSettings,
    DatabaseType,
    FrozenSettings,
    PoolSettings,
    ProfileSettings,
    RuntimeSettings,
)


@pytest.mark.parametrize(
    "exception_type",
    [
        ConfigFileNotFoundError,
        ConfigParseError,
        InvalidProfileError,
        ProfileNotFoundError,
        ConfigEnvironmentError,
        ConfigValidationError,
        ConfigKeyError,
        ConfigNotInitializedError,
        ConfigAlreadyInitializedError,
    ],
)
def test_config_exceptions_share_base_class(exception_type: type[ConfigError]) -> None:
    """所有配置异常都应继承 ConfigError。"""
    assert issubclass(exception_type, ConfigError)


def test_config_key_error_is_also_key_error() -> None:
    """ConfigKeyError 应同时支持按 KeyError 捕获。"""
    assert issubclass(ConfigKeyError, KeyError)


def test_database_defaults_to_mysql() -> None:
    """数据库配置应提供完整的 MySQL 默认值并解析默认端口。"""
    settings = DatabaseSettings()

    assert settings.type is DatabaseType.MYSQL
    assert settings.host == "127.0.0.1"
    assert settings.port == 3306
    assert settings.username == "root"
    assert settings.password == ""
    assert settings.database == "pythonbase"
    assert settings.echo is False
    assert settings.connect_timeout == 10
    assert settings.startup_check is True
    assert settings.pool == PoolSettings()


def test_postgresql_gets_default_port_after_type_is_known() -> None:
    """PostgreSQL 配置应在类型确定后使用 5432 默认端口。"""
    settings = DatabaseSettings(type="postgresql")

    assert settings.type is DatabaseType.POSTGRESQL
    assert settings.port == 5432


def test_explicit_port_is_preserved() -> None:
    """显式提供的合法端口不应被数据库类型默认值覆盖。"""
    settings = DatabaseSettings(type="postgresql", port=15432)

    assert settings.port == 15432


def test_numeric_password_is_normalized_to_text() -> None:
    """数字密码输入应规范化为文本。"""
    settings = DatabaseSettings(password=12345)

    assert settings.password == "12345"


def test_none_password_is_rejected() -> None:
    """None 密码应被拒绝。"""
    with pytest.raises(ValidationError):
        DatabaseSettings(password=None)


def test_non_scalar_password_is_rejected() -> None:
    """复合结构密码不应被转换为文本。"""
    with pytest.raises(ValidationError):
        DatabaseSettings(password=["secret"])


@pytest.mark.parametrize("field", ["host", "username", "database"])
def test_required_connection_text_cannot_be_blank(field: str) -> None:
    """主机、用户名和数据库名不应接受空白文本。"""
    with pytest.raises(ValidationError):
        DatabaseSettings(**{field: "   "})


@pytest.mark.parametrize("port", [0, 65536])
def test_invalid_ports_are_rejected(port: int) -> None:
    """数据库端口必须位于 1 到 65535 范围内。"""
    with pytest.raises(ValidationError):
        DatabaseSettings(port=port)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("size", 0),
        ("max_overflow", -1),
        ("timeout", 0),
        ("recycle", -1),
    ],
)
def test_invalid_pool_bounds_are_rejected(field: str, value: int) -> None:
    """连接池数值配置应遵守各自的下限。"""
    with pytest.raises(ValidationError):
        PoolSettings(**{field: value})


def test_application_defaults_include_default_profile() -> None:
    """应用配置应默认使用 pythonbase 名称和 default profile。"""
    settings = AppSettings()

    assert settings.name == "pythonbase"
    assert settings.profile == ProfileSettings(active="default")


def test_runtime_settings_use_default_sections() -> None:
    """运行时配置应默认创建应用和数据库配置。"""
    settings = RuntimeSettings()

    assert settings.app == AppSettings()
    assert settings.database == DatabaseSettings()


def test_runtime_settings_allow_extra_top_level_sections() -> None:
    """运行时配置应保留额外的顶层配置段。"""
    settings = RuntimeSettings(features={"enabled": True})

    assert settings.model_extra == {"features": {"enabled": True}}


def test_runtime_settings_are_frozen() -> None:
    """运行时配置创建后不应允许重新赋值。"""
    settings = RuntimeSettings()

    with pytest.raises(ValidationError):
        settings.database = DatabaseSettings(type="postgresql")


def test_known_settings_forbid_extra_fields() -> None:
    """已知配置模型应拒绝未声明字段。"""
    with pytest.raises(ValidationError):
        DatabaseSettings(unknown=True)


def test_frozen_settings_validate_default_values() -> None:
    """冻结配置基类应校验子类声明的默认值。"""

    class InvalidDefaultSettings(FrozenSettings):
        count: int = Field(default=0, ge=1)

    with pytest.raises(ValidationError):
        InvalidDefaultSettings()
