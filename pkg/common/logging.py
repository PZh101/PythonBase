"""统一日志配置与获取入口。"""

import logging
import sys
from types import FrameType
from typing import Any, cast

from loguru import logger

from pkg.config import LoggingSettings


class InterceptHandler(logging.Handler):
    """将标准库 logging 日志转发到 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        """转发标准库日志记录。

        Args:
            record: 标准库日志记录。

        使用方式:
            由 `configure_logging()` 注册到 root logger 后自动调用。
        """
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame is not None and _is_logging_frame(frame):
            frame = cast(FrameType | None, frame.f_back)
            depth += 1

        logger.bind(logger_name=record.name).opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


def configure_logging(settings: LoggingSettings | None = None) -> None:
    """配置项目统一日志。

    Args:
        settings: 日志配置。不传时使用默认配置。

    使用方式:
        在 FastAPI 应用创建早期调用一次，后续业务代码通过 `get_logger(__name__)` 获取日志对象。
    """
    resolved_settings = settings or LoggingSettings()
    logger.remove()
    logger.add(
        sys.stderr,
        level=resolved_settings.level,
        format=resolved_settings.format,
        serialize=resolved_settings.serialize,
        enqueue=resolved_settings.enqueue,
        backtrace=resolved_settings.backtrace,
        diagnose=resolved_settings.diagnose,
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy"):
        standard_logger = logging.getLogger(logger_name)
        standard_logger.handlers = [InterceptHandler()]
        standard_logger.propagate = False


def get_logger(name: str) -> Any:
    """获取绑定模块名称的 loguru logger。

    Args:
        name: 调用方模块名，通常传入 `__name__`。

    Returns:
        已绑定 `logger_name` 的 loguru logger。
    """
    return logger.bind(logger_name=name)


def _is_logging_frame(frame: FrameType) -> bool:
    """判断调用帧是否属于 logging 模块自身。"""
    module_name = frame.f_globals.get("__name__", "")
    return module_name.startswith("logging")
