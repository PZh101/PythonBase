"""Celery 示例任务测试（eager 模式，无需真实 Redis）。"""

import pytest
from celery.result import EagerResult

from pkg.celery import tasks as tasks_module


def test_demo_echo_returns_echo(celery_app) -> None:
    """demo.echo 应回显 payload。"""
    result = tasks_module.demo_echo.delay("hi")

    assert isinstance(result, EagerResult)
    assert result.get() == "echo:hi"


def test_demo_flaky_succeeds_after_retries(celery_app) -> None:
    """demo.flaky 前 N-1 次失败后应成功。"""
    result = tasks_module.demo_flaky.delay(attempts_until_success=2)

    assert result.get() == "success-after-2-attempts"
    assert result.state == "SUCCESS"


def test_demo_flaky_respects_max_retries(celery_app) -> None:
    """demo.flaky 超过 max_retries 应最终失败且不向上抛出。"""
    result = tasks_module.demo_flaky.delay(attempts_until_success=10)

    assert result.state == "FAILURE"
    assert result.result is not None


def test_demo_flaky_succeeds_immediately(celery_app) -> None:
    """attempts_until_success=1 时应一次成功。"""
    result = tasks_module.demo_flaky.delay(attempts_until_success=1)

    assert result.get() == "success-after-1-attempts"


def test_demo_db_write_runs_inside_transaction(celery_app, task_db_manager) -> None:
    """demo.db.write 应在事务边界内执行异步例程。"""
    tasks_module.demo_db_write.delay()

    assert task_db_manager.calls == [
        "initialize",
        "transaction_enter",
        "transaction_exit",
        "dispose",
    ]
