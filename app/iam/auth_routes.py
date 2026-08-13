"""IAM 认证 API 路由：登录、刷新、登出、改密。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.auth_service import IamAuthService, TokenPair
from app.iam.repository import IamRepository
from app.iam.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from pkg.common.api import ApiResponse
from pkg.config import SecuritySettings
from pkg.security import PasswordHasher, TokenService, get_current_auth_context
from pkg.security.context import AuthContext


def _to_token_response(pair: TokenPair) -> TokenResponse:
    """将 :class:`TokenPair` 转换为响应模型。"""
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        access_expires_in=pair.access_expires_in,
        refresh_expires_in=pair.refresh_expires_in,
        user_id=pair.user_id,
        username=pair.username,
        token_version=pair.token_version,
    )


def create_iam_auth_router(
    db_dependency: Callable[..., object],
    auth_dependency: Callable[..., object],
    security_settings: SecuritySettings,
    token_service: TokenService,
) -> APIRouter:
    """创建 IAM 认证路由。

    包含：

    - ``POST /iam/auth/login``：账号密码登录（无需认证）
    - ``POST /iam/auth/refresh``：刷新访问令牌（无需认证，靠 refresh token 自证）
    - ``POST /iam/auth/logout``：登出当前用户（需认证）
    - ``POST /iam/auth/password``：修改当前用户密码（需认证）

    Args:
        db_dependency: 返回 ``AsyncSession`` 的 FastAPI 依赖。
        auth_dependency: 返回 ``AuthContext`` 的 FastAPI 认证依赖。
        security_settings: 认证安全配置。
        token_service: 已构造好的 token 服务（仅用于校验 secret 一致性）。

    Returns:
        已绑定依赖的 :class:`APIRouter`。
    """
    router = APIRouter(prefix="/iam/auth", tags=["IAM 登录认证"])

    if not security_settings.enable_password_login:
        # 不启用密码登录时，仅返回空路由集合。
        return router

    password_hasher = PasswordHasher(security_settings.password)
    _ = token_service  # 当前路由不直接使用，但保留以备未来扩展

    def get_auth_service(db: Annotated[AsyncSession, Depends(db_dependency)]) -> IamAuthService:
        """构造 IAM 认证服务。"""
        return IamAuthService(
            repository=IamRepository(db),
            password_hasher=password_hasher,
            token_service=token_service,
            password_policy=security_settings.password,
            token_settings=security_settings.token,
        )

    @router.post("/login", response_model=ApiResponse[TokenResponse])
    async def login(
        body: LoginRequest,
        service: Annotated[IamAuthService, Depends(get_auth_service)],
    ) -> ApiResponse[TokenResponse]:
        """账号密码登录。"""
        pair = await service.login(username=body.username, password=body.password)
        return ApiResponse(data=_to_token_response(pair))

    @router.post("/refresh", response_model=ApiResponse[TokenResponse])
    async def refresh_token(
        body: RefreshTokenRequest,
        service: Annotated[IamAuthService, Depends(get_auth_service)],
    ) -> ApiResponse[TokenResponse]:
        """使用刷新令牌换取新的访问令牌。"""
        pair = await service.refresh(refresh_token=body.refresh_token)
        return ApiResponse(data=_to_token_response(pair))

    @router.post(
        "/logout",
        response_model=ApiResponse[None],
        dependencies=[Depends(auth_dependency)],
    )
    async def logout(
        context: Annotated[AuthContext, Depends(get_current_auth_context)],
        service: Annotated[IamAuthService, Depends(get_auth_service)],
    ) -> ApiResponse[None]:
        """登出当前用户，使历史 token 全部失效。"""
        await service.logout(user_id=context.principal.user_id)
        return ApiResponse(data=None)

    @router.post(
        "/password",
        response_model=ApiResponse[TokenResponse],
        dependencies=[Depends(auth_dependency)],
    )
    async def change_password(
        body: ChangePasswordRequest,
        context: Annotated[AuthContext, Depends(get_current_auth_context)],
        service: Annotated[IamAuthService, Depends(get_auth_service)],
    ) -> ApiResponse[TokenResponse]:
        """修改当前用户密码并重新签发 token。"""
        pair = await service.change_password(
            user_id=context.principal.user_id,
            old_password=body.old_password,
            new_password=body.new_password,
        )
        return ApiResponse(data=_to_token_response(pair))

    return router


__all__ = ["create_iam_auth_router"]
