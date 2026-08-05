"""统一日志配置测试。"""

import logging

from loguru import logger

from pkg.common.logging import InterceptHandler, configure_logging, get_logger
from pkg.config import LoggingSettings


def test_configure_logging_replaces_loguru_handlers() -> None:
    """配置日志时应注册可用的 loguru 输出处理器。"""
    configure_logging(LoggingSettings(level="DEBUG"))

    assert logger._core.handlers


def test_standard_logging_is_intercepted() -> None:
    """标准库 logging 应被转发到 loguru。"""
    configure_logging(LoggingSettings(level="INFO"))

    assert any(isinstance(handler, InterceptHandler) for handler in logging.getLogger().handlers)


def test_get_logger_binds_logger_name() -> None:
    """获取日志对象时应绑定业务模块名称。"""
    bound_logger = get_logger("tests.example")

    assert bound_logger._options[-1]["logger_name"] == "tests.example"
