"""FastAPI 应用工厂测试。"""

from pathlib import Path

import pytest

from app.web import create_app, load_runtime_settings
from pkg.config import DatabaseSettings, RuntimeSettings


def test_create_app_registers_app_routes() -> None:
    """应用工厂应集中注册当前 app 下的业务路由。"""
    settings = RuntimeSettings(database=DatabaseSettings(startup_check=False))

    app = create_app(settings=settings)

    paths = set(app.openapi()["paths"])
    assert "/system/users" in paths
    assert "/workspaces" in paths


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
