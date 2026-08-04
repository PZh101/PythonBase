"""配置模块异常定义。"""


class ConfigError(Exception):
    """配置模块异常基类。"""


class ConfigFileNotFoundError(ConfigError):
    """配置文件不存在。"""


class ConfigParseError(ConfigError):
    """配置文件格式错误。"""


class InvalidProfileError(ConfigError):
    """profile 名称不合法。"""


class ProfileNotFoundError(ConfigError):
    """指定 profile 不存在。"""


class ConfigEnvironmentError(ConfigError):
    """环境变量配置路径错误。"""


class ConfigValidationError(ConfigError):
    """配置字段校验失败。"""


class ConfigKeyError(ConfigError, KeyError):
    """运行时配置键不存在。"""


class ConfigNotInitializedError(ConfigError):
    """全局配置尚未初始化。"""


class ConfigAlreadyInitializedError(ConfigError):
    """配置已经初始化。"""
