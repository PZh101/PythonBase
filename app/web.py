"""FastAPI 应用创建与业务路由集中注册。"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.system.routes import create_system_router
from app.workspace.routes import create_workspace_router
from pkg.common.exceptions import register_exception_handlers
from pkg.config import RuntimeSettings
from pkg.config.environment import get_environment_profile, parse_environment
from pkg.database import (
    AsyncDatabaseManager,
    create_db_session_dependency,
    create_manager,
)


def load_runtime_settings() -> RuntimeSettings:
    """从环境变量加载运行时配置。

    Returns:
        解析后的运行时配置。

    使用方式:
        在应用启动前调用，读取 `APP_` 前缀环境变量并构造 `RuntimeSettings`。
    """
    data = parse_environment()
    profile = get_environment_profile()
    if profile is not None:
        app_data = data.setdefault("app", {})
        if isinstance(app_data, dict):
            profile_data = app_data.setdefault("profile", {})
            if isinstance(profile_data, dict):
                profile_data["active"] = profile

    return RuntimeSettings.model_validate(data)


def register_routes(
    app: FastAPI,
    db_dependency: Callable[..., object],
) -> None:
    """集中注册 app 下的所有业务路由。

    Args:
        app: FastAPI 应用实例。
        db_dependency: 返回数据库会话的 FastAPI 依赖。

    使用方式:
        新增业务模块路由后，在本函数中调用 `app.include_router(...)` 完成统一注册。
    """
    app.include_router(create_system_router(db_dependency))
    app.include_router(create_workspace_router(db_dependency))


def create_app(
    *,
    settings: RuntimeSettings | None = None,
    database_manager: AsyncDatabaseManager | None = None,
) -> FastAPI:
    """创建并装配 FastAPI 应用。

    Args:
        settings: 运行时配置。不传时从环境变量加载。
        database_manager: 数据库管理器。不传时根据配置创建。

    Returns:
        已注册异常处理器和业务路由的 FastAPI 应用。

    使用方式:
        `main.py` 直接导入本函数创建应用；测试可传入自定义配置或数据库管理器。
    """
    runtime_settings = settings or load_runtime_settings()
    manager = database_manager or create_manager(runtime_settings.database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """管理数据库连接池生命周期。"""
        await manager.initialize()
        app.state.database = manager
        try:
            yield
        finally:
            await manager.dispose()

    app = FastAPI(title=runtime_settings.app.name, lifespan=lifespan)
    app.state.settings = runtime_settings
    app.state.database = manager

    register_exception_handlers(app)
    register_routes(app, create_db_session_dependency(manager))
    return app
