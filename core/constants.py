"""
常量定义模块

定义插件中使用的错误类型与错误提示文案。
"""

from typing import Any


class ErrorType:
    """错误类型常量"""

    # 网络相关
    NETWORK_ERROR = "network_error"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_CONNECTION = "network_connection"

    # 截图相关
    SCREENSHOT_ERROR = "screenshot_error"
    BROWSER_ERROR = "browser_error"
    SCREENSHOT_LIMIT = "screenshot_limit"

    # 缓存相关
    CACHE_ERROR = "cache_error"

    # 访问规则相关
    DOMAIN_BLOCKED = "domain_blocked"

    # 其他错误
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity:
    """错误严重程度常量"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


ERROR_MESSAGES: dict[str, dict[str, Any]] = {
    "network_error": {
        "message": "网页访问失败",
        "solution": "请检查链接或网络连接，或稍后重试",
        "severity": ErrorSeverity.ERROR,
    },
    "network_timeout": {
        "message": "网页访问超时",
        "solution": "目标网站响应缓慢，请稍后重试",
        "severity": ErrorSeverity.ERROR,
    },
    "network_connection": {
        "message": "网络连接失败",
        "solution": "无法连接到目标网站，请检查网络或链接是否可访问",
        "severity": ErrorSeverity.ERROR,
    },
    "screenshot_error": {
        "message": "网页截图失败",
        "solution": "请检查浏览器配置或网络连接，或稍后重试",
        "severity": ErrorSeverity.WARNING,
    },
    "browser_error": {
        "message": "浏览器操作失败",
        "solution": "浏览器启动或连接失败，请检查系统浏览器配置",
        "severity": ErrorSeverity.ERROR,
    },
    "screenshot_limit": {
        "message": "截图超出限制",
        "solution": "页面过长或分辨率过大，请关闭整页截图或调整视口尺寸",
        "severity": ErrorSeverity.WARNING,
    },
    "cache_error": {
        "message": "缓存操作失败",
        "solution": "请检查缓存目录权限或存储空间",
        "severity": ErrorSeverity.WARNING,
    },
    "domain_blocked": {
        "message": "该链接不在允许访问的范围内",
        "solution": "请在插件配置的访问规则中调整域名白名单或黑名单",
        "severity": ErrorSeverity.WARNING,
    },
    "unknown_error": {
        "message": "处理失败",
        "solution": "请查看日志获取详细信息，或稍后重试",
        "severity": ErrorSeverity.ERROR,
    },
}
