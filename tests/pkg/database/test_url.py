"""数据库 URL、驱动映射和脱敏描述测试。"""

import pytest
from sqlalchemy.engine import URL

from pkg.config import DatabaseSettings, DatabaseType
from pkg.database.dialects import get_async_driver, get_async_drivername
from pkg.database.exceptions import UnsupportedDatabaseTypeError
from pkg.database.url import (
    build_async_database_url,
    build_connect_args,
    describe_database,
)


def test_mysql_and_postgresql_driver_mapping() -> None:
    """数据库类型应映射到对应的 SQLAlchemy 异步驱动。"""
    assert get_async_driver(DatabaseType.MYSQL) == "asyncmy"
    assert get_async_drivername(DatabaseType.MYSQL) == "mysql+asyncmy"
    assert get_async_driver(DatabaseType.POSTGRESQL) == "asyncpg"
    assert get_async_drivername(DatabaseType.POSTGRESQL) == "postgresql+asyncpg"


def test_unsupported_database_type_raises_database_error() -> None:
    """不支持的数据库类型应抛出数据库层异常。"""
    with pytest.raises(UnsupportedDatabaseTypeError):
        get_async_drivername("sqlite")  # type: ignore[arg-type]


def test_url_uses_sqlalchemy_url_create_and_preserves_secret_characters() -> None:
    """URL 构造不应因密码特殊字符产生转义错误。"""
    settings = DatabaseSettings(password="p@ss:word/with#chars")
    url = build_async_database_url(settings)

    assert isinstance(url, URL)
    assert url.drivername == "mysql+asyncmy"
    assert url.username == "root"
    assert url.password == "p@ss:word/with#chars"
    assert url.host == "127.0.0.1"
    assert url.port == 3306
    assert url.database == "pythonbase"


def test_postgresql_url_uses_asyncpg_and_default_port() -> None:
    """PostgreSQL 应使用 asyncpg 并继承配置层解析后的默认端口。"""
    settings = DatabaseSettings(type="postgresql", username="app", database="service")
    url = build_async_database_url(settings)

    assert url.drivername == "postgresql+asyncpg"
    assert url.port == 5432
    assert url.username == "app"
    assert url.database == "service"


def test_connect_args_follow_database_type() -> None:
    """connect_timeout 应转换为对应异步驱动的连接参数。"""
    assert build_connect_args(
        DatabaseSettings(type="mysql", connect_timeout=2.5)
    ) == {"connect_timeout": 2.5}
    assert build_connect_args(
        DatabaseSettings(type="postgresql", connect_timeout=3)
    ) == {"timeout": 3.0}


def test_description_does_not_include_password_or_username() -> None:
    """日志用连接描述不得包含用户名或密码。"""
    settings = DatabaseSettings(username="root", password="super-secret")
    description = describe_database(settings)

    assert description == "mysql://127.0.0.1:3306/pythonbase"
    assert "root" not in description
    assert "super-secret" not in description


def test_description_uses_explicit_port() -> None:
    """脱敏描述应展示最终活动端口。"""
    settings = DatabaseSettings(type="postgresql", port=15432, database="analytics")

    assert describe_database(settings) == "postgresql://127.0.0.1:15432/analytics"
