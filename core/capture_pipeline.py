"""
截图流程编排模块

自动识别与 /网页截图 共用同一条流水线：
URL 校验 → 访问规则 → 缓存命中 → 截图 → 裁剪 → 写缓存 → 结果整理。
批量处理受并发上限约束，交付由调用方完成。
"""

import asyncio
from dataclasses import dataclass

from astrbot.api import logger

from .cache import ScreenshotCache, build_cache_key
from .error_handler import ErrorHandler
from .screenshot import ScreenshotService
from .urls import is_domain_allowed, is_valid_url, normalize_url


@dataclass
class CaptureOutcome:
    """单个 URL 的截图结果。"""

    url: str  # 请求的 URL
    ok: bool = False
    error: str = ""  # 失败时的用户可读原因
    final_url: str = ""  # 页面跳转后的最终地址
    title: str = ""  # 页面标题
    screenshot: bytes | None = None  # 原图数据（可能已裁剪）
    thumbnail: bytes | None = None  # 卡片缩略图
    cache_id: str = ""  # 缓存键，供页面预览与卡片使用
    cached: bool = False  # 是否命中缓存
    source: str = ""  # 触发来源（command/auto/tool）


@dataclass
class CaptureSettings:
    """一次批量截图使用的参数（来自插件配置）。"""

    width: int = 1280
    height: int = 720
    full_page: bool = False
    format: str = "jpeg"
    quality: int = 80
    wait_strategy: str = "fixed"
    wait_time: int = 2000
    enable_crop: bool = False
    crop_area: tuple = (0, 0, 1280, 720)

    def cache_params(self) -> dict:
        """返回参与缓存键的参数字典。"""
        return {
            "width": self.width,
            "height": self.height,
            "full_page": self.full_page,
            "format": self.format,
            "quality": self.quality,
            "wait_strategy": self.wait_strategy,
            "wait_time": self.wait_time,
        }


class CapturePipeline:
    """截图流水线。"""

    def __init__(
        self,
        screenshot_service: ScreenshotService,
        cache: ScreenshotCache,
        max_concurrency: int = 5,
    ):
        """初始化流水线。

        Args:
            screenshot_service: 截图服务。
            cache: 截图缓存。
            max_concurrency: 批量处理并发上限。
        """
        self.screenshot_service = screenshot_service
        self.cache = cache
        self.max_concurrency = max(1, min(20, int(max_concurrency)))

    def apply_runtime_config(self, settings: dict) -> None:
        """应用运行中的并发配置。"""
        if "max_concurrency" in settings:
            self.max_concurrency = max(1, min(20, int(settings["max_concurrency"])))

    def filter_urls(
        self,
        urls: list[str],
        allowed_domains: list[str],
        blocked_domains: list[str],
        unify_www: bool = False,
        allow_local: bool = False,
    ) -> list[str]:
        """校验、去重并按访问规则过滤 URL 列表。"""
        valid = {
            url.strip().strip("`")
            for url in urls
            if url and is_valid_url(url.strip().strip("`"), allow_local)
        }
        normalized = []
        seen = set()
        for url in sorted(valid):
            normalized_url = normalize_url(url, unify_www)
            if normalized_url in seen:
                continue
            seen.add(normalized_url)
            if is_domain_allowed(normalized_url, allowed_domains, blocked_domains):
                normalized.append(normalized_url)
            else:
                logger.info(f"URL 不在允许访问的域名内，跳过: {normalized_url}")
        return normalized

    async def capture_batch(
        self, urls: list[str], settings: CaptureSettings
    ) -> list[CaptureOutcome]:
        """并发截取一批 URL，返回与输入顺序一致的结果列表。"""
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _one(url: str) -> CaptureOutcome:
            async with semaphore:
                return await self.capture_one(url, settings)

        outcomes = await asyncio.gather(*(_one(url) for url in urls))
        return list(outcomes)

    async def capture_one(
        self, url: str, settings: CaptureSettings, skip_cache: bool = False
    ) -> CaptureOutcome:
        """截取单个 URL：缓存优先，未命中时截图并写缓存。"""
        cache_key = build_cache_key(url, settings.cache_params())
        outcome = CaptureOutcome(url=url, cache_id=cache_key)

        if not skip_cache:
            entry = self.cache.get(cache_key)
            if entry is not None:
                screenshot = self.cache.get_screenshot(cache_key)
                result = entry.get("result", {})
                if screenshot:
                    outcome.ok = True
                    outcome.cached = True
                    outcome.screenshot = screenshot
                    outcome.title = result.get("title", "")
                    outcome.final_url = result.get("final_url", "") or url
                    logger.info(f"命中截图缓存: {url}")
                    return outcome

        try:
            screenshot, title, final_url = await self.screenshot_service.capture(
                url=url,
                width=settings.width,
                height=settings.height,
                full_page=settings.full_page,
                format=settings.format,
                quality=settings.quality,
                wait_time=settings.wait_time,
                wait_strategy=settings.wait_strategy,
            )
            if settings.enable_crop:
                try:
                    screenshot = ScreenshotService.crop_screenshot(
                        screenshot, tuple(settings.crop_area)
                    )
                except Exception as crop_error:
                    logger.warning(
                        f"截图裁剪失败，使用原始截图: {url}, 错误: {crop_error}"
                    )
            outcome.ok = True
            outcome.screenshot = screenshot
            outcome.title = title
            outcome.final_url = final_url or url
            outcome.thumbnail = ScreenshotService.make_thumbnail(screenshot)
            self.cache.put(
                cache_key,
                url,
                settings.cache_params(),
                {
                    "title": outcome.title,
                    "final_url": outcome.final_url,
                    "has_screenshot": True,
                },
                screenshot,
            )
            return outcome
        except Exception as e:
            error_type = ErrorHandler.classify(e)
            outcome.error = ErrorHandler.handle_error(error_type, e, url)
            return outcome
