"""应用环境变量解析。"""

import os
from collections.abc import Mapping, MutableMapping
from typing import Any

import yaml
from yaml import YAMLError

from pkg.config.exceptions import ConfigEnvironmentError


def _is_reserved_profile(name: str, prefix: str) -> bool:
    return name.startswith(prefix) and name[len(prefix) :].casefold() == "profile"


def get_environment_profile(environ: Mapping[str, str] | None = None) -> str | None:
    """读取并规范化 APP_PROFILE 指定的活动 profile。"""
    source = os.environ if environ is None else environ
    matches = [value for name, value in source.items() if _is_reserved_profile(name, "APP_")]
    if len(matches) > 1:
        raise ConfigEnvironmentError("环境变量 profile 冲突: APP_PROFILE")
    if not matches:
        return None

    profile = matches[0].strip()
    return profile or None


def _parse_value(value: str) -> Any:
    if value == "":
        return ""
    try:
        return yaml.safe_load(value)
    except YAMLError:
        return value


def _collect_candidates(
    source: Mapping[str, str],
    prefix: str,
    delimiter: str,
) -> list[tuple[tuple[str, ...], str]]:
    candidates: list[tuple[tuple[str, ...], str]] = []
    for name, raw_value in source.items():
        if not name.startswith(prefix) or _is_reserved_profile(name, prefix):
            continue

        key = name[len(prefix) :]
        path = tuple(segment.lower() for segment in key.split(delimiter))
        if not key or any(not segment for segment in path):
            raise ConfigEnvironmentError(f"环境变量路径非法: {name}")
        candidates.append((path, raw_value))
    return candidates


def _validate_candidate_paths(candidates: list[tuple[tuple[str, ...], str]]) -> None:
    paths: set[tuple[str, ...]] = set()
    conflicts: set[tuple[str, ...]] = set()
    for path, _ in candidates:
        if path in paths:
            conflicts.add(path)
        paths.add(path)

    for path in paths:
        for length in range(1, len(path)):
            parent = path[:length]
            if parent in paths:
                conflicts.add(parent)

    if conflicts:
        canonical_path = ".".join(min(conflicts))
        raise ConfigEnvironmentError(f"环境变量路径冲突: {canonical_path}")


def _insert_path(target: MutableMapping[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = target
    for segment in path[:-1]:
        if segment not in current:
            current[segment] = {}
        existing = current[segment]
        if not isinstance(existing, MutableMapping):
            raise ConfigEnvironmentError(f"环境变量路径冲突: {'.'.join(path)}")
        current = existing

    leaf = path[-1]
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
    candidates = _collect_candidates(source, prefix, delimiter)
    _validate_candidate_paths(candidates)

    result: dict[str, Any] = {}
    for path, raw_value in sorted(candidates):
        _insert_path(result, path, _parse_value(raw_value))

    return result
