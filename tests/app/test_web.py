"""FastAPI 应用工厂测试。"""

from app.web import create_app
from pkg.config import DatabaseSettings, RuntimeSettings


def test_create_app_registers_app_routes() -> None:
    """应用工厂应集中注册当前 app 下的业务路由。"""
    settings = RuntimeSettings(database=DatabaseSettings(startup_check=False))

    app = create_app(settings=settings)

    paths = set(app.openapi()["paths"])
    assert "/system/users" in paths
    assert "/workspaces" in paths
