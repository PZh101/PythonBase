"""FastAPI 应用创建与业务路由集中注册。"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.repository import IamRepository
from app.iam.routes import create_iam_router
from app.iam.service import IamAuthContextService
from app.system.routes import create_system_router
from app.workspace.routes import create_workspace_router
from pkg.common.exceptions import register_exception_handlers
from pkg.common.logging import configure_logging, get_logger
from pkg.config import RuntimeSettings
from pkg.config.loader import load_configuration
from pkg.database import (
    AsyncDatabaseManager,
    create_db_session_dependency,
    create_manager,
)
from pkg.security.context import AuthContext
from pkg.security.exceptions import AuthenticationRequiredException


def load_runtime_settings() -> RuntimeSettings:
    """从配置文件和环境变量加载运行时配置。

    Returns:
        解析后的运行时配置。

    使用方式:
        在应用启动前调用，读取 `application.yml`、profile 配置和 `APP_` 环境变量。
    """
    loaded = load_configuration(".")
    return RuntimeSettings.model_validate(loaded.data)


def create_auth_dependency(db_dependency: Callable[..., object]) -> Callable[..., object]:
    """创建基于 IAM 的认证上下文 FastAPI 依赖。

    从请求头中读取 ``X-User-Id`` 和 ``X-Tenant-Id``，加载用户的认证上下文，
    并将结果保存在 ``request.state.auth_context`` 中供后续依赖使用。

    Args:
        db_dependency: 返回 ``AsyncSession`` 的 FastAPI 依赖。

    Returns:
        返回 ``AuthContext`` 的 FastAPI 依赖函数。
    """

    async def get_auth_context(
        request: Request,
        db: Annotated[AsyncSession, Depends(db_dependency)],
        auth_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
        auth_tenant_id: Annotated[int | None, Header(alias="X-Tenant-Id")] = None,
    ) -> AuthContext:
        """从请求头读取用户和租户，通过 IAM 服务加载认证上下文。"""
        if auth_user_id is None:
            raise AuthenticationRequiredException()
        provider = IamAuthContextService(IamRepository(db))
        context = await provider.load_context(user_id=auth_user_id, tenant_id=auth_tenant_id)
        request.state.auth_context = context
        return context

    return get_auth_context


def register_routes(
    app: FastAPI,
    db_dependency: Callable[..., object],
) -> None:
    """集中注册 app 下的所有业务路由。

    Args:
        app: FastAPI 应用实例。
        db_dependency: 返回数据库会话的 FastAPI 依赖。

    使用方式:
        新增业务模块路由后，在本函数中调用 ``app.include_router(...)`` 完成统一注册。
    """
    auth_dependency = create_auth_dependency(db_dependency)
    app.include_router(create_system_router(db_dependency, auth_dependency))
    app.include_router(create_workspace_router(db_dependency, auth_dependency))
    app.include_router(create_iam_router(db_dependency, auth_dependency))


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
        ``main.py`` 直接导入本函数创建应用；测试可传入自定义配置或数据库管理器。
    """
    runtime_settings = settings or load_runtime_settings()
    configure_logging(runtime_settings.logging)
    logger = get_logger(__name__)
    manager = database_manager or create_manager(runtime_settings.database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """管理数据库连接池生命周期。"""
        logger.info("正在初始化数据库连接池")
        await manager.initialize()
        app.state.database = manager
        logger.info("数据库连接池初始化完成")
        try:
            yield
        finally:
            logger.info("正在释放数据库连接池")
            await manager.dispose()
            logger.info("数据库连接池已释放")

    app = FastAPI(title=runtime_settings.app.name, lifespan=lifespan)
    app.state.settings = runtime_settings
    app.state.database = manager

    register_exception_handlers(app)
    register_routes(app, create_db_session_dependency(manager))
    return app
