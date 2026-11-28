"""
错误处理模块

把异常归类为用户可读的错误提示，并按严重程度记录日志。
"""

from astrbot.api import logger

from .constants import ERROR_MESSAGES, ErrorSeverity, ErrorType


class ErrorHandler:
    """错误处理器"""

    @staticmethod
    def handle_error(
        error_type: str,
        original_error: Exception,
        url: str | None = None,
    ) -> str:
        """生成用户可读的错误消息并记录日志。

        Args:
            error_type: ErrorType 中的错误类型常量。
            original_error: 原始异常。
            url: 相关 URL（可选）。

        Returns:
            以 ❌ 开头的错误消息文本。
        """
        config = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES[ErrorType.UNKNOWN_ERROR])
        message = config["message"]
        solution = config["solution"]
        severity = config["severity"]

        context = f" (URL: {url})" if url else ""
        logger.log(
            _LOG_LEVELS.get(severity, logger.warning),
            f"{message}: {original_error}{context}",
            exc_info=original_error if original_error.__traceback__ else None,
        )

        detail = str(original_error)
        if len(detail) > 120:
            detail = detail[:120] + "..."
        lines = [f"❌ {message}"]
        if url:
            lines.append(f"🔗 链接: {url}")
        lines.append(f"💡 {solution}")
        if detail:
            lines.append(f"详情: {detail}")
        return "\n".join(lines)

    @staticmethod
    def classify(exception: Exception) -> str:
        """按异常类型与消息归类为 ErrorType 常量。"""
        type_name = type(exception).__name__.lower()
        message = str(exception).lower()

        if isinstance(exception, _NETWORK_TIMEOUT_ERRORS):
            return ErrorType.NETWORK_TIMEOUT
        if isinstance(exception, _NETWORK_CONNECT_ERRORS):
            return ErrorType.NETWORK_CONNECTION

        if "screenshot" in type_name or "screenshot" in message:
            return ErrorType.SCREENSHOT_ERROR
        if "browser" in type_name or "browser" in message:
            return ErrorType.BROWSER_ERROR
        if "limit" in type_name or "limit" in message or "pixel" in message:
            return ErrorType.SCREENSHOT_LIMIT
        if "timeout" in type_name or "timed out" in message:
            return ErrorType.NETWORK_TIMEOUT
        if "connect" in type_name or "connection" in message:
            return ErrorType.NETWORK_CONNECTION
        if "cache" in type_name or "cache" in message:
            return ErrorType.CACHE_ERROR
        if "domain" in message and ("block" in message or "allow" in message):
            return ErrorType.DOMAIN_BLOCKED
        if "http" in type_name or "network" in type_name or "fetch" in type_name:
            return ErrorType.NETWORK_ERROR
        return ErrorType.UNKNOWN_ERROR


_LOG_LEVELS = {
    ErrorSeverity.INFO: 20,  # logging.INFO
    ErrorSeverity.WARNING: 30,  # logging.WARNING
    ErrorSeverity.ERROR: 40,  # logging.ERROR
}

try:  # httpx 由宿主提供
    from httpx import ConnectError as _ConnectError
    from httpx import TimeoutException as _TimeoutException

    _NETWORK_TIMEOUT_ERRORS: tuple = (_TimeoutException,)
    _NETWORK_CONNECT_ERRORS: tuple = (_ConnectError,)
except ImportError:  # pragma: no cover - 宿主总是提供 httpx
    _NETWORK_TIMEOUT_ERRORS = ()
    _NETWORK_CONNECT_ERRORS = ()
