"""E2E 测试专属 fixture"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pkg.common.exceptions import register_exception_handlers


@pytest.fixture(scope="session")
def app() -> FastAPI:
    """创建一个标准的 FastAPI 应用实例，已注册异常处理器"""
    _app = FastAPI()
    register_exception_handlers(_app)
    return _app


@pytest.fixture(scope="session")
def client(app: FastAPI) -> TestClient:
    """返回一个绑定到测试应用的 TestClient

    使用 raise_server_exceptions=False 避免 ServerErrorMiddleware
    兜底异常时重新抛出异常导致测试失败。
    """
    return TestClient(app, raise_server_exceptions=False)