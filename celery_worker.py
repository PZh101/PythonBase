"""Celery worker + beat 启动入口（独立进程）。"""

import asyncio
import sys

from app.web import load_runtime_settings
from pkg.celery import (
    create_task_db_manager,
    dispose_task_db_manager,
    get_celery_app,
    set_task_db_manager,
)
from pkg.common.logging import configure_logging, get_logger

logger = get_logger(__name__)


def main() -> None:
    """启动 Celery worker（可选 beat）。

    使用方式:
        在项目根目录运行：

        - ``uv run python celery_worker.py`` 启动 worker（不启用定时调度）。
        - ``APP_CELERY__BEAT_ENABLED=true uv run python celery_worker.py`` 同时启动 beat。
        - 也可使用标准 CLI（不注入任务数据库管理器）：
          ``uv run celery -A pkg.celery.app:celery_app worker --loglevel=INFO``
    """
    settings = load_runtime_settings()
    if not settings.celery.enabled:
        logger.warning("celery.enabled=false，跳过 worker 启动")
        return
    configure_logging(settings.logging)
    app = get_celery_app(settings)

    # Windows 不支持 prefork 池，自动回退 solo，避免启动报错。
    pool = settings.celery.worker_pool
    if pool is None and sys.platform == "win32":
        pool = "solo"
        logger.info("当前平台为 Windows，worker 池回退为 solo")

    manager = create_task_db_manager(settings.database)
    set_task_db_manager(manager)

    worker = app.Worker(
        app=app,
        pool=pool,
        loglevel=settings.logging.level,
        beat=settings.celery.beat.enabled,
    )
    try:
        worker.start()
    finally:
        asyncio.run(dispose_task_db_manager())


if __name__ == "__main__":
    main()
