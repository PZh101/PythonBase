"""任务演示 API 路由（Celery 投递与结果查询）。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.task_demo.schemas import (
    TaskEnqueueRequest,
    TaskEnqueueResponse,
    TaskResultResponse,
)
from pkg.celery.app import get_celery_app
from pkg.common.api import ApiResponse
from pkg.common.exceptions import BadRequestException


def create_task_demo_router(
    auth_dependency: Callable[..., object],
) -> APIRouter:
    """创建任务演示路由。

    Args:
        auth_dependency: 返回 :class:`AuthContext` 的 FastAPI 认证依赖。

    Returns:
        已绑定认证依赖的 :class:`APIRouter`。
    """
    router = APIRouter(
        prefix="/task-demo",
        tags=["任务演示"],
        dependencies=[Depends(auth_dependency)],
    )

    @router.post("/enqueue", response_model=ApiResponse[TaskEnqueueResponse])
    async def enqueue_demo(
        body: TaskEnqueueRequest,
        request: Request,
    ) -> ApiResponse[TaskEnqueueResponse]:
        """投递 demo.echo 任务（apply_async 示例）。

        使用方式:
            ``POST /task-demo/enqueue``，请求体 ``{"payload": "hello"}``。
            返回的 ``task_id`` 可用于 ``GET /task-demo/result/{task_id}`` 查询结果。
        """
        app = get_celery_app(request.app.state.settings)
        # 惰性导入任务模块：按名称从应用的注册表取任务，保证与当前请求配置一致。
        import pkg.celery.tasks  # noqa: F401

        task = app.tasks["demo.echo"]
        async_result = task.apply_async(args=[body.payload])
        return ApiResponse(data=TaskEnqueueResponse(task_id=async_result.id))

    @router.get("/result/{task_id}", response_model=ApiResponse[TaskResultResponse])
    async def get_task_result(
        task_id: str,
        request: Request,
    ) -> ApiResponse[TaskResultResponse]:
        """读取任务结果（AsyncResult 示例）。

        使用方式:
            ``GET /task-demo/result/{task_id}``，其中 ``task_id`` 来自投递接口的返回值。
            未配置结果后端时返回 400 业务错误。

        Raises:
            BadRequestException: 未配置 ``result_backend``，无法查询任务结果。
        """
        app = get_celery_app(request.app.state.settings)
        # 未配置结果后端时 AsyncResult 使用 DisabledBackend，无法读取结果。
        if app.conf.result_backend is None:
            raise BadRequestException("未配置 result_backend，无法查询任务结果")
        result = app.AsyncResult(task_id)
        return ApiResponse(data=TaskResultResponse(
            task_id=task_id,
            state=result.state,
            result=result.result,
        ))

    return router
