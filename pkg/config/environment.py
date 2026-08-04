"""应用环境变量解析。"""

import os
from collections.abc import Mapping, MutableMapping
from typing import Any

import yaml
from yaml import YAMLError

from pkg.config.exceptions import ConfigEnvironmentError


def get_environment_profile(environ: Mapping[str, str] | None = None) -> str | None:
    """读取并规范化 APP_PROFILE 指定的活动 profile。"""
    source = os.environ if environ is None else environ
    value = source.get("APP_PROFILE")
    if value is None:
        return None

    profile = value.strip()
    return profile or None


def _parse_value(value: str) -> Any:
    if value == "":
        return ""
    try:
        return yaml.safe_load(value)
    except YAMLError:
        return value


def _insert_path(target: MutableMapping[str, Any], path: list[str], value: Any) -> None:
    current = target
    for segment in path[:-1]:
        if segment not in current:
            current[segment] = {}
        existing = current[segment]
        if not isinstance(existing, MutableMapping):
            raise ConfigEnvironmentError(f"环境变量路径冲突: {'.'.join(path)}")
        current = existing

    leaf = path[-1]
    if leaf in current and (isinstance(current[leaf], Mapping) or isinstance(value, Mapping)):
        raise ConfigEnvironmentError(f"环境变量路径冲突: {'.'.join(path)}")
    current[leaf] = value


def parse_environment(
    environ: Mapping[str, str] | None = None,
    *,
    prefix: str = "APP_",
    delimiter: str = "__",
) -> dict[str, Any]:
    """将指定前缀的环境变量解析为嵌套配置字典。"""
    if not delimiter:
        raise ConfigEnvironmentError("环境变量路径分隔符不能为空")

    source = os.environ if environ is None else environ
    result: dict[str, Any] = {}
    for name, raw_value in source.items():
        if not name.startswith(prefix) or name == "APP_PROFILE":
            continue

        key = name[len(prefix) :]
        path = [segment.lower() for segment in key.split(delimiter)]
        if not key or any(not segment for segment in path):
            raise ConfigEnvironmentError(f"环境变量路径非法: {name}")
        _insert_path(result, path, _parse_value(raw_value))

    return result
