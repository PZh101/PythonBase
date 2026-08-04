# User Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个可从 `application.yml`、profile 文件及 `APP_` 环境变量生成不可变强类型运行时配置的通用模块。

**Architecture:** `loader.py` 只负责文件读取、profile 选择和字典合并，`environment.py` 只负责环境变量映射，`models.py` 负责基础配置校验，`manager.py` 将这些能力编排成不可变快照和访问 API。配置模块不导入数据库模块；数据库类型枚举和数据库配置模型由配置模块拥有。

**Tech Stack:** Python 3.12、PyYAML、Pydantic 2.x、pytest、uv

---

## 文件结构

```text
pkg/config/
├── __init__.py       # 公共导出
├── exceptions.py     # 配置异常层次
├── models.py         # 强类型、冻结的基础配置模型
├── environment.py    # APP_ 环境变量解析
├── loader.py         # YAML/profile 加载及深度合并
├── security.py       # 敏感配置递归脱敏
└── manager.py        # ConfigSnapshot、ConfigManager 和全局访问器
tests/pkg/config/
├── __init__.py
├── test_models.py
├── test_environment.py
├── test_loader.py
└── test_manager.py
application.yml       # 可运行的默认示例配置
application-<profile>.yml  # 用户按需提供的 profile 差异配置，加载器支持但不预创建
```

### Task 1: 依赖、异常和强类型配置模型

**Files:**
- Modify: `pyproject.toml`
- Create: `pkg/config/__init__.py`
- Create: `pkg/config/exceptions.py`
- Create: `pkg/config/models.py`
- Create: `tests/pkg/config/__init__.py`
- Create: `tests/pkg/config/test_models.py`

- [ ] **Step 1: 添加模型失败测试**

在 `tests/pkg/config/test_models.py` 覆盖默认 MySQL、PostgreSQL 默认端口、显式端口、非法端口、空字段和冻结行为：

```python
import pytest
from pydantic import ValidationError

from pkg.config.models import DatabaseSettings, DatabaseType, RuntimeSettings


def test_database_defaults_to_mysql() -> None:
    settings = DatabaseSettings()
    assert settings.type is DatabaseType.MYSQL
    assert settings.port == 3306


def test_postgresql_gets_default_port_after_type_is_known() -> None:
    settings = DatabaseSettings(type="postgresql")
    assert settings.type is DatabaseType.POSTGRESQL
    assert settings.port == 5432


def test_explicit_port_is_preserved() -> None:
    settings = DatabaseSettings(type="postgresql", port=15432)
    assert settings.port == 15432


def test_numeric_password_is_normalized_to_text() -> None:
    settings = DatabaseSettings(password=12345)
    assert settings.password == "12345"


@pytest.mark.parametrize("field", ["host", "username", "database"])
def test_required_connection_text_cannot_be_blank(field: str) -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(**{field: "   "})


def test_runtime_settings_are_frozen() -> None:
    settings = RuntimeSettings()
    with pytest.raises(ValidationError):
        settings.database = DatabaseSettings(type="postgresql")
```

- [ ] **Step 2: 运行测试并确认因模块缺失而失败**

Run: `uv run pytest tests/pkg/config/test_models.py -v`

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'pkg.config'`。

- [ ] **Step 3: 添加 PyYAML 依赖并实现模型**

使用 `uv add pyyaml` 更新 `pyproject.toml` 和 `uv.lock`。创建异常基类及模型：

```python
class ConfigError(Exception):
    """配置模块异常基类。"""


class ConfigFileNotFoundError(ConfigError):
    """配置文件不存在。"""


class ConfigParseError(ConfigError):
    """配置文件格式错误。"""


class InvalidProfileError(ConfigError):
    """profile 名称不合法。"""


class ProfileNotFoundError(ConfigError):
    """指定 profile 不存在。"""


class ConfigEnvironmentError(ConfigError):
    """环境变量配置路径错误。"""


class ConfigValidationError(ConfigError):
    """配置字段校验失败。"""


class ConfigKeyError(ConfigError, KeyError):
    """运行时配置键不存在。"""


class ConfigNotInitializedError(ConfigError):
    """全局配置尚未初始化。"""


class ConfigAlreadyInitializedError(ConfigError):
    """配置已经初始化。"""
```

`models.py` 使用冻结模型，数据库端口在 `model_validator(mode="after")` 中按最终类型补全：

```python
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatabaseType(StrEnum):
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class FrozenSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


class ProfileSettings(FrozenSettings):
    active: str = "default"


class AppSettings(FrozenSettings):
    name: str = "pythonbase"
    profile: ProfileSettings = Field(default_factory=ProfileSettings)


class PoolSettings(FrozenSettings):
    size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    timeout: float = Field(default=30, gt=0)
    recycle: int = Field(default=1800, ge=0)
    pre_ping: bool = True


class DatabaseSettings(FrozenSettings):
    type: DatabaseType = DatabaseType.MYSQL
    host: str = "127.0.0.1"
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str = "root"
    password: str = ""
    database: str = "pythonbase"
    echo: bool = False
    connect_timeout: float = Field(default=10, gt=0)
    startup_check: bool = True
    pool: PoolSettings = Field(default_factory=PoolSettings)

    @field_validator("host", "username", "database")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value

    @field_validator("password", mode="before")
    @classmethod
    def normalize_password(cls, value: object) -> str:
        if value is None:
            raise ValueError("不能为空")
        return str(value)

    @model_validator(mode="after")
    def resolve_default_port(self) -> "DatabaseSettings":
        if self.port is None:
            port = 3306 if self.type is DatabaseType.MYSQL else 5432
            object.__setattr__(self, "port", port)
        return self


class RuntimeSettings(FrozenSettings):
    model_config = ConfigDict(frozen=True, extra="allow", validate_default=True)
    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
```

- [ ] **Step 4: 运行模型测试**

Run: `uv run pytest tests/pkg/config/test_models.py -v`

Expected: PASS，全部模型测试通过。

- [ ] **Step 5: 提交模型基础**

```bash
git add pyproject.toml uv.lock pkg/config tests/pkg/config
git commit -m "feat: add typed configuration models"
```

### Task 2: APP_ 环境变量解析

**Files:**
- Create: `pkg/config/environment.py`
- Create: `tests/pkg/config/test_environment.py`

- [ ] **Step 1: 添加环境变量映射失败测试**

```python
import pytest

from pkg.config.environment import get_environment_profile, parse_environment
from pkg.config.exceptions import ConfigEnvironmentError


def test_environment_maps_nested_keys_and_types() -> None:
    result = parse_environment({
        "APP_DATABASE__POOL__SIZE": "20",
        "APP_DATABASE__POOL__PRE_PING": "false",
        "APP_FEATURES__REGIONS": "[cn-east, cn-south]",
        "IGNORED_VALUE": "1",
    })
    assert result == {
        "database": {"pool": {"size": 20, "pre_ping": False}},
        "features": {"regions": ["cn-east", "cn-south"]},
    }


def test_profile_is_reserved_and_not_mapped() -> None:
    environ = {"APP_PROFILE": "prod", "APP_APP__NAME": "demo"}
    assert get_environment_profile(environ) == "prod"
    assert parse_environment(environ) == {"app": {"name": "demo"}}


def test_single_underscore_remains_in_field_name() -> None:
    result = parse_environment({"APP_DATABASE__CONNECT_TIMEOUT": "5"})
    assert result == {"database": {"connect_timeout": 5}}


def test_conflicting_environment_paths_are_rejected() -> None:
    with pytest.raises(ConfigEnvironmentError):
        parse_environment({"APP_DATABASE": "mysql", "APP_DATABASE__HOST": "db"})
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/pkg/config/test_environment.py -v`

Expected: FAIL，错误指出 `pkg.config.environment` 不存在。

- [ ] **Step 3: 实现受控环境变量解析**

实现 `get_environment_profile()`、安全 YAML 标量解析、双下划线路径拆分和冲突检测：

```python
import os
from collections.abc import Mapping, MutableMapping
from typing import Any

import yaml
from yaml import YAMLError

from pkg.config.exceptions import ConfigEnvironmentError


def get_environment_profile(
    environ: Mapping[str, str] | None = None,
) -> str | None:
    source = os.environ if environ is None else environ
    value = source.get("APP_PROFILE")
    return value.strip() if value and value.strip() else None


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
        existing = current.get(segment)
        if existing is None:
            existing = {}
            current[segment] = existing
        if not isinstance(existing, MutableMapping):
            raise ConfigEnvironmentError(f"环境变量路径冲突: {'.'.join(path)}")
        current = existing

    leaf = path[-1]
    if leaf in current and isinstance(current[leaf], MutableMapping):
        raise ConfigEnvironmentError(f"环境变量路径冲突: {'.'.join(path)}")
    current[leaf] = value


def parse_environment(
    environ: Mapping[str, str] | None = None,
    *,
    prefix: str = "APP_",
    delimiter: str = "__",
) -> dict[str, Any]:
    source = os.environ if environ is None else environ
    result: dict[str, Any] = {}
    for name, raw_value in source.items():
        if not name.startswith(prefix) or name == "APP_PROFILE":
            continue
        key = name[len(prefix):]
        path = [segment.lower() for segment in key.split(delimiter)]
        if not key or any(not segment for segment in path):
            raise ConfigEnvironmentError(f"环境变量路径非法: {name}")
        _insert_path(result, path, _parse_value(raw_value))
    return result
```

- [ ] **Step 4: 运行环境变量测试**

Run: `uv run pytest tests/pkg/config/test_environment.py -v`

Expected: PASS，4 个测试全部通过。

- [ ] **Step 5: 提交环境变量解析**

```bash
git add pkg/config/environment.py tests/pkg/config/test_environment.py
git commit -m "feat: parse application environment overrides"
```

### Task 3: YAML、profile 选择和深度合并

**Files:**
- Create: `pkg/config/loader.py`
- Create: `tests/pkg/config/test_loader.py`

- [ ] **Step 1: 添加加载与合并失败测试**

测试使用 `tmp_path` 写入临时 YAML，覆盖以下完整行为：

```python
from pathlib import Path

import pytest

from pkg.config.exceptions import InvalidProfileError, ProfileNotFoundError
from pkg.config.loader import deep_merge, load_configuration


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_deep_merge_recurses_and_replaces_lists() -> None:
    base = {"database": {"pool": {"size": 10, "timeout": 30}}, "items": [1, 2]}
    override = {"database": {"pool": {"size": 20}}, "items": [3]}
    assert deep_merge(base, override) == {
        "database": {"pool": {"size": 20, "timeout": 30}},
        "items": [3],
    }


def test_profile_sources_merge_in_documented_order(tmp_path: Path) -> None:
    write(tmp_path / "application.yml", """
app:
  profile:
    active: dev
database:
  host: common
  pool:
    size: 10
    timeout: 30
profiles:
  dev:
    database:
      host: inline
      pool:
        size: 15
""")
    write(tmp_path / "application-dev.yml", """
database:
  host: file
""")
    loaded = load_configuration(
        tmp_path,
        environ={"APP_DATABASE__POOL__SIZE": "20"},
    )
    assert loaded.active_profile == "dev"
    assert loaded.data["database"] == {
        "host": "file",
        "pool": {"size": 20, "timeout": 30},
    }
    assert "profiles" not in loaded.data
    assert loaded.data["app"]["profile"]["active"] == "dev"


def test_profile_selection_priority(tmp_path: Path) -> None:
    write(tmp_path / "application.yml", "app: {profile: {active: file}}\nprofiles: {file: {}, env: {}, explicit: {}}")
    loaded = load_configuration(tmp_path, profile="explicit", environ={"APP_PROFILE": "env"})
    assert loaded.active_profile == "explicit"


def test_invalid_and_missing_profiles_fail(tmp_path: Path) -> None:
    write(tmp_path / "application.yml", "{}")
    with pytest.raises(InvalidProfileError):
        load_configuration(tmp_path, profile="../prod")
    with pytest.raises(ProfileNotFoundError):
        load_configuration(tmp_path, profile="prod")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/pkg/config/test_loader.py -v`

Expected: FAIL，错误指出 `pkg.config.loader` 不存在。

- [ ] **Step 3: 实现加载器**

定义冻结的加载结果：

```python
@dataclass(frozen=True, slots=True)
class LoadedConfiguration:
    data: dict[str, Any]
    active_profile: str
    primary_path: Path
    profile_path: Path | None
```

完整加载算法如下：

```python
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
    data: dict[str, Any]
    active_profile: str
    primary_path: Path
    profile_path: Path | None


def deep_merge(*sources: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
    return result


def load_yaml_file(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ConfigFileNotFoundError(f"配置文件不存在: {path}")
        return {}
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f"第 {mark.line + 1} 行，第 {mark.column + 1} 列" if mark else "未知位置"
        raise ConfigParseError(f"YAML 格式错误: {path}，{location}") from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigParseError(f"配置文件读取失败: {path}: {type(exc).__name__}") from exc
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise ConfigParseError(f"配置文件根节点必须是字典: {path}")
    return content


def _profile_from_main(data: Mapping[str, Any]) -> str | None:
    app = data.get("app")
    if not isinstance(app, Mapping):
        return None
    profile = app.get("profile")
    if not isinstance(profile, Mapping):
        return None
    active = profile.get("active")
    return str(active) if active is not None else None


def load_configuration(
    config_dir: str | Path,
    *,
    profile: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> LoadedConfiguration:
    directory = Path(config_dir).resolve()
    primary_path = directory / "application.yml"
    main_data = load_yaml_file(primary_path, required=True)

    active = profile or get_environment_profile(environ) or _profile_from_main(main_data) or "default"
    if not PROFILE_PATTERN.fullmatch(active):
        raise InvalidProfileError(f"profile 名称非法: {active}")

    raw_profiles = main_data.get("profiles", {})
    if not isinstance(raw_profiles, Mapping):
        raise ConfigParseError(f"profiles 必须是字典: {primary_path}")
    inline_exists = active in raw_profiles
    inline_profile = raw_profiles.get(active, {})
    if not isinstance(inline_profile, Mapping):
        raise ConfigParseError(f"profiles.{active} 必须是字典: {primary_path}")

    candidate = directory / f"application-{active}.yml"
    file_exists = candidate.is_file()
    if active != "default" and not inline_exists and not file_exists:
        raise ProfileNotFoundError(f"profile 不存在: {active}")
    profile_data = load_yaml_file(candidate, required=False)

    common = dict(main_data)
    common.pop("profiles", None)
    merged = deep_merge(common, inline_profile, profile_data, parse_environment(environ))

    app = merged.setdefault("app", {})
    if not isinstance(app, MutableMapping):
        raise ConfigParseError("app 配置必须是字典")
    profile_data_node = app.setdefault("profile", {})
    if not isinstance(profile_data_node, MutableMapping):
        raise ConfigParseError("app.profile 配置必须是字典")
    profile_data_node["active"] = active

    return LoadedConfiguration(
        data=merged,
        active_profile=active,
        primary_path=primary_path,
        profile_path=candidate if file_exists else None,
    )
```

- [ ] **Step 4: 运行加载器测试**

Run: `uv run pytest tests/pkg/config/test_loader.py -v`

Expected: PASS，4 个测试全部通过。

- [ ] **Step 5: 提交加载器**

```bash
git add pkg/config/loader.py tests/pkg/config/test_loader.py
git commit -m "feat: load and merge profile configuration"
```

### Task 4: 不可变快照、通用访问和全局入口

**Files:**
- Create: `pkg/config/security.py`
- Create: `pkg/config/manager.py`
- Modify: `pkg/config/__init__.py`
- Create: `tests/pkg/config/test_manager.py`

- [ ] **Step 1: 添加 Manager 失败测试**

```python
from pathlib import Path

import pytest

from pkg.config.exceptions import (
    ConfigAlreadyInitializedError,
    ConfigKeyError,
    ConfigValidationError,
)
from pkg.config.manager import ConfigManager
from pkg.config.models import DatabaseType
from pkg.config.security import redact_sensitive


def write_config(path: Path, content: str) -> None:
    path.joinpath("application.yml").write_text(content, encoding="utf-8")


def test_manager_exposes_typed_and_generic_values(tmp_path: Path) -> None:
    write_config(tmp_path, "features: {order_timeout: 45}\ndatabase: {type: postgresql}")
    manager = ConfigManager(tmp_path, environ={})
    snapshot = manager.load()
    assert snapshot.settings.database.type is DatabaseType.POSTGRESQL
    assert snapshot.settings.database.port == 5432
    assert manager.get("features.order_timeout") == 45
    assert manager.get("features.missing", default=30) == 30


def test_missing_key_and_repeated_load_fail(tmp_path: Path) -> None:
    write_config(tmp_path, "{}")
    manager = ConfigManager(tmp_path, environ={})
    manager.load()
    with pytest.raises(ConfigKeyError):
        manager.get("missing.value")
    with pytest.raises(ConfigAlreadyInitializedError):
        manager.load()


def test_snapshot_data_is_recursively_immutable(tmp_path: Path) -> None:
    write_config(tmp_path, "features: {nested: {enabled: true}, regions: [cn-east]}")
    snapshot = ConfigManager(tmp_path, environ={}).load()
    with pytest.raises(TypeError):
        snapshot.data["features"]["nested"]["enabled"] = False
    assert snapshot.data["features"]["regions"] == ("cn-east",)
    with pytest.raises(TypeError):
        snapshot.settings.features["nested"]["enabled"] = False


def test_validation_error_does_not_include_password(tmp_path: Path) -> None:
    write_config(tmp_path, "database: {password: super-secret, port: 99999}")
    with pytest.raises(ConfigValidationError) as exc_info:
        ConfigManager(tmp_path, environ={}).load()
    assert "super-secret" not in str(exc_info.value)
    assert "database.port" in str(exc_info.value)


def test_sensitive_values_are_recursively_redacted() -> None:
    source = {
        "database": {"password": "secret", "host": "db.internal"},
        "services": [{"api_key": "key-value", "enabled": True}],
    }
    assert redact_sensitive(source) == {
        "database": {"password": "***", "host": "db.internal"},
        "services": [{"api_key": "***", "enabled": True}],
    }
    assert source["database"]["password"] == "secret"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/pkg/config/test_manager.py -v`

Expected: FAIL，错误指出 `pkg.config.manager` 不存在。

- [ ] **Step 3: 实现 Manager 和快照**

先在 `security.py` 实现不修改原对象的递归脱敏：

```python
from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS = frozenset({
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "access_key",
    "private_key",
})


def redact_sensitive(value: Any) -> Any:
    """递归复制配置结构，并将敏感键对应的值替换为星号。"""
    if isinstance(value, Mapping):
        return {
            key: "***" if str(key).lower() in SENSITIVE_KEYS else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value
```

随后实现递归冻结、路径访问、Pydantic 校验错误脱敏和全局入口：

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from pkg.config.exceptions import (
    ConfigAlreadyInitializedError,
    ConfigKeyError,
    ConfigNotInitializedError,
    ConfigValidationError,
)
from pkg.config.loader import load_configuration
from pkg.config.models import RuntimeSettings

_MISSING = object()
_default_manager: "ConfigManager | None" = None


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    active_profile: str
    primary_path: Path
    profile_path: Path | None
    settings: RuntimeSettings
    data: Mapping[str, Any]

    def get(self, path: str, default: Any = _MISSING) -> Any:
        segments = path.split(".") if path else []
        if not segments or any(not segment for segment in segments):
            raise ConfigKeyError(f"配置路径非法: {path!r}")
        current: Any = self.data
        for segment in segments:
            if not isinstance(current, Mapping) or segment not in current:
                if default is not _MISSING:
                    return default
                raise ConfigKeyError(f"配置项不存在: {path}")
            current = current[segment]
        return current


class ConfigManager:
    def __init__(
        self,
        config_dir: str | Path = ".",
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._config_dir = Path(config_dir)
        self._environ = dict(environ) if environ is not None else None
        self._snapshot: ConfigSnapshot | None = None

    def load(self, *, profile: str | None = None) -> ConfigSnapshot:
        if self._snapshot is not None:
            raise ConfigAlreadyInitializedError("配置已经加载")
        loaded = load_configuration(
            self._config_dir,
            profile=profile,
            environ=self._environ,
        )
        try:
            settings = RuntimeSettings.model_validate(_deep_freeze(loaded.data))
        except ValidationError as exc:
            details = []
            for error in exc.errors(include_input=False):
                location = ".".join(str(part) for part in error["loc"])
                details.append(f"{location}: {error['msg']}")
            raise ConfigValidationError("配置校验失败: " + "; ".join(details)) from exc

        self._snapshot = ConfigSnapshot(
            active_profile=loaded.active_profile,
            primary_path=loaded.primary_path,
            profile_path=loaded.profile_path,
            settings=settings,
            data=_deep_freeze(settings.model_dump(mode="python")),
        )
        return self._snapshot

    @property
    def snapshot(self) -> ConfigSnapshot:
        if self._snapshot is None:
            raise ConfigNotInitializedError("配置尚未加载")
        return self._snapshot

    @property
    def settings(self) -> RuntimeSettings:
        return self.snapshot.settings

    def get(self, path: str, default: Any = _MISSING) -> Any:
        return self.snapshot.get(path, default)


def initialize_config(
    config_dir: str | Path = ".",
    *,
    profile: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ConfigSnapshot:
    global _default_manager
    if _default_manager is not None:
        raise ConfigAlreadyInitializedError("全局配置已经初始化")
    manager = ConfigManager(config_dir, environ=environ)
    snapshot = manager.load(profile=profile)
    _default_manager = manager
    return snapshot


def get_config() -> ConfigSnapshot:
    if _default_manager is None:
        raise ConfigNotInitializedError("全局配置尚未初始化")
    return _default_manager.snapshot
```

`pkg/config/__init__.py` 导出公共异常、模型、`ConfigManager`、`ConfigSnapshot`、`initialize_config()` 和 `get_config()`。

- [ ] **Step 4: 运行 Manager 测试和全部配置测试**

Run: `uv run pytest tests/pkg/config -v`

Expected: PASS，模型、环境变量、加载器和 Manager 测试全部通过。

- [ ] **Step 5: 提交运行时配置 API**

```bash
git add pkg/config tests/pkg/config
git commit -m "feat: expose immutable runtime configuration"
```

### Task 5: 默认配置、文档与全量验证

**Files:**
- Create: `application.yml`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-04-user-configuration-design.md` only if implementation reveals an explicit contract correction

- [ ] **Step 1: 创建不含真实凭据的默认配置**

```yaml
app:
  name: pythonbase
  profile:
    active: default

database:
  type: mysql
  host: 127.0.0.1
  username: root
  password: ""
  database: pythonbase
  pool:
    size: 10
    max_overflow: 20
    timeout: 30
    recycle: 1800
    pre_ping: true

profiles:
  dev:
    database:
      echo: true
  postgresql:
    database:
      type: postgresql
```

- [ ] **Step 2: 在 README 添加使用示例**

说明 profile 优先级、`APP_` 双下划线覆盖规则，以及以下启动代码：

```python
from pkg.config import initialize_config

config = initialize_config()
print(config.settings.database.type)
print(config.get("features.enabled", default=False))
```

- [ ] **Step 3: 运行全量测试**

Run: `uv run pytest -v`

Expected: 全部测试 PASS，无失败或错误。

- [ ] **Step 4: 验证默认配置可加载**

Run: `uv run python -c "from pkg.config import initialize_config; c = initialize_config(); print(c.active_profile, c.settings.database.type, c.settings.database.port)"`

Expected: 输出 `default mysql 3306`。

- [ ] **Step 5: 验证 PostgreSQL profile**

Run: `uv run python -c "from pkg.config import initialize_config; c = initialize_config(profile='postgresql'); print(c.active_profile, c.settings.database.type, c.settings.database.port)"`

Expected: 输出 `postgresql postgresql 5432`。

- [ ] **Step 6: 检查敏感信息和工作区差异**

Run: `rg -n "super-secret|password:\s+[^\"']\S+" application.yml pkg/config tests/pkg/config`

Expected: 不出现测试密钥或非空明文密码。

Run: `git diff --check`

Expected: 无空白错误。

- [ ] **Step 7: 提交用户配置模块**

```bash
git add application.yml README.md pyproject.toml uv.lock pkg/config tests/pkg/config docs/superpowers/specs/2026-08-04-user-configuration-design.md
git commit -m "feat: implement profile-aware user configuration"
```
