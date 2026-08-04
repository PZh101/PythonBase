"""安全上下文 Provider 协议。"""

from typing import Protocol

from pkg.security.context import AuthContext


class AuthContextProvider(Protocol):
    """由应用层实现的认证上下文加载协议。"""

    async def load_context(self, *, user_id: int, tenant_id: int | None) -> AuthContext:
        """按用户和租户加载请求上下文。"""
