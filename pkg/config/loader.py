"""YAML 配置文件、profile 和环境变量合并加载。"""

import copy
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yaml import YAMLError

from pkg.config.environment import get_environment_profile, parse_environment
from pkg.config.exceptions import (
    ConfigFileNotFoundError,
    ConfigParseError,
    InvalidProfileError,
    ProfileNotFoundError,
)

PROFILE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class LoadedConfiguration:
    """配置加载结果。"""

    data: dict[str, Any]
    active_profile: str
    primary_path: Path
    profile_path: Path | None


def deep_merge(*sources: Mapping[str, Any]) -> dict[str, Any]:
    """深度合并多个字典配置。

    Args:
        sources: 按低优先级到高优先级排列的配置源。

    Returns:
        合并后的新字典。

    使用方式:
        后面的配置源覆盖前面的配置源；字典递归合并，列表和标量整体替换。
    """
    result: dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            existing = result.get(key)
            if isinstance(existing, Mapping) and isinstance(value, Mapping):
                result[key] = deep_merge(existing, value)
            else:
                result[key] = copy.deepcopy(value)
    return result


def load_yaml_file(path: Path, *, required: bool) -> dict[str, Any]:
    """读取 YAML 配置文件。

    Args:
        path: 配置文件路径。
        required: 文件不存在时是否报错。

    Returns:
        YAML 根字典。空文件和可选缺失文件返回空字典。
    """
    resolved_path = path.resolve()
    if not resolved_path.is_file():
        if required:
            raise ConfigFileNotFoundError(f"配置文件不存在: {resolved_path}")
        return {}

    try:
        content = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f"第 {mark.line + 1} 行，第 {mark.column + 1} 列" if mark is not None else "未知位置"
        raise ConfigParseError(f"YAML 格式错误: {resolved_path}，{location}") from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigParseError(f"配置文件读取失败: {resolved_path}: {type(exc).__name__}") from exc

    if content is None:
        return {}
    if not isinstance(content, dict):
        raise ConfigParseError(f"配置文件根节点必须是字典: {resolved_path}")
    return content


def load_configuration(
    config_dir: str | Path,
    *,
    profile: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> LoadedConfiguration:
    """加载最终运行时配置字典。

    Args:
        config_dir: 配置目录。
        profile: 显式指定的 profile。
        environ: 环境变量源。不传时读取当前进程环境变量。

    Returns:
        合并后的配置数据和加载元数据。
    """
    directory = Path(config_dir).resolve()
    primary_path = directory / "application.yml"
    main_data = load_yaml_file(primary_path, required=True)
    active_profile = _select_profile(profile=profile, environ=environ, main_data=main_data)

    raw_profiles = main_data.get("profiles", {})
    if not isinstance(raw_profiles, Mapping):
        raise ConfigParseError(f"profiles 必须是字典: {primary_path}")

    inline_exists = active_profile in raw_profiles
    inline_profile = raw_profiles.get(active_profile, {})
    if not isinstance(inline_profile, Mapping):
        raise ConfigParseError(f"profiles.{active_profile} 必须是字典: {primary_path}")

    profile_path = directory / f"application-{active_profile}.yml"
    profile_file_exists = profile_path.is_file()
    if active_profile != "default" and not inline_exists and not profile_file_exists:
        raise ProfileNotFoundError(f"profile 不存在: {active_profile}")

    profile_data = load_yaml_file(profile_path, required=False)
    common_data = dict(main_data)
    common_data.pop("profiles", None)

    merged = deep_merge(common_data, inline_profile, profile_data, parse_environment(environ))
    _force_active_profile(merged, active_profile)

    return LoadedConfiguration(
        data=merged,
        active_profile=active_profile,
        primary_path=primary_path,
        profile_path=profile_path if profile_file_exists else None,
    )


def _select_profile(
    *,
    profile: str | None,
    environ: Mapping[str, str] | None,
    main_data: Mapping[str, Any],
) -> str:
    """按显式、环境变量、主配置和默认值选择 profile。"""
    active_profile = (
        profile
        if profile is not None
        else get_environment_profile(environ) or _profile_from_main(main_data) or "default"
    )
    if not isinstance(active_profile, str):
        raise InvalidProfileError("profile 必须是字符串")

    normalized = active_profile.strip()
    if not PROFILE_PATTERN.fullmatch(normalized):
        raise InvalidProfileError(f"profile 名称非法: {active_profile}")
    return normalized


def _profile_from_main(main_data: Mapping[str, Any]) -> str | None:
    """从主配置 app.profile.active 中读取 profile。"""
    app_data = main_data.get("app")
    if app_data is None:
        return None
    if not isinstance(app_data, Mapping):
        raise ConfigParseError("app 配置必须是字典")

    profile_data = app_data.get("profile")
    if profile_data is None:
        return None
    if not isinstance(profile_data, Mapping):
        raise ConfigParseError("app.profile 配置必须是字典")

    active_profile = profile_data.get("active")
    if active_profile is None:
        return None
    if not isinstance(active_profile, str):
        raise InvalidProfileError("profile 必须是字符串")
    return active_profile


def _force_active_profile(data: dict[str, Any], active_profile: str) -> None:
    """强制最终配置中的 app.profile.active 等于实际选择的 profile。"""
    app_data = data.setdefault("app", {})
    if not isinstance(app_data, MutableMapping):
        raise ConfigParseError("app 配置必须是字典")

    profile_data = app_data.setdefault("profile", {})
    if not isinstance(profile_data, MutableMapping):
        raise ConfigParseError("app.profile 配置必须是字典")

    profile_data["active"] = active_profile
