"""Bearer token 头解析工具测试。"""

from pkg.security import extract_bearer_token


def test_returns_none_for_none_input() -> None:
    """输入为 None 时返回 None。"""
    assert extract_bearer_token(None) is None


def test_returns_none_for_empty_string() -> None:
    """空字符串输入返回 None。"""
    assert extract_bearer_token("") is None


def test_extracts_bearer_token() -> None:
    """标准 Authorization 头应能解析出 token。"""
    assert extract_bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"


def test_is_case_insensitive_on_scheme() -> None:
    """Bearer 关键字大小写不敏感。"""
    assert extract_bearer_token("bearer abc.def.ghi") == "abc.def.ghi"
    assert extract_bearer_token("BEARER abc.def.ghi") == "abc.def.ghi"


def test_strips_whitespace() -> None:
    """token 前后空白应被裁剪。"""
    assert extract_bearer_token("  Bearer   abc.def.ghi  ") == "abc.def.ghi"


def test_returns_none_for_non_bearer_scheme() -> None:
    """非 Bearer 协议应返回 None。"""
    assert extract_bearer_token("Basic dXNlcjpwYXNz") is None
    assert extract_bearer_token("Token abc") is None


def test_returns_none_when_token_is_empty() -> None:
    """Bearer 后无 token 内容应返回 None。"""
    assert extract_bearer_token("Bearer   ") is None
    assert extract_bearer_token("Bearer") is None
