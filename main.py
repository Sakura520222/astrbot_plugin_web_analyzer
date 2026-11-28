"""
AstrBot 网页截图插件

自动识别聊天中的网页链接并截图，支持 /网页截图 命令和两个助手工具：
- capture_webpage(urls)：截图并转发原图，向模型返回逐条结果；
- get_webpage_content(url)：按需读取网页正文（标题 + 可读文本）。

截图复用系统 Chrome / Edge / Chromium 的 CDP 连接，按 URL 与截图参数
命中缓存。网页分析功能已移除，/网页分析 保留为截图兼容别名。
"""

import asyncio
import base64

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register

from .core.cache import ScreenshotCache
from .core.capture_pipeline import (
    CaptureOutcome,
    CapturePipeline,
    CaptureSettings,
)
from .core.config_loader import ConfigLoader
from .core.content_fetcher import ContentFetcher, FetchError
from .core.messaging import MessageHelpers
from .core.screenshot import ScreenshotService
from .core.urls import extract_urls, is_domain_allowed, is_valid_url

PLUGIN_NAME = "astrbot_plugin_web_analyzer"

# 助手工具单次调用的链接数量上限
MAX_TOOL_URLS = 10
# 交互视图卡片最多携带的缩略图数量
MAX_CARD_THUMBNAILS = 5

USAGE_TEXT = (
    "【网页截图插件】\n"
    "用法：/网页截图 <链接1> [链接2] ...\n"
    "自动识别聊天中的网页链接并截图；也可让助手使用截图工具。\n"
    "管理员命令：/网页缓存 [clear]、/网页浏览器 [status|reload|cleanup]"
)


@register(
    "astrbot_plugin_web_analyzer",
    "Sakura520222",
    "自动识别聊天中的网页链接，支持命令和助手工具截图。可设置整页、视口、裁剪和加载等待方式。助手也可按需读取网页正文。",
    "2.0.0",
    "https://github.com/Sakura520222/astrbot_plugin_web_analyzer",
)
class WebScreenshotPlugin(Star):
    """网页截图插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        """初始化插件：加载配置、迁移旧配置并装配各组件。"""
        super().__init__(context)
        self.config = config
        ScreenshotService.reset_browser_session()

        settings = ConfigLoader.load(config)
        self._settings = settings
        self._apply_settings(settings)

        self.recall_tasks: list = []
        self._web_api_registered = False
        self._register_web_api(context)

        logger.info("网页截图插件初始化完成")

    def _apply_settings(self, settings: dict) -> None:
        """按配置装配各组件（插件加载时执行一次）。"""
        self.screenshot_service = ScreenshotService(
            timeout=settings["request_timeout_s"],
            user_agent=settings["user_agent"],
            proxy=settings["proxy"],
            hide_ip=settings["hide_ip"],
            sandbox_mode=settings["sandbox_mode"],
            max_browser_instances=settings["max_browser_instances"],
            screenshot_retry_count=settings["screenshot_retry_count"],
            enable_memory_monitor=settings["enable_memory_monitor"],
            memory_threshold_percent=settings["memory_threshold_percent"],
        )
        self.cache = ScreenshotCache(
            max_size=settings["max_cache_size"],
            expire_minutes=settings["cache_expire_time_min"],
            enabled=settings["enable_cache"],
        )
        self.pipeline = CapturePipeline(
            self.screenshot_service,
            self.cache,
            max_concurrency=settings["max_concurrency"],
        )
        self.content_fetcher = ContentFetcher(
            timeout=settings["request_timeout_s"],
            user_agent=settings["user_agent"],
            proxy=settings["proxy"],
            retry_count=settings["retry_count"],
            retry_delay_s=settings["retry_delay_s"],
            max_content_length=settings["max_content_length"],
            fetch_mode=settings["fetch_mode"],
            screenshot_service=self.screenshot_service,
            allow_local=settings["allow_local_addresses"],
        )

    def capture_settings(self) -> CaptureSettings:
        """从当前配置构造截图参数。"""
        s = self._settings
        return CaptureSettings(
            width=s["screenshot_width"],
            height=s["screenshot_height"],
            full_page=s["screenshot_full_page"],
            format=s["screenshot_format"],
            quality=s["screenshot_quality"],
            wait_strategy=s["screenshot_wait_strategy"],
            wait_time=s["screenshot_wait_ms"],
            enable_crop=s["enable_crop"],
            crop_area=s["crop_area"],
        )

    # ==================== 命令 ====================

    @filter.command("网页截图", alias={"网页分析"})
    async def screenshot_command(self, event: AstrMessageEvent):
        """手动截取网页：/网页截图 <链接...>（/网页分析 为兼容别名）"""
        urls = self._collect_urls(event.message_str)
        if not urls:
            yield event.plain_result(USAGE_TEXT)
            return

        blocked = self._is_group_blocked(event)
        if blocked:
            logger.info(f"群组 {blocked} 在黑名单中，跳过处理")
            return

        async for result in self._run_and_deliver(event, urls):
            yield result

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("网页缓存", alias={"web_cache", "清理缓存"})
    async def manage_cache(self, event: AstrMessageEvent):
        """管理截图缓存：/网页缓存 status | clear"""
        parts = event.message_str.strip().split()
        action = parts[1].lower() if len(parts) > 1 else ""

        if action == "clear":
            self.cache.clear()
            stats = self.cache.get_stats()
            await event.send(
                event.plain_result(
                    f"✅ 已清空所有截图缓存（当前缓存 {stats['total']} 条）"
                )
            )
            return

        s = self._settings
        stats = self.cache.get_stats()
        await event.send(
            event.plain_result(
                "当前截图缓存\n"
                f"- 总数: {stats['total']} 条，有效 {stats['valid']} 条，过期 {stats['expired']} 条\n"
                f"- 有效期: {s['cache_expire_time_min']} 分钟\n"
                f"- 条数上限: {s['max_cache_size']} 条\n"
                f"- 缓存功能: {'✅ 已启用' if s['enable_cache'] else '❌ 已禁用'}\n"
                "使用 /网页缓存 clear 清空所有缓存"
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("网页浏览器", alias={"web_browser", "浏览器管理"})
    async def manage_browser(self, event: AstrMessageEvent):
        """浏览器诊断：/网页浏览器 status | reload | cleanup"""
        parts = event.message_str.strip().split()
        action = parts[1].lower() if len(parts) > 1 else ""

        if action == "reload":
            self.screenshot_service._reset_browser_detection()
            await event.send(
                event.plain_result("✅ 已重置浏览器检测缓存，下次截图将重新检测")
            )
            return
        if action == "cleanup":
            result = await self.screenshot_service.uninstall_legacy_artifacts()
            await event.send(event.plain_result(result["message"]))
            return

        status = await self.screenshot_service.get_browser_status()
        if status["installed"]:
            text = (
                f"✅ 系统浏览器可用：{status['browser_type'] or '未知'}\n"
                f"版本: {status['browser_version'] or '未知'}\n"
                f"路径: {status['install_path']}\n"
                f"实例: 空闲 {status['browser_pool_size']} / "
                f"在用+启动中 {status['browser_instances']} / "
                f"上限 {status['max_browser_instances']}"
            )
        else:
            text = "❌ 未检测到系统浏览器，请安装 Chrome / Edge / Chromium"
        if status["skipped_browsers"]:
            skips = "\n".join(
                f"- {path}: {info['reason']}（约 {info['expires_in_min']} 分钟后重试）"
                for path, info in status["skipped_browsers"].items()
            )
            text += f"\n暂时跳过的浏览器:\n{skips}"
        await event.send(event.plain_result(text))

    # ==================== 自动识别 ====================

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_capture(self, event: AstrMessageEvent):
        """自动识别聊天中的网页链接并截图"""
        if not self._settings["auto_capture"]:
            return
        message_text = event.message_str.strip()
        if not message_text or message_text.startswith("/"):
            return
        if getattr(event, "command", None):
            return

        group_id = self._get_group_id(event)
        if group_id and group_id in self._settings["group_blacklist"]:
            return

        urls = self._collect_urls(message_text)
        if not urls:
            return

        if self._settings["handoff_to_model"]:
            # 不 yield 结果，事件继续传播给会话模型；结果直接发送
            async for _ in self._run_and_deliver(event, urls, send_directly=True):
                pass
        else:
            async for result in self._run_and_deliver(event, urls):
                yield result

    # ==================== 助手工具 ====================

    @filter.llm_tool(name="capture_webpage")
    async def capture_webpage_tool(self, event: AstrMessageEvent, urls):
        """截取一个或多个网页，把截图原图发送到当前会话，并返回每个链接的结果。

        Args:
            urls(array[string]): 要截图的网页URL列表。
        """
        if not isinstance(urls, list):
            urls = [urls]
        urls = [str(u).strip().strip("`") for u in urls if str(u).strip()]
        urls = list(dict.fromkeys(urls))[:MAX_TOOL_URLS]
        if not urls:
            return "没有提供有效的网页链接。"

        # 与自动识别和命令共用同一套校验：格式、SSRF 防护与访问规则
        s = self._settings
        checked = []
        rejected = []
        for url in urls:
            if is_valid_url(url, s["allow_local_addresses"]) and is_domain_allowed(
                url, s["allowed_domains"], s["blocked_domains"]
            ):
                checked.append(url)
            else:
                rejected.append(url)

        outcomes = []
        if checked:
            outcomes = await self.pipeline.capture_batch(
                checked, self.capture_settings()
            )
        async for _ in self._deliver(event, outcomes, send_directly=True):
            pass

        lines = []
        for index, outcome in enumerate(outcomes, 1):
            if outcome.ok:
                title = f"（{outcome.title}）" if outcome.title else ""
                lines.append(f"{index}. {outcome.url} — 截图已发送{title}")
            else:
                reason = outcome.error.splitlines()[0] if outcome.error else "未知错误"
                lines.append(f"{index}. {outcome.url} — 失败：{reason}")
        for url in rejected:
            lines.append(f"- {url} — 已拒绝：格式无效或不在允许访问的域名内")
        return "\n".join(lines) if lines else "没有可处理的网页链接。"

    @filter.llm_tool(name="get_webpage_content")
    async def get_webpage_content_tool(self, event: AstrMessageEvent, url: str) -> str:
        """读取网页的最终地址、标题和可读正文。适用于需要了解网页文字内容的场景。

        Args:
            url(string): 要读取的网页URL地址，支持http和https协议。
        """
        url = str(url).strip().strip("`")
        try:
            result = await self.content_fetcher.fetch(url)
        except FetchError as e:
            logger.info(f"正文抓取失败: {url}: {e}")
            return f"读取失败：{e}"
        except Exception as e:
            logger.warning(f"正文抓取异常: {url}: {e}")
            return f"读取失败：{e}"
        return ContentFetcher.format_tool_result(
            result, max_chars=self._settings["max_content_length"]
        )

    # ==================== 截图与交付 ====================

    def _collect_urls(self, message_text: str) -> list[str]:
        """从文本提取并按访问规则过滤 URL。"""
        s = self._settings
        raw_urls = extract_urls(
            message_text, s["enable_no_protocol_url"], s["default_protocol"]
        )
        if not raw_urls:
            return []
        return self.pipeline.filter_urls(
            raw_urls,
            s["allowed_domains"],
            s["blocked_domains"],
            s["enable_unified_domain"],
            s["allow_local_addresses"],
        )

    def _get_group_id(self, event: AstrMessageEvent) -> str | None:
        """从事件读取群聊 ID（可能为 None）。"""
        group_id = None
        if hasattr(event, "get_group_id"):
            try:
                group_id = event.get_group_id() or None
            except Exception:
                group_id = None
        return group_id

    def _is_group_blocked(self, event: AstrMessageEvent) -> str | None:
        """群聊在黑名单中时返回群 ID。"""
        group_id = self._get_group_id(event)
        if group_id and group_id in self._settings["group_blacklist"]:
            return group_id
        return None

    async def _run_and_deliver(
        self,
        event: AstrMessageEvent,
        urls: list[str],
        send_directly: bool = False,
    ):
        """发送提示消息、批量截图并交付结果。

        Args:
            send_directly: True 时通过 context.send_message 直接发送
               （自动识别且允许继续交给会话模型的场景），不产生 yield。

        Yields:
            需要通过 handler 返回的消息结果。
        """
        s = self._settings
        if len(urls) == 1:
            tip = f"正在截图: {urls[0]}"
        else:
            tip = f"正在截图 {len(urls)} 个网页链接..."
        processing_id, bot = await MessageHelpers.send_processing_message(
            event,
            tip,
            s["enable_processing_message"],
            s["enable_recall"],
            s["recall_type"],
            s["recall_time_s"],
            s["smart_recall_enabled"],
            self.recall_tasks,
        )

        outcomes = await self.pipeline.capture_batch(urls, self.capture_settings())
        if send_directly:
            async for _ in self._deliver(event, outcomes, send_directly=True):
                pass
        else:
            async for result in self._deliver(event, outcomes):
                yield result
        # smart 撤回模式在结果发出后撤回提示消息
        if processing_id and bot and s["recall_type"] == "smart":
            asyncio.create_task(
                MessageHelpers.recall_processing_message(
                    event,
                    processing_id,
                    bot,
                    s["recall_type"],
                    s["smart_recall_enabled"],
                    s["recall_time_s"],
                )
            )

    async def _deliver(
        self,
        event: AstrMessageEvent,
        outcomes: list[CaptureOutcome],
        send_directly: bool = False,
    ):
        """把截图结果发送到会话。

        支持交互视图的平台发送结果卡片（来源链接 + 缩略图），
        原图始终通过图片附件交付；其他平台发送常规图片消息。

        Yields:
            消息结果（send_directly 为 True 时不 yield）。
        """
        card_items = []
        for outcome in outcomes:
            if not outcome.ok:
                message = event.plain_result(outcome.error or "截图失败，请稍后重试。")
                if send_directly:
                    await self.context.send_message(event.unified_msg_origin, message)
                else:
                    yield message
                continue

            image = event.chain_result([Image.fromBytes(outcome.screenshot)])
            if send_directly:
                await self.context.send_message(event.unified_msg_origin, image)
            else:
                yield image

            if outcome.thumbnail is not None and len(card_items) < MAX_CARD_THUMBNAILS:
                card_items.append(
                    {
                        "url": outcome.url,
                        "final_url": outcome.final_url or outcome.url,
                        "title": outcome.title or outcome.url,
                        "thumb": "data:image/jpeg;base64,"
                        + base64.b64encode(outcome.thumbnail).decode(),
                    }
                )

        if card_items and self._supports_interactive_view(event):
            view = self._build_view_result(event, card_items)
            if view is not None:
                if send_directly:
                    await self._emit_view(event, view)
                else:
                    yield view

    async def _emit_view(self, event: AstrMessageEvent, view):
        """在直接发送路径上通过宿主 emit_view 发出交互卡片。

        ViewResult 不是消息链，不能交给 context.send_message（平台适配器
        只接受 MessageChain）；emit_view 是宿主管线发送卡片的同一通道。
        失败时静默跳过卡片——原图已通过图片附件送达。
        """
        try:
            from astrbot.core.chatui import emit_view

            await emit_view(event, __name__, view)
        except Exception as e:
            logger.debug(f"发送截图结果卡片失败（原图已发送，跳过卡片）: {e}")

    def _supports_interactive_view(self, event: AstrMessageEvent) -> bool:
        """平台声明支持交互视图且宿主提供 view_result 时返回 True。"""
        if not hasattr(event, "view_result"):
            return False
        meta = getattr(event, "platform_meta", None)
        return bool(getattr(meta, "support_ui_interaction", False))

    def _build_view_result(self, event: AstrMessageEvent, card_items: list):
        """构造截图结果卡片；宿主不支持时返回 None。"""
        try:
            return event.view_result(
                name="screenshot_card",
                data={"items": card_items},
                text="网页截图结果：" + "；".join(item["url"] for item in card_items),
            )
        except Exception as e:
            logger.debug(f"构造截图结果卡片失败，回退为普通消息: {e}")
            return None

    # ==================== Web API（只读 + 缓存管理） ====================

    def _register_web_api(self, context: Context):
        """注册管理面板的 Web API 路由。"""
        if self._web_api_registered:
            return
        self._web_api_registered = True
        prefix = f"/{PLUGIN_NAME}/dashboard"
        routes = [
            (f"{prefix}/overview", self._api_overview, ["GET"]),
            (f"{prefix}/cache", self._api_cache, ["GET"]),
            (f"{prefix}/cache/clear", self._api_cache_clear, ["POST"]),
            (f"{prefix}/cache/delete", self._api_cache_delete, ["POST"]),
            (f"{prefix}/cache/preview", self._api_cache_preview, ["GET"]),
            (f"{prefix}/rules", self._api_rules, ["GET"]),
            (f"{prefix}/browser", self._api_browser, ["GET"]),
            (f"{prefix}/browser/recheck", self._api_browser_recheck, ["POST"]),
            (f"{prefix}/browser/cleanup", self._api_browser_cleanup, ["POST"]),
        ]
        for path, handler, methods in routes:
            context.register_web_api(
                path, handler, methods, f"Dashboard: {path.rsplit('/', 1)[-1]}"
            )

    async def _api_overview(self):
        """管理面板概览：缓存统计、自动截图与浏览器状态摘要。"""
        from astrbot.api.web import json_response

        s = self._settings
        return json_response(
            {
                "cache_stats": self.cache.get_stats(),
                "auto_capture": s["auto_capture"],
                "handoff_to_model": s["handoff_to_model"],
                "screenshot": {
                    "width": s["screenshot_width"],
                    "height": s["screenshot_height"],
                    "full_page": s["screenshot_full_page"],
                    "format": s["screenshot_format"],
                    "quality": s["screenshot_quality"],
                    "wait_strategy": s["screenshot_wait_strategy"],
                    "wait_ms": s["screenshot_wait_ms"],
                    "crop_enabled": s["enable_crop"],
                },
                "max_concurrency": s["max_concurrency"],
            }
        )

    async def _api_cache(self):
        """缓存列表，支持按 URL 搜索。"""
        from astrbot.api.web import json_response, request

        query = request.query.get("query", "").strip()
        items = self.cache.list_entries(query)
        return json_response({"stats": self.cache.get_stats(), "items": items})

    async def _api_cache_clear(self):
        """清空全部缓存。"""
        from astrbot.api.web import json_response

        self.cache.clear()
        return json_response(
            {"message": "已清空所有截图缓存", "stats": self.cache.get_stats()}
        )

    async def _api_cache_delete(self):
        """删除一条缓存。"""
        from astrbot.api.web import json_response, request

        data = await request.json(default={})
        if not isinstance(data, dict):
            return json_response({"error": "请求必须为 JSON 对象"}, status_code=400)
        key = str(data.get("id", "")).strip()
        if not key:
            return json_response({"error": "缺少 id 参数"}, status_code=400)
        self.cache.delete(key)
        return json_response({"message": "已删除缓存"})

    async def _api_cache_preview(self):
        """返回缓存截图的 data URL，供面板预览。"""
        import base64

        from astrbot.api.web import json_response, request

        key = request.query.get("id", "").strip()
        if not key or not key.isalnum():
            return json_response({"error": "无效的缓存 id"}, status_code=400)
        path = self.cache.get_file_path(key)
        if not path:
            return json_response({"error": "截图不存在"}, status_code=404)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return json_response({"error": "截图读取失败"}, status_code=500)
        mime = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
        return json_response(
            {"data_url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}
        )

    async def _api_rules(self):
        """访问规则（生效配置，只读展示）。"""
        from astrbot.api.web import json_response

        s = self._settings
        return json_response(
            {
                "allowed_domains": s["allowed_domains"],
                "blocked_domains": s["blocked_domains"],
                "enable_unified_domain": s["enable_unified_domain"],
                "group_blacklist": s["group_blacklist"],
                "auto_capture": s["auto_capture"],
            }
        )

    async def _api_browser(self):
        """浏览器诊断状态。"""
        from astrbot.api.web import json_response

        return json_response(await self.screenshot_service.get_browser_status())

    async def _api_browser_recheck(self):
        """重置检测缓存并重新检测系统浏览器。"""
        from astrbot.api.web import json_response

        self.screenshot_service._reset_browser_detection()
        return json_response(await self.screenshot_service.get_browser_status())

    async def _api_browser_cleanup(self):
        """清理旧版 Playwright 浏览器残留文件。"""
        from astrbot.api.web import json_response

        result = await self.screenshot_service.uninstall_legacy_artifacts()
        result["status"] = await self.screenshot_service.get_browser_status()
        return json_response(result)

    # ==================== 卸载 ====================

    async def terminate(self):
        """插件卸载时的资源清理。"""
        logger.info("网页截图插件正在卸载，执行资源清理...")

        ScreenshotService._shutting_down = True

        for task in self.recall_tasks:
            if not task.done():
                task.cancel()
        self.recall_tasks.clear()

        try:
            lock = ScreenshotService._browser_lock
            if lock:
                async with lock:
                    await ScreenshotService.close_all_browsers()
            else:
                await ScreenshotService.close_all_browsers()
        except Exception as e:
            logger.debug(f"清理浏览器实例时出错（可忽略）: {e}")

        try:
            if hasattr(self, "content_fetcher"):
                await self.content_fetcher.close()
        except Exception:
            logger.debug("关闭正文抓取客户端失败（可忽略）")

        logger.info("网页截图插件已卸载")
