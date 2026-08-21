"""任务演示路由测试（eager 模式，无需真实 Redis）。"""

import sys
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.task_demo.routes import create_task_demo_router
from pkg.celery.app import reset_celery_app
from pkg.common.exceptions import register_exception_handlers
from pkg.config import CelerySettings, RuntimeSettings


async def _noop_auth():
    """绕开 IAM DB 查询的认证桩。"""
    return None


def _make_client(celery: CelerySettings) -> TestClient:
    """构造注册了异常处理器的测试应用与客户端。"""
    reset_celery_app()
    settings = RuntimeSettings(celery=celery)
    app = FastAPI()
    register_exception_handlers(app)
    app.state.settings = settings
    app.include_router(create_task_demo_router(_noop_auth))
    return TestClient(app)


def test_enqueue_works_in_eager_mode() -> None:
    """eager 模式下应能投递任务并返回 task_id。"""
    client = _make_client(CelerySettings(
        task_always_eager=True,
        task_store_eager_result=True,
        result_backend=None,
    ))
    try:
        response = client.post("/task-demo/enqueue", json={"payload": "hello"})
        assert response.status_code == 200
        assert response.json()["code"] == 0
        assert response.json()["data"]["taskId"]
    finally:
        reset_celery_app()


def test_result_without_backend_returns_bad_request() -> None:
    """未配置结果后端时查询结果应返回 400 业务错误。"""
    client = _make_client(CelerySettings(
        task_always_eager=True,
        task_store_eager_result=True,
        result_backend=None,
    ))
    try:
        response = client.get("/task-demo/result/some-task-id")
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == 40000
        assert "result_backend" in body["msg"]
    finally:
        reset_celery_app()


def test_enqueue_reads_app_from_request_state() -> None:
    """路由应从请求状态读取配置，而非进程级默认应用。

    进程级默认应用由磁盘 application.yml 构建（非 eager、带 Redis backend）；
    若路由误用默认应用，投递会尝试连接 Redis 而失败。
    """
    with patch.dict(sys.modules, {}):
        # 确保没有其他模块先构建默认应用：直接 reset 后构建 eager 应用。
        reset_celery_app()
        client = _make_client(CelerySettings(
            task_always_eager=True,
            task_store_eager_result=True,
            result_backend=None,
        ))
    try:
        response = client.post("/task-demo/enqueue", json={"payload": "x"})
        assert response.status_code == 200
        assert response.json()["code"] == 0
    finally:
        reset_celery_app()
