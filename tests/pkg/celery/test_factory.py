"""Celery 应用工厂测试。"""

from celery.schedules import crontab

from pkg.celery.app import create_celery_app, get_celery_app, reset_celery_app
from pkg.config.models import BeatSettings, CelerySettings, RuntimeSettings


def _runtime(celery: CelerySettings) -> RuntimeSettings:
    """构造以给定 Celery 配置为主的运行时配置。"""
    return RuntimeSettings(celery=celery)


def test_create_celery_app_maps_conf() -> None:
    """工厂应按配置映射 Celery conf 键。"""
    app = create_celery_app(_runtime(CelerySettings(
        broker_url="redis://127.0.0.1:6379/5",
        task_serializer="json",
        timezone="UTC",
        enable_utc=True,
        max_retries=5,
        worker_concurrency=4,
        worker_pool="solo",
    )))

    assert app.conf.broker_url == "redis://127.0.0.1:6379/5"
    assert app.conf.task_serializer == "json"
    assert app.conf.timezone == "UTC"
    assert app.conf.enable_utc is True
    assert app.conf.worker_concurrency == 4
    assert app.conf.worker_pool == "solo"
    assert app.conf.task_default_max_retries == 5
    assert app.conf.task_retry_backoff is True
    assert app.conf.task_retry_backoff_max == 600
    assert app.conf.task_retry_jitter is True


def test_create_celery_app_default_conf() -> None:
    """工厂默认配置应映射默认值。"""
    app = create_celery_app(_runtime(CelerySettings()))

    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.task_track_started is True
    assert app.conf.task_always_eager is False
    assert app.conf.task_store_eager_result is True
    assert app.conf.result_backend == "redis://127.0.0.1:6379/1"
    assert app.conf.result_expires == 86_400
    assert app.conf.broker_connection_retry_on_startup is True


def test_result_backend_none_leaves_conf_unset() -> None:
    """result_backend=None 时不应在配置表中设置该键。"""
    app = create_celery_app(_runtime(CelerySettings(result_backend=None)))

    assert "result_backend" not in app.conf.table()
    # Celery 默认值为 None
    assert app.conf.result_backend is None


def test_eager_mode_omits_result_backend() -> None:
    """eager 模式不应设置结果后端（避免 apply_async 连接外部 backend）。"""
    app = create_celery_app(_runtime(CelerySettings(
        task_always_eager=True,
        result_backend="redis://127.0.0.1:6379/1",
    )))

    assert "result_backend" not in app.conf.table()


def test_non_eager_mode_sets_result_backend() -> None:
    """非 eager 模式应设置结果后端。"""
    app = create_celery_app(_runtime(CelerySettings(result_backend="redis://127.0.0.1:6379/1")))

    assert app.conf.table()["result_backend"] == "redis://127.0.0.1:6379/1"


def test_worker_pool_none_leaves_conf_unset() -> None:
    """worker_pool=None 时不应在配置表中设置该键。"""
    app = create_celery_app(_runtime(CelerySettings()))

    assert "worker_pool" not in app.conf.table()


def test_beat_disabled_by_default() -> None:
    """默认不启用 beat_schedule。"""
    app = create_celery_app(_runtime(CelerySettings()))

    assert "beat_schedule" not in app.conf.table()


def test_beat_schedule_maps_cron_to_crontab() -> None:
    """启用 beat 时 cron 字符串应正确转换为 crontab。"""
    app = create_celery_app(_runtime(CelerySettings(
        beat=BeatSettings(
            enabled=True,
            schedules=(
                {
                    "task": "demo.echo",
                    "schedule": "30 3 * * 1",
                    "args": ["daily-echo"],
                    "kwargs": {"channel": "ops"},
                },
            ),
        ),
    )))

    schedule = app.conf.beat_schedule
    assert "demo.echo" in schedule
    entry = schedule["demo.echo"]
    assert entry["task"] == "demo.echo"
    assert entry["args"] == ["daily-echo"]
    assert entry["kwargs"] == {"channel": "ops"}
    cron = entry["schedule"]
    assert isinstance(cron, crontab)
    assert cron.minute == {30}
    assert cron.hour == {3}
    assert cron.day_of_week == {1}
    assert cron.day_of_month == set(range(1, 32))
    assert cron.month_of_year == set(range(1, 13))


def test_get_celery_app_caches_single_instance() -> None:
    """get_celery_app 应缓存并返回同一实例。"""
    reset_celery_app()
    try:
        settings = _runtime(CelerySettings(task_always_eager=True))
        first = get_celery_app(settings)
        second = get_celery_app(settings)
        assert first is second
    finally:
        reset_celery_app()


def test_reset_celery_app_clears_cache() -> None:
    """reset_celery_app 应清空进程级实例。"""
    reset_celery_app()
    try:
        settings = _runtime(CelerySettings())
        first = get_celery_app(settings)
        reset_celery_app()
        second = get_celery_app(settings)
        assert first is not second
    finally:
        reset_celery_app()


def test_include_registers_tasks_module() -> None:
    """include 应注册到 Celery 应用。"""
    app = create_celery_app(_runtime(CelerySettings()))

    assert "pkg.celery.tasks" in app.conf.include
