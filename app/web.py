"""FastAPI 应用创建与业务路由集中注册。"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.auth_routes import create_iam_auth_router
from app.iam.repository import IamRepository
from app.iam.routes import create_iam_router
from app.iam.service import IamAuthContextService
from app.system.routes import create_system_router
from app.workspace.routes import create_workspace_router
from pkg.common.exceptions import register_exception_handlers
from pkg.common.logging import configure_logging, get_logger
from pkg.config import AuthMode, RuntimeSettings
from pkg.config.loader import load_configuration
from pkg.database import (
    AsyncDatabaseManager,
    create_db_session_dependency,
    create_manager,
)
from pkg.security import (
    AuthContext,
    JwtTokenResolver,
    TokenResolver,
    TokenService,
    extract_principal_from_request,
)


def load_runtime_settings() -> RuntimeSettings:
    """从配置文件和环境变量加载运行时配置。

    Returns:
        解析后的运行时配置。

    使用方式:
        在应用启动前调用，读取 `application.yml`、profile 配置和 `APP_` 环境变量。
    """
    loaded = load_configuration(".")
    return RuntimeSettings.model_validate(loaded.data)


def create_token_service(settings: RuntimeSettings) -> TokenService | None:
    """根据配置构造 token 服务。

    启用以下任一条件时返回 :class:`TokenService`：

    - ``security.enable_password_login=True``：需要签发登录 token。
    - ``security.auth_mode=jwt``：需要校验请求中的 Bearer token。

    两者均关闭时返回 ``None``。
    """
    security = settings.security
    if not (security.enable_password_login or security.auth_mode is AuthMode.JWT):
        return None
    return TokenService(security.token)


def create_token_resolver(token_service: TokenService | None) -> JwtTokenResolver | None:
    """根据 token 服务构造 resolver，未启用 token 时返回 None。"""
    if token_service is None:
        return None
    return JwtTokenResolver(token_service)


def create_auth_dependency(
    db_dependency: Callable[..., object],
    *,
    auth_mode: AuthMode,
    token_resolver: TokenResolver | None = None,
) -> Callable[..., object]:
    """创建基于 IAM 的认证上下文 FastAPI 依赖。

    解析路径由 :class:`AuthMode` **严格** 决定：

    - ``AuthMode.HEADER``：从 ``X-User-Id`` / ``X-Tenant-Id`` 头解析；忽略 ``Authorization``。
    - ``AuthMode.JWT``：从 ``Authorization: Bearer <token>`` 头解析；忽略 X- 头；
      此时 ``token_resolver`` 必须提供。

    Args:
        db_dependency: 返回 ``AsyncSession`` 的 FastAPI 依赖。
        auth_mode: 认证模式，决定走哪条解析路径。
        token_resolver: 仅 ``AuthMode.JWT`` 时需要。

    Returns:
        返回 :class:`AuthContext` 的 FastAPI 依赖函数。
    """

    async def get_auth_context(
        request: Request,
        db: Annotated[AsyncSession, Depends(db_dependency)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        auth_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
        auth_tenant_id: Annotated[int | None, Header(alias="X-Tenant-Id")] = None,
    ) -> AuthContext:
        """从请求头中读取主体并加载认证上下文。"""
        user_id, tenant_id = extract_principal_from_request(
            auth_mode=auth_mode,
            authorization=authorization,
            auth_user_id=auth_user_id,
            auth_tenant_id=auth_tenant_id,
            token_resolver=token_resolver,
        )

        provider = IamAuthContextService(IamRepository(db))
        context = await provider.load_context(user_id=user_id, tenant_id=tenant_id)
        request.state.auth_context = context
        return context

    return get_auth_context


def register_routes(
    app: FastAPI,
    db_dependency: Callable[..., object],
    token_service: TokenService | None,
    token_resolver: JwtTokenResolver | None,
    settings: RuntimeSettings,
) -> None:
    """集中注册 app 下的所有业务路由。

    Args:
        app: FastAPI 应用实例。
        db_dependency: 返回数据库会话的 FastAPI 依赖。
        token_service: token 服务（可为 None）。
        token_resolver: token 解析器（可为 None）。
        settings: 运行时配置，用于将 SecuritySettings 注入到 auth 路由。

    使用方式:
        新增业务模块路由后，在本函数中调用 ``app.include_router(...)`` 完成统一注册。
    """
    auth_dependency = create_auth_dependency(
        db_dependency,
        auth_mode=settings.security.auth_mode,
        token_resolver=token_resolver,
    )
    app.include_router(create_system_router(db_dependency, auth_dependency))
    app.include_router(create_workspace_router(db_dependency, auth_dependency))
    app.include_router(create_iam_router(db_dependency, auth_dependency))

    if settings.security.enable_password_login and token_service is not None:
        app.include_router(
            create_iam_auth_router(
                db_dependency=db_dependency,
                auth_dependency=auth_dependency,
                security_settings=settings.security,
                token_service=token_service,
            )
        )


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
    token_service = create_token_service(runtime_settings)
    token_resolver = create_token_resolver(token_service)

    # 防御性检查：Pydantic 校验已保证 jwt 模式下 secret 必填，这里再兜底。
    if runtime_settings.security.auth_mode is AuthMode.JWT and token_resolver is None:
        raise RuntimeError(
            "auth_mode=jwt 必须构造 token_resolver (检查 security.token.secret 是否已配置)"
        )

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
    if token_service is not None:
        app.state.token_service = token_service

    register_exception_handlers(app)
    register_routes(
        app,
        create_db_session_dependency(manager),
        token_service=token_service,
        token_resolver=token_resolver,
        settings=runtime_settings,
    )
    return app
