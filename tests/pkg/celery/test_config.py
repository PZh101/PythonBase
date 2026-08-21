"""Celery 配置模型校验测试。"""

import pytest
from pydantic import ValidationError

from pkg.config.models import (
    BeatScheduleItem,
    BeatSettings,
    CelerySettings,
    RuntimeSettings,
)


def test_celery_settings_defaults() -> None:
    """Celery 配置应提供完整的默认值。"""
    settings = CelerySettings()

    assert settings.enabled is True
    assert settings.broker_url == "redis://127.0.0.1:6379/0"
    assert settings.result_backend == "redis://127.0.0.1:6379/1"
    assert settings.task_serializer == "json"
    assert settings.timezone == "Asia/Shanghai"
    assert settings.enable_utc is False
    assert settings.worker_pool is None
    assert settings.worker_concurrency is None
    assert settings.worker_prefetch_multiplier == 1
    assert settings.task_acks_late is True
    assert settings.task_reject_on_worker_lost is True
    assert settings.task_track_started is True
    assert settings.task_always_eager is False
    assert settings.task_eager_propagates is False
    assert settings.task_store_eager_result is True
    assert settings.max_retries == 3
    assert settings.retry_backoff is True
    assert settings.retry_backoff_max == 600
    assert settings.retry_jitter is True
    assert settings.beat == BeatSettings()
    assert settings.include == ["pkg.celery.tasks"]


def test_runtime_settings_nest_celery_defaults() -> None:
    """运行时配置应默认创建 Celery 配置。"""
    settings = RuntimeSettings()

    assert settings.celery == CelerySettings()


def test_blank_broker_url_is_rejected() -> None:
    """broker 地址不应接受空白文本。"""
    with pytest.raises(ValidationError):
        CelerySettings(broker_url="   ")


def test_blank_result_backend_normalizes_to_none() -> None:
    """空字符串结果后端应视为禁用（None）。"""
    settings = CelerySettings(result_backend="")

    assert settings.result_backend is None


def test_explicit_none_result_backend_disables_backend() -> None:
    """显式 None 结果后端应保持禁用。"""
    settings = CelerySettings(result_backend=None)

    assert settings.result_backend is None


def test_invalid_timezone_is_rejected() -> None:
    """未知时区应被拒绝。"""
    with pytest.raises(ValidationError):
        CelerySettings(timezone="Mars/Olympus_Mons")


def test_valid_timezone_is_accepted() -> None:
    """合法时区应被接受。"""
    settings = CelerySettings(timezone="UTC")

    assert settings.timezone == "UTC"


@pytest.mark.parametrize(
    "schedule",
    [
        "0 3 * * *",       # 合法：每天 03:00
        "*/5 0-23 * * *",  # 合法：分 时 日 月 周
        "0 0 1 1 0",       # 合法：具体值
    ],
)
def test_valid_cron_schedules(schedule: str) -> None:
    """合法 5 字段 cron 表达式应被接受。"""
    item = BeatScheduleItem(task="demo.echo", schedule=schedule)

    assert item.schedule == schedule


@pytest.mark.parametrize(
    "schedule",
    [
        "0 3 * *",        # 只有 4 个字段
        "0 3 * * * *",    # 6 个字段
        "0 99 * * *",     # 时越界
        "60 0 * * *",     # 分越界
        "0 0 0 * *",      # 日越界
        "0 0 * 13 *",     # 月越界
        "0 0 * * 7",      # 周越界
        "0 abc * * *",    # 非数字
        "",               # 空
    ],
)
def test_invalid_cron_schedules_are_rejected(schedule: str) -> None:
    """非法 cron 表达式应被拒绝。"""
    with pytest.raises(ValidationError):
        BeatScheduleItem(task="demo.echo", schedule=schedule)


def test_blank_beat_task_is_rejected() -> None:
    """定时任务名称不应为空白。"""
    with pytest.raises(ValidationError):
        BeatScheduleItem(task="   ", schedule="0 3 * * *")


def test_beat_schedule_item_defaults() -> None:
    """单条定时任务应提供默认参数。"""
    item = BeatScheduleItem(task="demo.echo", schedule="0 3 * * *")

    assert item.args == []
    assert item.kwargs == {}
    assert item.options == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("worker_concurrency", True),
        ("worker_prefetch_multiplier", False),
        ("result_expires_seconds", True),
        ("max_retries", False),
        ("retry_backoff_max", True),
    ],
)
def test_numeric_fields_reject_boolean_values(field: str, value: bool) -> None:
    """数值配置字段不应将布尔值转换为数字。"""
    with pytest.raises(ValidationError):
        CelerySettings(**{field: value})


@pytest.mark.parametrize("field", ["worker_concurrency", "worker_prefetch_multiplier"])
def test_non_positive_numeric_fields_are_rejected(field: str) -> None:
    """Celery 数值配置应遵守各自的下限。"""
    with pytest.raises(ValidationError):
        CelerySettings(**{field: 0})


def test_worker_concurrency_allows_none() -> None:
    """worker_concurrency 允许为空（交给 Celery 默认）。"""
    settings = CelerySettings(worker_concurrency=None)

    assert settings.worker_concurrency is None
