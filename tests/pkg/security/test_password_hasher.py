"""PasswordHasher 单元测试。"""

from pkg.config import PasswordPolicySettings
from pkg.security import PasswordHasher


def _policy() -> PasswordPolicySettings:
    """构造一个测试用密码策略（迭代次数调小以加速测试）。"""
    return PasswordPolicySettings(iterations=1000, max_failed_attempts=5, lock_duration_seconds=60)


def test_hash_produces_valid_pbkdf2_string() -> None:
    """hash 应返回 pbkdf2_sha256$<iter>$<salt>$<hash> 格式字符串。"""
    hasher = PasswordHasher(_policy())
    encoded = hasher.hash("correct horse battery staple")
    parts = encoded.split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) == 1000
    assert len(parts[2]) > 0
    assert len(parts[3]) > 0


def test_hash_returns_different_salt_each_call() -> None:
    """两次相同明文的 hash 应因 salt 随机而不同。"""
    hasher = PasswordHasher(_policy())
    assert hasher.hash("same-password") != hasher.hash("same-password")


def test_verify_accepts_matching_password() -> None:
    """verify 对正确密码应返回 True。"""
    hasher = PasswordHasher(_policy())
    encoded = hasher.hash("hunter2")
    assert hasher.verify("hunter2", encoded) is True


def test_verify_rejects_wrong_password() -> None:
    """verify 对错误密码应返回 False。"""
    hasher = PasswordHasher(_policy())
    encoded = hasher.hash("hunter2")
    assert hasher.verify("hunter3", encoded) is False


def test_verify_rejects_malformed_encoded() -> None:
    """verify 对格式非法的编码应返回 False 而不是抛异常。"""
    hasher = PasswordHasher(_policy())
    assert hasher.verify("anything", "not-a-valid-hash") is False
    assert hasher.verify("anything", "pbkdf2_sha256$1000$zzz") is False


def test_verify_rejects_non_matching_iteration_hash() -> None:
    """篡改 hash 段后应校验失败。"""
    hasher = PasswordHasher(_policy())
    encoded = hasher.hash("pw")
    # 修改最后一段 hash 字符
    tampered = encoded[:-1] + ("0" if encoded[-1] != "0" else "1")
    assert hasher.verify("pw", tampered) is False


def test_hash_rejects_empty_password() -> None:
    """hash 对空密码应抛 ValueError。"""
    import pytest

    hasher = PasswordHasher(_policy())
    with pytest.raises(ValueError):
        hasher.hash("")
