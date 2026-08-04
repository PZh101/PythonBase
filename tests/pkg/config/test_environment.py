"""应用环境变量解析测试。"""

import os
from collections.abc import Mapping

import pytest

from pkg.config.environment import get_environment_profile, parse_environment
from pkg.config.exceptions import ConfigEnvironmentError


def test_environment_maps_nested_keys_and_typed_values() -> None:
    """环境变量应映射嵌套路径并解析布尔值、数字、列表和字典。"""
    result = parse_environment(
        {
            "APP_DATABASE__POOL__SIZE": "20",
            "APP_DATABASE__POOL__PRE_PING": "false",
            "APP_DATABASE__CONNECT_TIMEOUT": "1.5",
            "APP_FEATURES__REGIONS": "[cn-east, cn-south]",
            "APP_FEATURES__LIMITS": "{daily: 100, burst: 10}",
        }
    )

    assert result == {
        "database": {"pool": {"size": 20, "pre_ping": False}, "connect_timeout": 1.5},
        "features": {"regions": ["cn-east", "cn-south"], "limits": {"daily": 100, "burst": 10}},
    }


@pytest.mark.parametrize(("raw_profile", "expected"), [("  prod  ", "prod"), ("   ", None), ("", None)])
def test_profile_is_trimmed_and_blank_profile_is_none(raw_profile: str, expected: str | None) -> None:
    """APP_PROFILE 应去除首尾空白，并将空值视为未选择 profile。"""
    assert get_environment_profile({"APP_PROFILE": raw_profile}) == expected


def test_profile_is_reserved_and_not_mapped() -> None:
    """APP_PROFILE 应仅用于选择 profile，不应进入普通配置映射。"""
    environ = {"APP_PROFILE": "prod", "APP_APP__NAME": "demo"}

    assert get_environment_profile(environ) == "prod"
    assert parse_environment(environ) == {"app": {"name": "demo"}}


def test_single_underscore_remains_in_field_name() -> None:
    """单下划线应保留在字段名中，只有双下划线拆分层级。"""
    result = parse_environment({"APP_DATABASE__CONNECT_TIMEOUT": "5"})

    assert result == {"database": {"connect_timeout": 5}}


def test_empty_string_is_preserved_and_yaml_null_is_parsed() -> None:
    """空原始文本应保持为空字符串，YAML null 应解析为 None。"""
    result = parse_environment({"APP_DATABASE__PASSWORD": "", "APP_FEATURES__OPTION": "null"})

    assert result == {"database": {"password": ""}, "features": {"option": None}}


def test_non_prefixed_values_are_ignored() -> None:
    """不带 APP_ 前缀的环境变量不应进入配置。"""
    result = parse_environment({"DATABASE__HOST": "ignored", "APP_DATABASE__HOST": "db"})

    assert result == {"database": {"host": "db"}}


@pytest.mark.parametrize("name", ["APP_", "APP___HOST", "APP_DATABASE____HOST", "APP_DATABASE__"])
def test_empty_environment_path_segments_are_rejected(name: str) -> None:
    """空配置键或空路径段应引发 ConfigEnvironmentError。"""
    raw_value = "must-not-appear"

    with pytest.raises(ConfigEnvironmentError) as exc_info:
        parse_environment({name: raw_value})

    assert raw_value not in str(exc_info.value)


@pytest.mark.parametrize(
    "environ",
    [
        {"APP_DATABASE": "mysql", "APP_DATABASE__HOST": "db"},
        {"APP_DATABASE__HOST": "db", "APP_DATABASE": "mysql"},
    ],
)
def test_scalar_and_mapping_path_conflicts_are_rejected(environ: Mapping[str, str]) -> None:
    """标量与映射路径冲突在两种插入顺序下都应被拒绝。"""
    with pytest.raises(ConfigEnvironmentError) as exc_info:
        parse_environment(environ)

    assert "mysql" not in str(exc_info.value)
    assert "db" not in str(exc_info.value)


@pytest.mark.parametrize(
    "environ",
    [
        {"APP_DATABASE": "mysql", "APP_database": "{host: db}"},
        {"APP_database": "{host: db}", "APP_DATABASE": "mysql"},
    ],
)
def test_normalized_scalar_and_mapping_conflicts_are_rejected(environ: Mapping[str, str]) -> None:
    """大小写不同但规范化后相同的标量与映射路径也应按任意顺序拒绝。"""
    with pytest.raises(ConfigEnvironmentError):
        parse_environment(environ)


def test_explicit_mapping_is_isolated_from_real_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式环境变量映射不应读取真实 os.environ。"""
    monkeypatch.setenv("APP_PROFILE", "real-profile")
    monkeypatch.setenv("APP_DATABASE__HOST", "real-db")
    explicit = {"APP_APP__NAME": "isolated"}

    assert get_environment_profile(explicit) is None
    assert parse_environment(explicit) == {"app": {"name": "isolated"}}


def test_none_environment_reads_real_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """未提供显式映射时应从 os.environ 读取 APP_ 配置。"""
    for name in tuple(os.environ):
        if name.startswith("APP_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("APP_PROFILE", "local")
    monkeypatch.setenv("APP_DATABASE__PORT", "5432")

    assert get_environment_profile() == "local"
    assert parse_environment()["database"]["port"] == 5432


def test_malformed_yaml_value_falls_back_to_raw_text() -> None:
    """YAML 解析失败时应保留未经修改的原始文本。"""
    raw_value = "[unterminated"

    assert parse_environment({"APP_APP__NAME": raw_value}) == {"app": {"name": raw_value}}


def test_parsing_does_not_mutate_explicit_mapping() -> None:
    """解析过程不应修改调用方提供的环境变量映射。"""
    environ = {"APP_DATABASE__POOL__SIZE": "20"}
    original = environ.copy()

    parse_environment(environ)

    assert environ == original
