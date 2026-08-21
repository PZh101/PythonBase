"""Celery 应用工厂与进程级懒加载持有器。"""

from typing import Any

from celery import Celery
from celery.schedules import crontab

from pkg.config import BeatSettings, CelerySettings, RuntimeSettings

_celery_app: Celery | None = None


def create_celery_app(settings: RuntimeSettings) -> Celery:
    """按运行时配置构建 Celery 应用（纯函数，可重复调用、可单测）。

    Args:
        settings: 运行时配置，取其 ``celery`` 段构造应用。

    Returns:
        已应用全部 conf 的 :class:`Celery` 实例。

    注意:
        构建过程不会连接 Redis；broker 连接在 worker 启动或任务投递时才建立。
    """
    celery_settings = settings.celery
    app = Celery("pythonbase", include=tuple(celery_settings.include))
    app.conf.update(_build_conf(celery_settings))
    if celery_settings.beat.enabled:
        app.conf.beat_schedule = _build_beat_schedule(celery_settings.beat)
    return app


def _build_conf(settings: CelerySettings) -> dict[str, Any]:
    """把强类型配置映射为 Celery conf 键。"""
    conf: dict[str, Any] = {
        "broker_url": settings.broker_url,
        "task_serializer": settings.task_serializer,
        "timezone": settings.timezone,
        "enable_utc": settings.enable_utc,
        "worker_prefetch_multiplier": settings.worker_prefetch_multiplier,
        "task_acks_late": settings.task_acks_late,
        "task_reject_on_worker_lost": settings.task_reject_on_worker_lost,
        "task_track_started": settings.task_track_started,
        "task_always_eager": settings.task_always_eager,
        "task_eager_propagates": settings.task_eager_propagates,
        "task_store_eager_result": settings.task_store_eager_result,
        "broker_connection_retry_on_startup": settings.broker_connection_retry_on_startup,
        "result_expires": settings.result_expires_seconds,
        "task_default_max_retries": settings.max_retries,
        "task_retry_backoff": settings.retry_backoff,
        "task_retry_backoff_max": settings.retry_backoff_max,
        "task_retry_jitter": settings.retry_jitter,
    }
    if settings.worker_concurrency is not None:
        conf["worker_concurrency"] = settings.worker_concurrency
    if settings.worker_pool is not None:
        conf["worker_pool"] = settings.worker_pool
    if settings.result_backend is not None:
        # eager 模式任务在进程内执行并保存结果，无需也不应连接外部结果后端；
        # 否则 apply_async 仍会为 on_task_call 尝试连接 backend（如 Redis），
        # 在没有 broker 的本地/测试环境会直接失败。
        if not settings.task_always_eager:
            conf["result_backend"] = settings.result_backend
    return conf


def _build_beat_schedule(settings: BeatSettings) -> dict[str, dict[str, Any]]:
    """把强类型 cron 定义转换为 Celery beat_schedule 字典。

    注意:
        ``crontab`` 的字段位置与 cron 字符串不一致：cron 为 ``分 时 日 月 周``，
        而 ``crontab(minute, hour, day_of_week, day_of_month, month_of_year)``
        中 **day_of_week 在 day_of_month 之前**，必须按关键字拆分传参。
        各字段保留原始表达式（``*``、``*/n``、``a-b``、逗号列表），交由 crontab 解析。
    """
    schedule: dict[str, dict[str, Any]] = {}
    for item in settings.schedules:
        minute, hour, day_of_month, month, day_of_week = item.schedule.split()
        entry: dict[str, Any] = {
            "task": item.task,
            "schedule": crontab(
                minute=minute,
                hour=hour,
                day_of_week=day_of_week,
                day_of_month=day_of_month,
                month_of_year=month,
            ),
            "args": item.args,
            "kwargs": item.kwargs,
        }
        entry.update(item.options)
        schedule[item.task] = entry
    return schedule


def get_celery_app(settings: RuntimeSettings | None = None) -> Celery:
    """返回进程级 Celery 应用；首次调用时构建并缓存。

    Args:
        settings: 运行时配置。不传时从根目录 ``application.yml`` 加载（便于
            ``celery -A pkg.celery.app:celery_app`` 与任务模块直接使用）。

    Returns:
        进程级共享的 :class:`Celery` 实例。
    """
    global _celery_app
    if _celery_app is None:
        _celery_app = create_celery_app(settings if settings is not None else _load_settings())
    return _celery_app


def reset_celery_app() -> None:
    """清空进程级 Celery 应用（测试隔离用）。"""
    global _celery_app
    _celery_app = None


def _load_settings() -> RuntimeSettings:
    """从根目录配置加载 RuntimeSettings（pkg 层不依赖 app.web）。"""
    from pkg.config.loader import load_configuration

    loaded = load_configuration(".")
    return RuntimeSettings.model_validate(loaded.data)


# 供 `celery -A pkg.celery.app:celery_app worker` CLI 使用的模块属性。
celery_app = get_celery_app()


__all__ = [
    "celery_app",
    "create_celery_app",
    "get_celery_app",
    "reset_celery_app",
]
