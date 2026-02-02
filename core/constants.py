# -*- coding: utf-8 -*-
"""
常量定义模块

定义插件中使用的所有常量、枚举和配置字典。
"""

from typing import Any


class ErrorType:
    """错误类型枚举"""

    # 网络相关
    NETWORK_ERROR = "network_error"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_CONNECTION = "network_connection"

    # 解析相关
    PARSING_ERROR = "parsing_error"
    CONTENT_EMPTY = "content_empty"
    HTML_PARSING = "html_parsing"

    # LLM相关
    LLM_ERROR = "llm_error"
    LLM_TIMEOUT = "llm_timeout"
    LLM_INVALID_RESPONSE = "llm_invalid_response"
    LLM_PERMISSION = "llm_permission"

    # 截图相关
    SCREENSHOT_ERROR = "screenshot_error"
    BROWSER_ERROR = "browser_error"

    # 缓存相关
    CACHE_ERROR = "cache_error"
    CACHE_WRITE = "cache_write"
    CACHE_READ = "cache_read"

    # 配置相关
    CONFIG_ERROR = "config_error"
    CONFIG_INVALID = "config_invalid"

    # 权限相关
    PERMISSION_ERROR = "permission_error"
    DOMAIN_BLOCKED = "domain_blocked"

    # 其他错误
    UNKNOWN_ERROR = "unknown_error"
    INTERNAL_ERROR = "internal_error"


class ErrorSeverity:
    """错误严重程度枚举"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# 错误处理配置
ERROR_MESSAGES: dict[str, dict[str, Any]] = {
    "network_error": {
        "message": "网络请求失败",
        "solution": "请检查网络连接或URL是否正确，或尝试调整请求超时设置",
        "severity": ErrorSeverity.ERROR,
    },
    "network_timeout": {
        "message": "网络请求超时",
        "solution": "目标网站响应缓慢，请稍后重试或调整请求超时设置",
        "severity": ErrorSeverity.ERROR,
    },
    "network_connection": {
        "message": "网络连接失败",
        "solution": "无法连接到服务器，请检查网络连接或目标网站是否可访问",
        "severity": ErrorSeverity.ERROR,
    },
    "parsing_error": {
        "message": "网页内容解析失败",
        "solution": "该网页结构可能较为特殊，建议尝试其他分析方式",
        "severity": ErrorSeverity.WARNING,
    },
    "content_empty": {
        "message": "提取的内容为空",
        "solution": "目标网页可能没有可提取的内容，或内容格式不支持",
        "severity": ErrorSeverity.WARNING,
    },
    "html_parsing": {
        "message": "HTML解析错误",
        "solution": "网页HTML格式异常，无法正确解析",
        "severity": ErrorSeverity.ERROR,
    },
    "llm_error": {
        "message": "大语言模型分析失败",
        "solution": "请检查LLM配置是否正确，或尝试调整分析参数",
        "severity": ErrorSeverity.ERROR,
    },
    "llm_timeout": {
        "message": "大语言模型响应超时",
        "solution": "LLM响应缓慢，请稍后重试或调整LLM超时设置",
        "severity": ErrorSeverity.ERROR,
    },
    "llm_invalid_response": {
        "message": "大语言模型返回无效响应",
        "solution": "LLM返回格式异常，请检查LLM配置或稍后重试",
        "severity": ErrorSeverity.ERROR,
    },
    "llm_permission": {
        "message": "大语言模型权限不足",
        "solution": "请检查LLM API密钥或权限配置",
        "severity": ErrorSeverity.ERROR,
    },
    "screenshot_error": {
        "message": "网页截图失败",
        "solution": "请检查浏览器配置或网络连接，或尝试调整截图参数",
        "severity": ErrorSeverity.WARNING,
    },
    "browser_error": {
        "message": "浏览器操作失败",
        "solution": "浏览器初始化或操作失败，请检查浏览器配置或重启插件",
        "severity": ErrorSeverity.ERROR,
    },
    "cache_error": {
        "message": "缓存操作失败",
        "solution": "请检查缓存目录权限或存储空间",
        "severity": ErrorSeverity.WARNING,
    },
    "cache_write": {
        "message": "缓存写入失败",
        "solution": "无法写入缓存文件，请检查缓存目录权限或存储空间",
        "severity": ErrorSeverity.WARNING,
    },
    "cache_read": {
        "message": "缓存读取失败",
        "solution": "无法读取缓存文件，缓存可能已损坏",
        "severity": ErrorSeverity.WARNING,
    },
    "config_error": {
        "message": "配置错误",
        "solution": "请检查插件配置是否正确，或尝试重置配置",
        "severity": ErrorSeverity.ERROR,
    },
    "config_invalid": {
        "message": "配置无效",
        "solution": "插件配置格式无效，请检查配置项是否正确",
        "severity": ErrorSeverity.ERROR,
    },
    "permission_error": {
        "message": "权限不足",
        "solution": "请检查插件权限配置，或联系管理员获取权限",
        "severity": ErrorSeverity.ERROR,
    },
    "domain_blocked": {
        "message": "域名被阻止",
        "solution": "该域名已被加入黑名单，无法访问",
        "severity": ErrorSeverity.ERROR,
    },
    "unknown_error": {
        "message": "未知错误",
        "solution": "请检查日志获取详细信息，或尝试重启插件",
        "severity": ErrorSeverity.CRITICAL,
    },
    "internal_error": {
        "message": "内部错误",
        "solution": "插件内部发生错误，请检查日志或联系开发者",
        "severity": ErrorSeverity.CRITICAL,
    },
}