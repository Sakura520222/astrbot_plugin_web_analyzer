"""
网页截图插件核心模块
"""

from .cache import ScreenshotCache, build_cache_key
from .capture_pipeline import CaptureOutcome, CapturePipeline, CaptureSettings
from .config_loader import ConfigLoader
from .constants import ERROR_MESSAGES, ErrorSeverity, ErrorType
from .content_fetcher import ContentFetcher, ContentResult, FetchError
from .error_handler import ErrorHandler
from .messaging import MessageHelpers
from .screenshot import ScreenshotError, ScreenshotService
from .urls import (
    extract_urls,
    is_domain_allowed,
    is_valid_url,
    normalize_url,
    parse_domain_list,
    parse_group_list,
)

__all__ = [
    "CaptureOutcome",
    "CapturePipeline",
    "CaptureSettings",
    "ContentFetcher",
    "ContentResult",
    "ConfigLoader",
    "ErrorHandler",
    "ErrorType",
    "ErrorSeverity",
    "ERROR_MESSAGES",
    "FetchError",
    "MessageHelpers",
    "ScreenshotCache",
    "ScreenshotError",
    "ScreenshotService",
    "build_cache_key",
    "extract_urls",
    "is_domain_allowed",
    "is_valid_url",
    "normalize_url",
    "parse_domain_list",
    "parse_group_list",
]
