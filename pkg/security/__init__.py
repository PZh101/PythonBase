"""安全上下文、权限校验和 FastAPI 依赖。"""

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.dependencies import (
    create_auth_context_dependency,
    require_any_permission,
    require_permission,
    require_role,
    require_tenant,
)
from pkg.security.exceptions import (
    AuthenticationRequiredException,
    InvalidCredentialException,
    PermissionDeniedException,
    TenantAccessDeniedException,
    TenantRequiredException,
)
from pkg.security.permissions import ensure_any_permission, ensure_permission, ensure_role, ensure_tenant
from pkg.security.providers import AuthContextProvider

__all__ = [
    "AuthContext",
    "AuthContextProvider",
    "AuthenticationRequiredException",
    "InvalidCredentialException",
    "PermissionDeniedException",
    "PermissionSet",
    "Principal",
    "TenantAccessDeniedException",
    "TenantRequiredException",
    "create_auth_context_dependency",
    "ensure_any_permission",
    "ensure_permission",
    "ensure_role",
    "ensure_tenant",
    "require_any_permission",
    "require_permission",
    "require_role",
    "require_tenant",
]
