"""任务演示 API 模型。"""

from typing import Any

from pkg.common.api import BaseSchema


class TaskEnqueueRequest(BaseSchema):
    """投递任务请求。"""

    payload: str


class TaskEnqueueResponse(BaseSchema):
    """投递任务响应。"""

    task_id: str


class TaskResultResponse(BaseSchema):
    """任务结果查询响应。"""

    task_id: str
    state: str
    result: Any | None = None
