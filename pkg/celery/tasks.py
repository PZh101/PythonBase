"""示例 Celery 任务：普通任务、重试/退避演示、异步数据库写演示。"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pkg.celery.app import get_celery_app
from pkg.celery.runner import run_async_in_task
from pkg.common.logging import get_logger

logger = get_logger(__name__)

# 进程级 Celery 应用；任务通过它注册。
_celery = get_celery_app()


@_celery.task(name="demo.echo")
def demo_echo(payload: str) -> str:
    """回显示例任务。

    Args:
        payload: 需要回显的字符串。

    Returns:
        形如 ``echo:<payload>`` 的字符串。

    使用方式:
        ``demo_echo.delay("hello")`` 或 ``demo_echo.apply_async(args=["hello"])``。
    """
    logger.info("demo.echo 收到 {}", payload)
    return f"echo:{payload}"


@_celery.task(
    name="demo.flaky",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def demo_flaky(self, attempts_until_success: int = 2) -> str:
    """指数退避重试演示：第 N 次尝试成功。

    Args:
        attempts_until_success: 期望成功的尝试序号（前 N-1 次失败）。

    Returns:
        成功后返回包含尝试次数的字符串。

    使用方式:
        ``demo_flaky.delay(attempts_until_success=2)`` 演示第 2 次尝试成功。
    """
    attempt = self.request.retries + 1
    if attempt < attempts_until_success:
        logger.warning("demo.flaky 第 {} 次失败，准备重试", attempt)
        raise self.retry(countdown=2 ** self.request.retries)
    return f"success-after-{attempt}-attempts"


@_celery.task(name="demo.db.write")
def demo_db_write() -> None:
    """异步数据库访问演示任务。

    在任务内通过 ``run_async_in_task`` 于事务边界中执行异步例程；
    真实业务请将 ``_touch`` 替换为具体的写入逻辑。
    """

    async def _touch(db: AsyncSession) -> None:
        await db.execute(text("SELECT 1"))

    run_async_in_task(_touch)


__all__ = ["demo_db_write", "demo_echo", "demo_flaky"]
