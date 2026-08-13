"""TokenService 单元测试。"""

import time

import pytest

from pkg.config import TokenSettings
from pkg.security import TokenService
from pkg.security.exceptions import InvalidTokenException


def _settings(**overrides) -> TokenSettings:
    """构造测试用 token 配置。"""
    base = {
        "secret": "test-secret-must-be-long-enough-for-hmac-32-bytes-ok",
        "access_token_ttl_seconds": 60,
        "refresh_token_ttl_seconds": 3600,
        "clock_skew_seconds": 5,
    }
    base.update(overrides)
    return TokenSettings(**base)


def test_issue_and_decode_access_token_roundtrip() -> None:
    """签发后应能解析出原始主体三元组。"""
    service = TokenService(_settings())
    token = service.issue_access_token(user_id=42, token_version=3, tenant_id=7)

    payload = service.decode(token, expected_type="access")

    assert payload.user_id == 42
    assert payload.tenant_id == 7
    assert payload.token_version == 3
    assert payload.token_type == "access"
    assert payload.expires_at - payload.issued_at == 60


def test_decode_without_tenant_returns_none() -> None:
    """签发时不带 tenant_id，解析后 tenant_id 应为 None。"""
    service = TokenService(_settings())
    token = service.issue_access_token(user_id=1, token_version=0)

    payload = service.decode(token)

    assert payload.tenant_id is None


def test_decode_rejects_wrong_type() -> None:
    """期望 access 但拿到 refresh 时应报错。"""
    service = TokenService(_settings())
    refresh = service.issue_refresh_token(user_id=1, token_version=0)

    with pytest.raises(InvalidTokenException):
        service.decode(refresh, expected_type="access")


def test_decode_rejects_expired_token_with_clock_skew() -> None:
    """过期时间超出 clock_skew 应被拒绝。"""
    service = TokenService(_settings(access_token_ttl_seconds=1, clock_skew_seconds=0))
    token = service.issue_access_token(user_id=1, token_version=0)

    # 等待 2.5 秒以确保 int(time.time()) 跨过 exp 边界，避免秒级精度问题。
    time.sleep(2.5)

    with pytest.raises(InvalidTokenException):
        service.decode(token)


def test_decode_rejects_tampered_signature() -> None:
    """篡改签名后应解析失败。"""
    service = TokenService(_settings())
    token = service.issue_access_token(user_id=1, token_version=0)
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")

    with pytest.raises(InvalidTokenException):
        service.decode(tampered)


def test_decode_rejects_empty_token() -> None:
    """空 token 应直接抛错。"""
    service = TokenService(_settings())
    with pytest.raises(InvalidTokenException):
        service.decode("")


def test_decode_rejects_malformed_token() -> None:
    """段数不对的 token 应抛错。"""
    service = TokenService(_settings())
    with pytest.raises(InvalidTokenException):
        service.decode("not-a-jwt")


def test_decode_rejects_token_signed_with_different_secret() -> None:
    """不同 secret 签发的 token 不能被当前 service 解析。"""
    issuer = TokenService(_settings(secret="issuer-secret-1"))
    token = issuer.issue_access_token(user_id=1, token_version=0)

    verifier = TokenService(_settings(secret="verifier-secret-2"))

    with pytest.raises(InvalidTokenException):
        verifier.decode(token)


def test_refresh_token_can_be_distinguished_by_type() -> None:
    """refresh 与 access 应可通过 type 字段区分。"""
    service = TokenService(_settings())
    access = service.issue_access_token(user_id=1, token_version=0)
    refresh = service.issue_refresh_token(user_id=1, token_version=0)

    access_payload = service.decode(access, expected_type="access")
    refresh_payload = service.decode(refresh, expected_type="refresh")

    assert access_payload.token_type == "access"
    assert refresh_payload.token_type == "refresh"


def test_token_service_rejects_empty_secret() -> None:
    """secret 为空时构造 TokenService 应抛 ValueError。"""
    with pytest.raises(ValueError):
        TokenService(_settings(secret=""))


def test_token_service_rejects_non_hs256_algorithm() -> None:
    """非 HS256 算法应抛 ValueError。"""
    with pytest.raises(ValueError):
        TokenService(_settings(algorithm="RS256"))
