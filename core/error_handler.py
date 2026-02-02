# -*- coding: utf-8 -*-
"""
错误处理模块

提供统一的错误处理、日志记录和用户友好的错误信息生成。
"""

import logging
from typing import Any

from astrbot.api import logger

from core.constants import ERROR_MESSAGES, ErrorSeverity, ErrorType


class ErrorHandler:
    """错误处理器类"""

    @staticmethod
    def handle_error(
        error_type: str,
        original_error: Exception,
        url: str | None = None,
        context: dict | None = None,
    ) -> str:
        """统一错误处理方法

        Args:
            error_type: 错误类型
            original_error: 原始异常对象
            url: 相关URL（可选）
            context: 额外上下文信息（可选）

        Returns:
            用户友好的错误信息字符串
        """
        error_config = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES["unknown_error"])
        error_message = error_config["message"]
        solution = error_config["solution"]
        severity = error_config["severity"]

        context_str = ErrorHandler._build_context_str(url, context)
        ErrorHandler._log_error(error_message, original_error, context_str, severity)
        return ErrorHandler._build_user_message(
            error_message, url, original_error, solution, error_type, severity
        )

    @staticmethod
    def _build_context_str(url: str | None, context: dict | None) -> str:
        """构建上下文信息字符串"""
        context_info = []
        if url:
            context_info.append(f"URL: {url}")
        if context:
            context_info.extend([f"{key}: {value}" for key, value in context.items()])
        return " | ".join(context_info)

    @staticmethod
    def _log_error(
        error_message: str,
        original_error: Exception,
        context_str: str,
        severity: str,
    ) -> None:
        """记录错误日志"""
        log_message = f"{error_message}: {str(original_error)}"
        if context_str:
            log_message += f" ({context_str})"

        log_levels = {
            ErrorSeverity.INFO: logger.info,
            ErrorSeverity.WARNING: logger.warning,
            ErrorSeverity.ERROR: logger.error,
            ErrorSeverity.CRITICAL: logger.critical,
        }
        log_levels[severity](log_message, exc_info=True)

    @staticmethod
    def _build_user_message(
        error_message: str,
        url: str | None,
        original_error: Exception,
        solution: str,
        error_type: str,
        severity: str,
    ) -> str:
        """构建用户友好的错误信息"""
        error_detail = str(original_error)
        if len(error_detail) > 100:
            error_detail = error_detail[:100] + "..."

        user_message = [
            f"❌ {error_message}",
            f"🔗 相关链接: {url}" if url else None,
            f"📋 错误详情: {error_detail}",
            f"💡 建议解决方案: {solution}",
        ]

        if severity in [ErrorSeverity.ERROR, ErrorSeverity.CRITICAL]:
            user_message.extend(
                [f"⚠️  错误类型: {error_type}", f"🔴 严重程度: {severity.upper()}"]
            )

        return "\n".join([msg for msg in user_message if msg is not None])

    @staticmethod
    def get_error_type(exception: Exception) -> str:
        """根据异常类型获取对应的错误类型

        Args:
            exception: 异常对象

        Returns:
            错误类型字符串
        """
        exception_type = type(exception).__name__
        exception_msg = str(exception).lower()
        exception_type_lower = exception_type.lower()

        # 按优先级检查各类错误
        error_type = (
            ErrorHandler._check_network_errors(
                exception, exception_type_lower, exception_msg
            )
            or ErrorHandler._check_parsing_errors(exception_type_lower, exception_msg)
            or ErrorHandler._check_llm_errors(exception_type_lower, exception_msg)
            or ErrorHandler._check_screenshot_errors(
                exception_type_lower, exception_msg
            )
            or ErrorHandler._check_cache_errors(exception_type_lower, exception_msg)
            or ErrorHandler._check_config_errors(exception_type_lower, exception_msg)
            or ErrorHandler._check_permission_errors(
                exception_type_lower, exception_msg
            )
            or ErrorHandler._check_other_errors(exception_type_lower, exception_msg)
            or ErrorType.UNKNOWN_ERROR
        )
        return error_type

    @staticmethod
    def _check_network_errors(
        exception: Exception, exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查网络相关错误"""
        from httpx import ConnectError, HTTPError, TimeoutException

        if isinstance(exception, HTTPError):
            if isinstance(exception, TimeoutException):
                return ErrorType.NETWORK_TIMEOUT
            if isinstance(exception, ConnectError):
                return ErrorType.NETWORK_CONNECTION
            return ErrorType.NETWORK_ERROR

        if "timeout" in exception_type_lower or "timeout" in exception_msg:
            return ErrorType.NETWORK_TIMEOUT
        if "connect" in exception_type_lower or "connection" in exception_msg:
            return ErrorType.NETWORK_CONNECTION
        if "network" in exception_type_lower or "http" in exception_type_lower:
            return ErrorType.NETWORK_ERROR
        return None

    @staticmethod
    def _check_parsing_errors(
        exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查解析相关错误"""
        if (
            "parse" in exception_type_lower
            or "soup" in exception_type_lower
            or "lxml" in exception_type_lower
        ):
            return ErrorType.HTML_PARSING
        if "empty" in exception_msg or "none" in exception_msg or "null" in exception_msg:
            return ErrorType.CONTENT_EMPTY
        if "parse" in exception_msg:
            return ErrorType.PARSING_ERROR
        return None

    @staticmethod
    def _check_llm_errors(
        exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查LLM相关错误"""
        if "llm" in exception_type_lower or "llm" in exception_msg:
            return ErrorType.LLM_ERROR
        if "generate" in exception_type_lower or "generate" in exception_msg:
            return ErrorType.LLM_ERROR
        if "timeout" in exception_msg and "llm" in exception_msg:
            return ErrorType.LLM_TIMEOUT
        if "invalid" in exception_msg or "format" in exception_msg:
            return ErrorType.LLM_INVALID_RESPONSE
        if "permission" in exception_msg or "auth" in exception_msg or "key" in exception_msg:
            return ErrorType.LLM_PERMISSION
        return None

    @staticmethod
    def _check_screenshot_errors(
        exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查截图相关错误"""
        if "screenshot" in exception_type_lower or "screenshot" in exception_msg:
            return ErrorType.SCREENSHOT_ERROR
        if "browser" in exception_type_lower or "playwright" in exception_type_lower:
            return ErrorType.BROWSER_ERROR
        return None

    @staticmethod
    def _check_cache_errors(
        exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查缓存相关错误"""
        if "cache" in exception_type_lower or "cache" in exception_msg:
            return ErrorType.CACHE_ERROR
        if "write" in exception_msg or "save" in exception_msg:
            return ErrorType.CACHE_WRITE
        if "read" in exception_msg or "load" in exception_msg:
            return ErrorType.CACHE_READ
        return None

    @staticmethod
    def _check_config_errors(
        exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查配置相关错误"""
        if "config" in exception_type_lower or "setting" in exception_type_lower:
            return ErrorType.CONFIG_ERROR
        if "invalid" in exception_msg:
            return ErrorType.CONFIG_INVALID
        return None

    @staticmethod
    def _check_permission_errors(
        exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查权限相关错误"""
        if "permission" in exception_type_lower or "auth" in exception_type_lower:
            return ErrorType.PERMISSION_ERROR
        if "blocked" in exception_msg or "deny" in exception_msg:
            return ErrorType.DOMAIN_BLOCKED
        return None

    @staticmethod
    def _check_other_errors(
        exception_type_lower: str, exception_msg: str
    ) -> str | None:
        """检查其他错误"""
        if "internal" in exception_type_lower or "internal" in exception_msg:
            return ErrorType.INTERNAL_ERROR
        return None