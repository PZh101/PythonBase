"""FastAPI 应用工厂测试。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.web import create_app, load_runtime_settings
from pkg.config import (
    AuthMode,
    DatabaseSettings,
    RuntimeSettings,
    SecuritySettings,
    TokenSettings,
)


def test_create_app_registers_app_routes() -> None:
    """应用工厂应集中注册当前 app 下的业务路由。"""
    settings = RuntimeSettings(database=DatabaseSettings(startup_check=False))

    app = create_app(settings=settings)

    paths = set(app.openapi()["paths"])
    assert "/system/users" in paths
    assert "/workspaces" in paths


def test_create_app_with_jwt_mode_constructs_token_service() -> None:
    """auth_mode=jwt 时应构造 token_service（即便 enable_password_login=False）。"""
    settings = RuntimeSettings(
        database=DatabaseSettings(startup_check=False),
        security=SecuritySettings(
            auth_mode=AuthMode.JWT,
            token=TokenSettings(secret="x" * 32),
        ),
    )

    app = create_app(settings=settings)

    assert app.state.token_service is not None


def test_create_app_with_header_mode_skips_token_service() -> None:
    """默认 header 模式且未启用密码登录时不应构造 token_service。"""
    settings = RuntimeSettings(
        database=DatabaseSettings(startup_check=False),
        security=SecuritySettings(),  # 默认 auth_mode=header
    )

    app = create_app(settings=settings)

    assert not hasattr(app.state, "token_service")


def test_runtime_settings_reject_jwt_mode_without_secret() -> None:
    """RuntimeSettings 在 auth_mode=jwt 但 secret 缺失时应抛 ValidationError。"""
    with pytest.raises(ValidationError) as exc_info:
        RuntimeSettings(
            database=DatabaseSettings(startup_check=False),
            security=SecuritySettings(auth_mode=AuthMode.JWT),
        )

    assert "auth_mode=jwt" in str(exc_info.value)


def test_load_runtime_settings_reads_application_yml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行时配置应读取 application.yml 并合并为强类型配置。"""
    (tmp_path / "application.yml").write_text(
        """
app:
  name: yaml-app
database:
  password: "123456"
  startup_check: false
logging:
  level: debug
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = load_runtime_settings()

    assert settings.app.name == "yaml-app"
    assert settings.database.password == "123456"
    assert settings.database.startup_check is False
    assert settings.logging.level == "DEBUG"
