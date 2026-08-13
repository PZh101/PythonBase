"""安全上下文、权限校验和 FastAPI 依赖。"""
from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.dependencies import (
    create_auth_context_dependency,
    extract_principal_from_request,
    get_current_auth_context,
    require_any_permission,
    require_permission,
    require_role,
    require_tenant,
)
from pkg.security.exceptions import (
    AuthenticationRequiredException,
    InvalidCredentialException,
    InvalidTokenException,
    PermissionDeniedException,
    TenantAccessDeniedException,
    TenantRequiredException,
)
from pkg.security.permissions import ensure_any_permission, ensure_permission, ensure_role, ensure_tenant
from pkg.security.providers import AuthContextProvider
from pkg.security.token import (
    AccessTokenPayload,
    JwtTokenResolver,
    PasswordHasher,
    TokenResolver,
    TokenService,
    extract_bearer_token,
)

__all__ = [
    "AccessTokenPayload",
    "AuthContext",
    "AuthContextProvider",
    "AuthenticationRequiredException",
    "InvalidCredentialException",
    "InvalidTokenException",
    "JwtTokenResolver",
    "PasswordHasher",
    "PermissionDeniedException",
    "PermissionSet",
    "Principal",
    "TenantAccessDeniedException",
    "TenantRequiredException",
    "TokenResolver",
    "TokenService",
    "create_auth_context_dependency",
    "ensure_any_permission",
    "ensure_permission",
    "ensure_role",
    "ensure_tenant",
    "extract_bearer_token",
    "extract_principal_from_request",
    "get_current_auth_context",
    "require_any_permission",
    "require_permission",
    "require_role",
    "require_tenant",
]
