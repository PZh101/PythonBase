"""JWT 签发、解析与密码哈希工具。

本模块不引入第三方依赖：

- JWT 走 HS256（HMAC-SHA256），仅使用标准库 ``hmac`` / ``hashlib`` / ``secrets``。
- 密码哈希走 PBKDF2-HMAC-SHA256，存储格式 ``pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>``。

为什么不用 bcrypt / passlib：
- 项目当前依赖只有标准库 + FastAPI / SQLAlchemy 等，避免新增 C 扩展依赖。
- PBKDF2-HMAC-SHA256 是 FIPS 认可、Python 标准库原生支持的算法，
  在足够迭代次数（OWASP 2023 推荐 600000）下安全性可与 bcrypt 持平。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Final, Protocol

from pkg.config import PasswordPolicySettings, TokenSettings
from pkg.security.exceptions import (
    AuthenticationRequiredException,
    InvalidCredentialException,
    InvalidTokenException,
)

# ──────────────────────────────────────────────
# 密码哈希（PBKDF2-HMAC-SHA256）
# ──────────────────────────────────────────────

_PASSWORD_HASH_PREFIX: Final = "pbkdf2_sha256"
_PASSWORD_HASH_SEPARATOR: Final = "$"
_HASH_KEY_LENGTH: Final = 32  # 256 bit
_SALT_BYTES: Final = 16


class PasswordHasher:
    """基于 PBKDF2-HMAC-SHA256 的密码哈希器。

    Args:
        policy: 密码策略，至少提供迭代次数。
    """

    def __init__(self, policy: PasswordPolicySettings) -> None:
        if policy.algorithm != _PASSWORD_HASH_PREFIX:
            raise ValueError(
                f"不支持的密码哈希算法: {policy.algorithm}, 当前仅支持 {_PASSWORD_HASH_PREFIX}"
            )
        self._iterations = policy.iterations

    def hash(self, password: str) -> str:
        """对明文密码进行哈希，返回可持久化字符串。

        Args:
            password: 明文密码。

        Returns:
            形如 ``pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>`` 的字符串。
        """
        if not password:
            raise ValueError("密码不能为空")
        salt = secrets.token_bytes(_SALT_BYTES)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self._iterations,
            dklen=_HASH_KEY_LENGTH,
        )
        return _PASSWORD_HASH_SEPARATOR.join([
            _PASSWORD_HASH_PREFIX,
            str(self._iterations),
            salt.hex(),
            derived.hex(),
        ])

    def verify(self, password: str, encoded: str) -> bool:
        """校验明文密码与已存储哈希是否匹配。

        Args:
            password: 待校验明文。
            encoded: 数据库中存储的哈希字符串。

        Returns:
            匹配返回 ``True``，否则 ``False``；格式非法时返回 ``False``。
        """
        parts = encoded.split(_PASSWORD_HASH_SEPARATOR)
        if len(parts) != 4 or parts[0] != _PASSWORD_HASH_PREFIX:
            return False
        try:
            iterations = int(parts[1])
            salt = bytes.fromhex(parts[2])
            expected = bytes.fromhex(parts[3])
        except ValueError:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)


# ──────────────────────────────────────────────
# JWT（HS256，零三方依赖）
# ──────────────────────────────────────────────


def _b64url_encode(raw: bytes) -> str:
    """按 JWT 规范进行 base64url 编码（去 padding）。"""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """按 JWT 规范进行 base64url 解码（补回 padding）。"""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


@dataclass(frozen=True, slots=True)
class AccessTokenPayload:
    """解析后的访问令牌载荷。"""

    user_id: int
    tenant_id: int | None
    token_version: int
    issued_at: int
    expires_at: int
    token_type: str

    @property
    def is_expired(self) -> bool:
        """返回当前时钟下 token 是否已过期。"""
        return time.time() >= self.expires_at


class TokenService:
    """HS256 JWT 签发与解析。

    Args:
        settings: token 配置，必须包含 ``secret`` 与 ``algorithm``。
    """

    def __init__(self, settings: TokenSettings) -> None:
        if settings.algorithm != "HS256":
            raise ValueError(f"当前仅支持 HS256 算法, 收到: {settings.algorithm}")
        if not settings.secret:
            raise ValueError("token 配置缺少 secret")
        self._settings = settings
        self._signing_key = settings.secret.encode("utf-8")

    @property
    def settings(self) -> TokenSettings:
        """返回当前生效的 token 配置。"""
        return self._settings

    def issue_access_token(
        self,
        *,
        user_id: int,
        token_version: int,
        tenant_id: int | None = None,
    ) -> str:
        """签发访问令牌。

        Args:
            user_id: 用户 ID。
            token_version: 用户凭证版本号（用于登出/重置密码后吊销历史 token）。
            tenant_id: 当前租户 ID，可为空（仅主体身份）。

        Returns:
            紧凑序列化后的 JWT 字符串。
        """
        now = int(time.time())
        ttl = self._settings.access_token_ttl_seconds
        header = {"alg": "HS256", "typ": "JWT"}
        payload: dict[str, Any] = {
            "iss": self._settings.issuer,
            "sub": str(user_id),
            "tid": tenant_id,
            "ver": token_version,
            "type": "access",
            "iat": now,
            "exp": now + ttl,
            "jti": secrets.token_hex(8),
        }
        return self._encode(header, payload)

    def issue_refresh_token(self, *, user_id: int, token_version: int) -> str:
        """签发刷新令牌（仅持有 user_id，租户在刷新时再确定）。"""
        now = int(time.time())
        ttl = self._settings.refresh_token_ttl_seconds
        header = {"alg": "HS256", "typ": "JWT"}
        payload: dict[str, Any] = {
            "iss": self._settings.issuer,
            "sub": str(user_id),
            "ver": token_version,
            "type": "refresh",
            "iat": now,
            "exp": now + ttl,
            "jti": secrets.token_hex(8),
        }
        return self._encode(header, payload)

    def decode(self, token: str, *, expected_type: str | None = None) -> AccessTokenPayload:
        """解析并校验 JWT 签名与有效期。

        Args:
            token: 待解析的 JWT 字符串。
            expected_type: 期望的 ``type`` 声明（如 ``"access"`` / ``"refresh"``）。

        Returns:
            解析后的载荷。

        Raises:
            InvalidTokenException: 签名错误、格式非法、过期、类型不匹配。
        """
        if not token:
            raise InvalidTokenException("token 不能为空")
        try:
            header_b64, payload_b64, signature_b64 = token.split(".")
        except ValueError as exc:
            raise InvalidTokenException("token 格式非法") from exc

        try:
            header = json.loads(_b64url_decode(header_b64))
            payload = json.loads(_b64url_decode(payload_b64))
            signature = _b64url_decode(signature_b64)
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidTokenException("token 内容解析失败") from exc

        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise InvalidTokenException("token 头信息不被支持")

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(self._signing_key, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, signature):
            raise InvalidTokenException("token 签名校验失败")

        now = int(time.time())
        skew = self._settings.clock_skew_seconds
        exp = int(payload.get("exp", 0))
        if now > exp + skew:
            raise InvalidTokenException("token 已过期")

        if expected_type is not None and payload.get("type") != expected_type:
            raise InvalidTokenException(f"token 类型不匹配, 期望 {expected_type}")

        try:
            return AccessTokenPayload(
                user_id=int(payload["sub"]),
                tenant_id=payload.get("tid"),
                token_version=int(payload.get("ver", 0)),
                issued_at=int(payload.get("iat", 0)),
                expires_at=exp,
                token_type=str(payload.get("type", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidTokenException("token 字段缺失或类型错误") from exc

    def _encode(self, header: dict[str, Any], payload: dict[str, Any]) -> str:
        """编码并签名 JWT。"""
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(self._signing_key, signing_input, hashlib.sha256).digest()
        return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


# ──────────────────────────────────────────────
# Token Resolver：从请求头中提取 (user_id, tenant_id, token_version)
# ──────────────────────────────────────────────


class TokenResolver(Protocol):
    """从 ``Authorization: Bearer <token>`` 中解析当前主体的协议。"""

    def resolve(self, token: str) -> tuple[int, int | None, int]:
        """解析 token 并返回 ``(user_id, tenant_id, token_version)``。

        Raises:
            InvalidCredentialException: token 无效或已过期。
        """


class JwtTokenResolver:
    """基于 :class:`TokenService` 的 Token Resolver 实现。"""

    def __init__(self, token_service: TokenService) -> None:
        self._token_service = token_service

    def resolve(self, token: str) -> tuple[int, int | None, int]:
        """解析访问 token，返回主体三元组。"""
        try:
            payload = self._token_service.decode(token, expected_type="access")
        except InvalidTokenException as exc:
            raise InvalidCredentialException(str(exc.msg)) from exc
        return payload.user_id, payload.tenant_id, payload.token_version


# ──────────────────────────────────────────────
# Bearer 头解析工具
# ──────────────────────────────────────────────

_BEARER_PREFIX: Final = "Bearer "


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """从 ``Authorization`` 头中提取 Bearer token。

    Args:
        authorization_header: 原始头内容，可能为 ``None``。

    Returns:
        解析出的 token 字符串，若缺失或格式非法则返回 ``None``。
    """
    if not authorization_header:
        return None
    header = authorization_header.strip()
    if not header.lower().startswith(_BEARER_PREFIX.lower()):
        return None
    token = header[len(_BEARER_PREFIX):].strip()
    return token or None


__all__ = [
    "AccessTokenPayload",
    "JwtTokenResolver",
    "PasswordHasher",
    "TokenResolver",
    "TokenService",
    "extract_bearer_token",
]
