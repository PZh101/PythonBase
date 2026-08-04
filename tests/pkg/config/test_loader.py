"""YAML 配置加载、profile 选择和深度合并测试。"""

import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

import pkg.config.loader as loader
from pkg.config.exceptions import (
    ConfigFileNotFoundError,
    ConfigParseError,
    InvalidProfileError,
    ProfileNotFoundError,
)
from pkg.config.loader import LoadedConfiguration, deep_merge, load_configuration, load_yaml_file


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_deep_merge_recurses_and_replaces_values_without_mutating_sources() -> None:
    """深度合并应递归字典、整体替换列表和空值，并隔离所有源数据。"""
    base = {
        "database": {
            "pool": {"size": 10, "timeout": 30},
            "replicas": [{"host": "base"}],
        },
        "mode": {"name": "legacy"},
        "nullable": {"enabled": True},
        "metadata": "base",
    }
    override = {
        "database": {
            "pool": {"size": 20},
            "replicas": [{"host": "override"}],
        },
        "mode": "strict",
        "nullable": None,
        "metadata": {"owner": ["platform"]},
    }
    base_before = copy.deepcopy(base)
    override_before = copy.deepcopy(override)

    result = deep_merge(base, override)

    assert result == {
        "database": {
            "pool": {"size": 20, "timeout": 30},
            "replicas": [{"host": "override"}],
        },
        "mode": "strict",
        "nullable": None,
        "metadata": {"owner": ["platform"]},
    }
    result["database"]["pool"]["size"] = 99
    result["database"]["replicas"][0]["host"] = "changed"
    result["metadata"]["owner"].append("changed")
    assert base == base_before
    assert override == override_before


def test_load_yaml_file_returns_empty_for_missing_optional_file(tmp_path: Path) -> None:
    """可选 YAML 文件不存在时应返回空字典。"""
    assert load_yaml_file(tmp_path / "optional.yml", required=False) == {}


def test_load_yaml_file_returns_empty_for_empty_file(tmp_path: Path) -> None:
    """空 YAML 文件应解析为空字典。"""
    path = tmp_path / "empty.yml"
    _write(path, "")

    assert load_yaml_file(path, required=True) == {}


def test_main_only_configuration_uses_default_profile_and_resolved_metadata(tmp_path: Path) -> None:
    """仅主配置文件时应选择 default，并返回解析后的路径元数据。"""
    _write(
        tmp_path / "application.yml",
        """
app:
  name: 示例应用
features:
  regions: [cn-east]
""",
    )

    loaded = load_configuration(tmp_path, environ={})

    assert isinstance(loaded, LoadedConfiguration)
    assert loaded.data == {
        "app": {"name": "示例应用", "profile": {"active": "default"}},
        "features": {"regions": ["cn-east"]},
    }
    assert loaded.active_profile == "default"
    assert loaded.primary_path == (tmp_path / "application.yml").resolve()
    assert loaded.profile_path is None
    assert not hasattr(loaded, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(loaded, "active_profile", "prod")


def test_empty_main_configuration_is_valid_for_default_profile(tmp_path: Path) -> None:
    """空主配置文件应允许缺省的 default profile。"""
    _write(tmp_path / "application.yml", "")

    loaded = load_configuration(tmp_path, environ={})

    assert loaded.active_profile == "default"
    assert loaded.data == {"app": {"profile": {"active": "default"}}}
    assert loaded.profile_path is None


def test_profile_sources_merge_in_documented_order(tmp_path: Path) -> None:
    """公共、内联、外部文件和环境变量应按从低到高的优先级合并。"""
    _write(
        tmp_path / "application.yml",
        """
app:
  profile:
    active: dev
database:
  host: common
  pool:
    size: 10
    timeout: 30
  tags: [common]
profiles:
  dev:
    database:
      host: inline
      pool:
        size: 15
      tags: [inline]
""",
    )
    _write(
        tmp_path / "application-dev.yml",
        """
database:
  host: file
  tags: [file]
""",
    )
    environ = {
        "APP_DATABASE__POOL__SIZE": "20",
        "APP_DATABASE__POOL__PRE_PING": "false",
    }
    environ_before = environ.copy()

    loaded = load_configuration(tmp_path, environ=environ)

    assert loaded.data["database"] == {
        "host": "file",
        "pool": {"size": 20, "timeout": 30, "pre_ping": False},
        "tags": ["file"],
    }
    assert loaded.active_profile == "dev"
    assert loaded.data["app"]["profile"]["active"] == "dev"
    assert environ == environ_before


def test_profile_selection_priority_is_explicit_then_environment_then_main(tmp_path: Path) -> None:
    """profile 选择应依次采用显式参数、环境变量和主配置。"""
    _write(
        tmp_path / "application.yml",
        """
app:
  profile:
    active: main
profiles:
  main: {}
  env: {}
  explicit: {}
""",
    )

    explicit = load_configuration(tmp_path, profile="explicit", environ={"APP_PROFILE": "env"})
    environment = load_configuration(tmp_path, environ={"APP_PROFILE": "env"})
    main = load_configuration(tmp_path, environ={})

    assert explicit.active_profile == "explicit"
    assert environment.active_profile == "env"
    assert main.active_profile == "main"


@pytest.mark.parametrize(
    ("main_content", "external_content", "expected_source"),
    [
        (
            "app: {profile: {active: dev}}\nprofiles: {dev: {feature: {source: inline}}}\n",
            None,
            "inline",
        ),
        (
            "app: {profile: {active: dev}}\n",
            "feature: {source: file}\n",
            "file",
        ),
        (
            "app: {profile: {active: dev}}\nprofiles: {dev: {feature: {source: inline}}}\n",
            "feature: {source: file}\n",
            "file",
        ),
        (
            "app: {profile: {active: dev}}\nprofiles: {dev: {}}\n",
            None,
            None,
        ),
    ],
    ids=["inline-only", "file-only", "both", "empty-inline"],
)
def test_non_default_profile_may_be_inline_file_both_or_empty_inline(
    tmp_path: Path,
    main_content: str,
    external_content: str | None,
    expected_source: str | None,
) -> None:
    """非 default profile 应支持内联、文件、两者并存及空内联块。"""
    _write(tmp_path / "application.yml", main_content)
    if external_content is not None:
        _write(tmp_path / "application-dev.yml", external_content)

    loaded = load_configuration(tmp_path, environ={})

    assert loaded.active_profile == "dev"
    if expected_source is None:
        assert "feature" not in loaded.data
    else:
        assert loaded.data["feature"]["source"] == expected_source


def test_missing_non_default_profile_is_rejected(tmp_path: Path) -> None:
    """既无内联块也无外部文件的非 default profile 应被拒绝。"""
    _write(tmp_path / "application.yml", "{}\n")

    with pytest.raises(ProfileNotFoundError):
        load_configuration(tmp_path, profile="prod", environ={})


def test_absent_default_profile_is_allowed(tmp_path: Path) -> None:
    """default profile 缺少内联块和外部文件时仍应允许加载。"""
    _write(tmp_path / "application.yml", "{}\n")

    loaded = load_configuration(tmp_path, environ={})

    assert loaded.active_profile == "default"
    assert loaded.profile_path is None


@pytest.mark.parametrize("profile", ["", "   ", "../prod", "prod/dev", "prod\\dev", "prod dev"])
def test_invalid_explicit_profiles_are_rejected(tmp_path: Path, profile: str) -> None:
    """空白、路径穿越、路径分隔符和空格均不应成为合法 profile。"""
    _write(tmp_path / "application.yml", "{}\n")

    with pytest.raises(InvalidProfileError):
        load_configuration(tmp_path, profile=profile, environ={})


def test_non_string_main_active_profile_is_rejected(tmp_path: Path) -> None:
    """主配置中的活动 profile 必须是字符串。"""
    _write(tmp_path / "application.yml", "app: {profile: {active: 123}}\nprofiles: {'123': {}}\n")

    with pytest.raises(InvalidProfileError):
        load_configuration(tmp_path, environ={})


def test_missing_main_file_is_rejected_with_resolved_path(tmp_path: Path) -> None:
    """缺少必需的 application.yml 时应报告解析后的文件路径。"""
    expected_path = (tmp_path / "application.yml").resolve()

    with pytest.raises(ConfigFileNotFoundError) as exc_info:
        load_configuration(tmp_path, environ={})

    assert str(expected_path) in str(exc_info.value)


def test_malformed_yaml_reports_location_without_echoing_values(tmp_path: Path) -> None:
    """YAML 语法错误应报告文件和位置，但不得回显配置内容。"""
    secret = "super-secret-token"
    path = tmp_path / "application.yml"
    _write(path, f"password: {secret}\nbroken: [unterminated\n")

    with pytest.raises(ConfigParseError) as exc_info:
        load_yaml_file(path, required=True)

    message = str(exc_info.value)
    assert str(path) in message
    assert "行" in message
    assert "列" in message
    assert secret not in message
    assert "unterminated" not in message


def test_decode_error_reports_exception_type_without_echoing_content(tmp_path: Path) -> None:
    """UTF-8 解码错误应仅报告异常类型和路径，不得回显文件内容。"""
    path = tmp_path / "application.yml"
    path.write_bytes(b"\xffprivate-value")

    with pytest.raises(ConfigParseError) as exc_info:
        load_yaml_file(path, required=True)

    message = str(exc_info.value)
    assert str(path) in message
    assert "UnicodeDecodeError" in message
    assert "private-value" not in message


@pytest.mark.parametrize("content", ["- first\n- second\n", "plain-text\n", "42\n"])
def test_non_mapping_yaml_root_is_rejected(tmp_path: Path, content: str) -> None:
    """列表、标量和文本 YAML 根节点均应被拒绝。"""
    path = tmp_path / "application.yml"
    _write(path, content)

    with pytest.raises(ConfigParseError) as exc_info:
        load_yaml_file(path, required=True)

    assert str(path) in str(exc_info.value)


def test_non_mapping_profiles_node_is_rejected(tmp_path: Path) -> None:
    """顶层 profiles 节点必须是字典。"""
    _write(tmp_path / "application.yml", "profiles: [dev]\n")

    with pytest.raises(ConfigParseError):
        load_configuration(tmp_path, environ={})


@pytest.mark.parametrize("selected_block", ["null", "[]", "scalar"])
def test_non_mapping_selected_profile_block_is_rejected(tmp_path: Path, selected_block: str) -> None:
    """选中的内联 profile 块必须是字典。"""
    _write(
        tmp_path / "application.yml",
        f"app: {{profile: {{active: dev}}}}\nprofiles:\n  dev: {selected_block}\n",
    )

    with pytest.raises(ConfigParseError):
        load_configuration(tmp_path, environ={})


@pytest.mark.parametrize(
    "environ",
    [
        {"APP_APP": "scalar"},
        {"APP_APP__PROFILE": "scalar"},
    ],
    ids=["app", "app-profile"],
)
def test_merged_app_nodes_must_remain_mappings(tmp_path: Path, environ: dict[str, str]) -> None:
    """合并后的 app 和 app.profile 节点必须保持为字典。"""
    _write(tmp_path / "application.yml", "{}\n")

    with pytest.raises(ConfigParseError):
        load_configuration(tmp_path, environ=environ)


def test_actual_profile_is_forced_after_generic_environment_override(tmp_path: Path) -> None:
    """普通环境变量不得把最终活动 profile 改成未选择的值。"""
    _write(
        tmp_path / "application.yml",
        "app: {profile: {active: dev}}\nprofiles: {dev: {}}\n",
    )

    loaded = load_configuration(
        tmp_path,
        environ={"APP_APP__PROFILE__ACTIVE": "contradictory"},
    )

    assert loaded.active_profile == "dev"
    assert loaded.data["app"]["profile"]["active"] == "dev"


def test_profile_metadata_uses_existing_resolved_candidate_and_removes_profiles(tmp_path: Path) -> None:
    """存在的 profile 文件应返回解析路径，且加载元数据不进入最终配置。"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write(
        config_dir / "application.yml",
        "app: {profile: {active: prod}}\nprofiles: {prod: {inline: true}}\n",
    )
    _write(config_dir / "application-prod.yml", "external: true\n")

    loaded = load_configuration(config_dir / ".", environ={})

    assert loaded.primary_path == (config_dir / "application.yml").resolve()
    assert loaded.profile_path == (config_dir / "application-prod.yml").resolve()
    assert "profiles" not in loaded.data


def test_loading_does_not_mutate_parsed_source_dictionaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """加载和强制活动 profile 时不得修改主文件、profile 文件及环境源字典。"""
    main_source = {
        "app": {"profile": {"active": "main"}},
        "database": {"pool": {"size": 10}},
        "profiles": {"dev": {"database": {"host": "inline"}}},
    }
    profile_source = {"database": {"pool": {"timeout": 30}}}
    environment_source = {"app": {"profile": {"active": "wrong"}}, "database": {"host": "env"}}
    snapshots = tuple(copy.deepcopy(source) for source in (main_source, profile_source, environment_source))
    _write(tmp_path / "application.yml", "{}\n")
    _write(tmp_path / "application-dev.yml", "{}\n")

    def fake_load_yaml_file(path: Path, *, required: bool) -> dict[str, Any]:
        return main_source if path.name == "application.yml" else profile_source

    monkeypatch.setattr(loader, "load_yaml_file", fake_load_yaml_file)
    monkeypatch.setattr(loader, "parse_environment", lambda environ=None: environment_source)

    loaded = loader.load_configuration(tmp_path, profile="dev", environ={})

    assert loaded.data["database"] == {"pool": {"size": 10, "timeout": 30}, "host": "env"}
    assert loaded.data["app"]["profile"]["active"] == "dev"
    assert (main_source, profile_source, environment_source) == snapshots
