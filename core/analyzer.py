"""
网页分析插件 - 网页分析器模块

这个模块是网页分析的核心组件，负责：
- 网页内容的异步抓取
- URL的提取和验证
- 网页内容的结构化解析
- 特定类型内容的提取（图片、链接、表格等）
- 网页截图的捕获

使用异步HTTP客户端和BeautifulSoup进行网页处理，支持代理、重试等高级功能。
"""

import asyncio
import gc
import io
import ipaddress
import re
import time
from urllib.parse import unquote, urljoin, urlparse

import httpx
import psutil
from bs4 import BeautifulSoup
from PIL import Image

from astrbot.api import logger

from .browser import (
    BrowserInstance,
    BrowserLaunchError,
    detect_system_browser,
    sweep_stale_browser_artifacts,
)
from .utils import WebAnalyzerUtils

# 启用"隐藏IP"时注入的 WebRTC 屏蔽脚本，防止真实IP通过WebRTC泄漏
_WEBRTC_BLOCK_JS = """\
// 屏蔽WebRTC以防止IP泄漏
const originalRTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
if (originalRTC) {
    window.RTCPeerConnection = function() {
        const pc = new originalRTC(...arguments);
        const origSetLocalDescription = pc.setLocalDescription.bind(pc);
        pc.setLocalDescription = function(desc) {
            if (desc && desc.type === 'offer') {
                desc.sdp = desc.sdp.replace(/a=candidate:.+\\r\\n/g, '');
            }
            return origSetLocalDescription(desc);
        };
        return pc;
    };
    window.RTCPeerConnection.prototype = originalRTC.prototype;
}
Object.defineProperty(navigator, 'connection', { get: () => null });
"""


# 自定义异常类
class WebAnalyzerException(Exception):
    """网页分析器基础异常类"""

    pass


class NetworkError(WebAnalyzerException):
    """网络相关错误"""

    pass


class ParsingError(WebAnalyzerException):
    """网页解析相关错误"""

    pass


class ScreenshotError(WebAnalyzerException):
    """网页截图相关错误"""

    pass


class ContentExtractionError(WebAnalyzerException):
    """内容提取相关错误"""

    pass


class WebAnalyzer:
    """网页分析器核心类

    这个类提供了完整的网页分析功能，包括：
    - 网页内容的异步抓取
    - URL的提取和验证
    - HTML内容的解析和结构化
    - 特定类型内容的提取
    - 网页截图的捕获

    支持异步上下文管理器，确保资源的正确释放。
    """

    # 类级别的浏览器实例池，用于复用浏览器实例
    _browser_pool = []
    _max_browser_instances = 3  # 最大浏览器实例数量
    _browser_last_used = {}  # 记录每个浏览器实例的最后使用时间
    _browser_lock = None  # 浏览器实例池锁
    _last_cleanup_time = 0  # 上次清理时间，用于定期清理任务
    _cleanup_interval = 60 * 5  # 清理间隔，5分钟
    _instance_timeout = 60 * 30  # 实例超时时间，30分钟未使用则清理

    # 系统浏览器检测结果缓存（类级别，所有实例共享）
    _detected_browser_path = ""  # 浏览器可执行文件路径
    _detected_browser_name = ""  # 浏览器名称，如 Google Chrome
    _detected_browser_version = ""  # 浏览器版本号
    _last_profile_sweep = 0  # 上次清理残留临时目录的时间
    _browser_blacklist: set[str] = set()  # Paths that failed to launch this session.
    _browser_instances: set = set()  # Includes checked-out and starting instances.

    _shutting_down = False  # 插件正在关闭标志，阻止新的浏览器操作

    def __init__(
        self,
        max_content_length: int = 10000,
        timeout: int = 30,
        user_agent: str = None,
        proxy: str = None,
        retry_count: int = 3,
        retry_delay: int = 2,
        enable_memory_monitor: bool = True,
        memory_threshold: float = 80.0,  # 内存使用阈值百分比
        enable_unified_domain: bool = True,  # 是否启用域名统一处理
        hide_ip: bool = False,  # 截图时是否隐藏真实IP
        fetch_mode: str = "httpx",  # 网页抓取模式：httpx 或 browser（兼容旧值 playwright）
        sandbox_mode: str = "auto",  # 浏览器沙箱模式：auto / always_disabled / always_enabled
    ):
        """初始化网页分析器

        Args:
            max_content_length: 提取的最大内容长度，防止内容过大
            timeout: HTTP请求超时时间，单位为秒
            user_agent: 请求时使用的User-Agent头
            proxy: HTTP代理设置，格式为 http://host:port 或 https://host:port
            retry_count: 请求失败时的重试次数
            retry_delay: 重试间隔时间，单位为秒
            enable_memory_monitor: 是否启用内存监控
            memory_threshold: 内存使用阈值百分比，超过此阈值时自动释放内存
            enable_unified_domain: 是否启用域名统一处理（如google.com和www.google.com视为同一域名）
            fetch_mode: 网页抓取模式，httpx(轻量快速) 或 browser(系统浏览器渲染)
            sandbox_mode: 浏览器沙箱模式，auto(自动检测) / always_disabled(始终禁用) / always_enabled(始终启用)
        """
        self.max_content_length = max_content_length
        self.timeout = timeout
        self.user_agent = (
            user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.proxy = proxy
        self.hide_ip = hide_ip
        if self.hide_ip and not self.proxy:
            logger.warning("已启用截图隐藏IP，但未配置代理，IP隐藏功能将不会生效")
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        # 兼容旧配置值 playwright，统一映射为 browser
        mode = "browser" if fetch_mode == "playwright" else fetch_mode
        self.fetch_mode = mode if mode in ("httpx", "browser") else "httpx"
        # 沙箱模式
        valid_modes = ("auto", "always_disabled", "always_enabled")
        self.sandbox_mode = sandbox_mode if sandbox_mode in valid_modes else "auto"
        self._sandbox_disabled = self._resolve_sandbox_disabled()
        self.client = None
        self._client_refs = 0  # HTTP 客户端并发引用计数（并发 async with 场景）
        self._client_lock = asyncio.Lock()
        self._client_generations = {}
        self._task_clients = {}
        self._client_entries = []
        self._memory_monitor_task = None
        self._browser_proxy_credentials = (
            None  # 浏览器代理认证凭据 (username, password)
        )
        # 内存监控相关
        self.enable_memory_monitor = enable_memory_monitor
        self.memory_threshold = memory_threshold
        self.last_memory_check = time.time()
        self.memory_check_interval = 60 * 5  # 内存检查间隔，单位为秒，从60秒延长到5分钟
        # URL处理相关
        self.enable_unified_domain = enable_unified_domain

        # 初始化浏览器锁
        if not WebAnalyzer._browser_lock:
            WebAnalyzer._browser_lock = asyncio.Lock()

    def _apply_ip_hide_args(self, args: list[str]) -> None:
        """将IP隐藏相关参数应用到浏览器启动参数中

        Chromium 的 --proxy-server 不支持内嵌认证信息，带凭据的代理串会被
        解析为无效代理并静默回退直连（导致真实IP泄漏），因此先拆出凭据，
        启动参数只携带地址，认证挑战由 CDP Fetch.authRequired 自动应答。
        """
        if not self.hide_ip or not self.proxy:
            return
        parsed = urlparse(self.proxy)
        proxy_for_launch = self.proxy
        if parsed.username or parsed.password:
            netloc = parsed.hostname or ""
            if ":" in netloc:
                netloc = f"[{netloc}]"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            proxy_for_launch = f"{parsed.scheme}://{netloc}"
            if parsed.scheme not in ("http", "https"):
                raise ScreenshotError("带认证的浏览器代理仅支持 HTTP/HTTPS")
            self._browser_proxy_credentials = (
                unquote(parsed.username or ""),
                unquote(parsed.password or ""),
            )
            logger.debug("检测到带凭据的代理，已拆分认证信息供 CDP 自动应答")
        args.append(f"--proxy-server={proxy_for_launch}")
        args.extend(
            [
                "--disable-webrtc-hw-encoding",
                "--disable-webrtc-hw-decoding",
                "--enforce-webrtc-ip-handling-policy",
                "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            ]
        )
        logger.debug("已启用代理和WebRTC屏蔽以隐藏真实IP")

    def _resolve_sandbox_disabled(self) -> bool:
        """根据 sandbox_mode 配置决定是否禁用浏览器沙箱"""
        if self.sandbox_mode == "always_disabled":
            return True
        if self.sandbox_mode == "always_enabled":
            return False
        # auto 模式：检测运行环境
        is_container = WebAnalyzerUtils.is_container_environment()
        if is_container:
            logger.info("检测到容器环境，将禁用浏览器沙箱")
        else:
            logger.debug("检测到非容器环境，将启用浏览器沙箱")
        return is_container

    def _build_browser_launch_args(self) -> list[str]:
        """构建浏览器启动参数（沙箱与代理策略），基础参数由 BrowserInstance 提供"""
        args = []
        if self._sandbox_disabled:
            args.extend(["--no-sandbox", "--disable-setuid-sandbox"])
        self._apply_ip_hide_args(args)
        return args

    @staticmethod
    async def _cleanup_browser_pool():
        """Remove expired, disconnected or excess idle instances."""
        now = time.time()
        if now - WebAnalyzer._last_cleanup_time < WebAnalyzer._cleanup_interval:
            return
        async with WebAnalyzer._browser_lock:
            WebAnalyzer._last_cleanup_time = now
            keep = []
            discard = []
            for browser in dict.fromkeys(WebAnalyzer._browser_pool):
                last_used = WebAnalyzer._browser_last_used.get(id(browser), 0)
                if (
                    browser.is_connected()
                    and now - last_used < WebAnalyzer._instance_timeout
                    and len(keep) < WebAnalyzer._max_browser_instances
                ):
                    keep.append(browser)
                else:
                    discard.append(browser)
            WebAnalyzer._browser_pool = keep
        for browser in discard:
            try:
                await browser.close()
            except Exception as exc:
                logger.warning(f"Failed to close an expired browser: {exc}")
            finally:
                WebAnalyzer._browser_instances.discard(browser)
                WebAnalyzer._browser_last_used.pop(id(browser), None)

    @staticmethod
    def _get_memory_usage_percent() -> float:
        """获取当前内存使用率（百分比）

        Linux 容器内 psutil.virtual_memory() 读取的是宿主机 /proc/meminfo，
        不反映容器的 cgroup 内存限制（docker -m 的场景下会读到宿主机的
        个位数百分比，导致保护逻辑永不触发，容器被内核 OOM-kill）。
        存在 cgroup 内存限制时优先按限制计算，否则回退 psutil。
        """
        # cgroup v2 与 v1 的使用量/上限文件
        for current_path, limit_path in (
            ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
            (
                "/sys/fs/cgroup/memory/memory.usage_in_bytes",
                "/sys/fs/cgroup/memory/memory.limit_in_bytes",
            ),
        ):
            try:
                with open(current_path) as f:
                    used = int(f.read().strip())
                with open(limit_path) as f:
                    raw = f.read().strip()
                # "max" 或无效值表示无限制
                limit = int(raw) if raw.isdigit() else 0
                if limit > 0:
                    return used / limit * 100
            except (OSError, ValueError):
                continue
        return psutil.virtual_memory().percent

    def _check_memory_usage(self):
        """检查内存使用情况，超过阈值时自动释放内存

        Returns:
            bool: 如果释放了内存，返回True，否则返回False
        """
        current_time = time.time()
        # 定期检查内存使用情况
        if current_time - self.last_memory_check < self.memory_check_interval:
            return False

        self.last_memory_check = current_time

        try:
            # 获取内存使用情况
            memory_usage = self._get_memory_usage_percent()

            logger.debug(f"当前内存使用情况: {memory_usage:.1f}%")

            if memory_usage > self.memory_threshold:
                logger.warning(
                    f"内存使用超过阈值 ({self.memory_threshold}%), 自动释放资源"
                )
                # 释放内存
                self._release_memory()
                return True
        except Exception as e:
            logger.error(f"检查内存使用情况失败: {e}")

        return False

    async def _optimize_browser_pool(self):
        """异步优化浏览器实例池，根据内存使用情况调整实例数量

        根据当前内存使用情况动态调整浏览器实例池大小：
        - 内存使用率 > 90%: 只保留0个实例
        - 内存使用率 > 80%: 只保留1个实例
        - 内存使用率 > 70%: 只保留2个实例
        - 内存使用率 ≤70%: 保留最大数量减1个实例
        """
        try:
            async with WebAnalyzer._browser_lock:
                # 获取当前内存使用情况
                memory_usage = self._get_memory_usage_percent()

                # 根据内存使用情况决定保留的实例数量
                if memory_usage > 90:
                    max_keep = 0
                elif memory_usage > 80:
                    max_keep = 1
                elif memory_usage > 70:
                    max_keep = 2
                else:
                    max_keep = WebAnalyzer._max_browser_instances - 1

                # 释放超出保留数量的浏览器实例
                while len(WebAnalyzer._browser_pool) > max_keep:
                    browser = WebAnalyzer._browser_pool.pop()
                    try:
                        await browser.close()
                        logger.debug("Closed an idle browser under memory pressure")
                    except Exception as e:
                        logger.error(f"Failed to release an idle browser: {e}")
                    finally:
                        WebAnalyzer._browser_instances.discard(browser)
                        WebAnalyzer._browser_last_used.pop(id(browser), None)
        except Exception as e:
            logger.error(f"优化浏览器实例池失败: {e}")

    def _release_memory(self):
        """释放内存资源

        执行垃圾回收，释放不再使用的资源，优化内存使用

        优化策略：
        1. 执行垃圾回收释放内存
        2. 智能调整浏览器实例池大小
        3. 增强容错机制，确保内存释放过程稳定
        """
        try:
            # 执行垃圾回收，释放内存
            collected = gc.collect()
            logger.info(f"执行垃圾回收，释放内存，回收了 {collected} 个对象")

            # 在异步上下文中执行浏览器池优化
            try:
                import asyncio

                loop = asyncio.get_running_loop()
                loop.create_task(self._optimize_browser_pool())
            except Exception as e:
                logger.error(f"执行浏览器实例池优化失败: {e}")
        except Exception as e:
            logger.error(f"释放内存资源失败: {e}")
            # 增强容错机制，确保内存释放失败不会影响插件正常运行

    async def apply_runtime_config(self, settings: dict) -> None:
        """Apply normalized settings without replacing active request clients."""
        mapping = {
            "request_timeout_s": "timeout",
            "retry_delay_s": "retry_delay",
            "memory_threshold_percent": "memory_threshold",
        }
        accepted = {
            "max_content_length",
            "timeout",
            "user_agent",
            "proxy",
            "retry_count",
            "retry_delay",
            "enable_unified_domain",
            "hide_ip",
            "fetch_mode",
            "sandbox_mode",
            "enable_memory_monitor",
            "memory_threshold",
        }
        for key, value in settings.items():
            attr = mapping.get(key, key)
            if attr in accepted:
                setattr(
                    self,
                    attr,
                    "browser"
                    if attr == "fetch_mode" and value == "playwright"
                    else value,
                )
        self._sandbox_disabled = self._resolve_sandbox_disabled()
        self._browser_proxy_credentials = self._parse_browser_proxy_credentials()
        await self._close_incompatible_idle_browsers()
        self._sync_memory_monitor()

    def _parse_browser_proxy_credentials(self):
        if not self.hide_ip or not self.proxy:
            return None
        parsed = urlparse(self.proxy)
        if parsed.username is None and parsed.password is None:
            return None
        return (unquote(parsed.username or ""), unquote(parsed.password or ""))

    async def _close_incompatible_idle_browsers(self):
        async with WebAnalyzer._browser_lock:
            old = [
                browser
                for browser in WebAnalyzer._browser_pool
                if getattr(browser, "pool_key", None) != self._browser_pool_key()
            ]
            WebAnalyzer._browser_pool = [
                browser for browser in WebAnalyzer._browser_pool if browser not in old
            ]
        for browser in old:
            try:
                await browser.close()
            finally:
                WebAnalyzer._browser_instances.discard(browser)
                WebAnalyzer._browser_last_used.pop(id(browser), None)

    def _sync_memory_monitor(self):
        task = getattr(self, "_memory_monitor_task", None)
        if not self.enable_memory_monitor:
            if task and not task.done():
                task.cancel()
            self._memory_monitor_task = None
        elif task is None or task.done():
            try:
                self._memory_monitor_task = asyncio.get_running_loop().create_task(
                    self._memory_monitor_loop()
                )
            except RuntimeError:
                pass

    async def _memory_monitor_loop(self):
        try:
            while self.enable_memory_monitor:
                await asyncio.sleep(self.memory_check_interval)
                if self.enable_memory_monitor:
                    self._check_memory_usage()
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        """Cancel runtime monitoring and close all owned HTTP client generations."""
        task = getattr(self, "_memory_monitor_task", None)
        self.enable_memory_monitor = False
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._memory_monitor_task = None
        async with self._client_lock:
            generations = list(self._client_generations.values())
            self._client_generations.clear()
            self._task_clients.clear()
            self._client_refs = 0
            self.client = None
        if generations:
            await asyncio.gather(
                *(generation["client"].aclose() for generation in generations),
                return_exceptions=True,
            )

    async def __aenter__(self):
        """异步上下文管理器入口

        惰性创建/复用共享 HTTP 客户端（引用计数保护）：
        同一 WebAnalyzer 实例会被并发请求重复进入，无保护的
        "进入即新建、退出即关闭" 会让并发请求互相关闭对方的客户端。
        第一个进入者创建客户端，最后一个退出者关闭。

        Returns:
            返回WebAnalyzer实例自身，用于上下文管理
        """
        async with self._client_lock:
            task = asyncio.current_task()
            signature = (self.timeout, self.proxy)
            generation = next(
                (
                    g
                    for g in self._client_generations.values()
                    if g["signature"] == signature
                ),
                None,
            )
            if generation is None:
                params = {"timeout": self.timeout}
                if self.proxy:
                    params["proxy"] = self.proxy
                generation = {
                    "signature": signature,
                    "client": httpx.AsyncClient(**params),
                    "refs": 0,
                }
                self._client_generations[id(generation)] = generation
            generation["refs"] += 1
            self.client = generation["client"]
            self._client_refs += 1
            self._task_clients.setdefault(task, []).append(
                (generation, self._request_snapshot())
            )
        return self

    def _request_snapshot(self):
        return {
            "timeout": self.timeout,
            "proxy": self.proxy,
            "user_agent": self.user_agent,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
        }

    def _current_request_snapshot(self):
        entries = self._task_clients.get(asyncio.current_task(), ())
        return entries[-1][1] if entries else self._request_snapshot()

    def _current_client(self):
        entries = self._task_clients.get(asyncio.current_task(), ())
        return entries[-1][0]["client"] if entries else self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口

        清理资源，确保：
        - 异步HTTP客户端正确关闭（最后一个退出者负责）
        - 浏览器实例正确处理（放回池中或关闭）
        - 资源泄漏的防止

        Args:
            exc_type: 异常类型（如果有）
            exc_val: 异常值（如果有）
            exc_tb: 异常回溯（如果有）
        """
        async with self._client_lock:
            task = asyncio.current_task()
            entries = self._task_clients.get(task, [])
            if not entries:
                owner = next(
                    (
                        owner
                        for owner, contexts in self._task_clients.items()
                        if contexts
                    ),
                    None,
                )
                if owner is not None:
                    task = owner
                    entries = self._task_clients[owner]
            generation, _snapshot = entries.pop() if entries else (None, None)
            if not entries:
                self._task_clients.pop(task, None)
            self._client_refs = max(0, self._client_refs - 1)
            if generation:
                generation["refs"] -= 1
                if generation["refs"] == 0:
                    await generation["client"].aclose()
                    self._client_generations.pop(id(generation), None)
            self.client = next(
                (g["client"] for g in self._client_generations.values()), None
            )

        # 检查内存使用情况
        self._check_memory_usage()

    async def _recycle_browser(self, browser):
        """Return one exclusively owned browser to the bounded idle pool."""
        async with WebAnalyzer._browser_lock:
            if browser in WebAnalyzer._browser_pool:
                return
            if (
                not WebAnalyzer._shutting_down
                and browser.is_connected()
                and getattr(browser, "pool_key", self._browser_pool_key())
                == self._browser_pool_key()
                and len(WebAnalyzer._browser_pool) < WebAnalyzer._max_browser_instances
            ):
                WebAnalyzer._browser_last_used[id(browser)] = time.time()
                WebAnalyzer._browser_pool.append(browser)
                return
        try:
            await browser.close()
        finally:
            WebAnalyzer._browser_instances.discard(browser)
            WebAnalyzer._browser_last_used.pop(id(browser), None)

    def extract_urls(
        self,
        text: str,
        enable_no_protocol: bool = False,
        default_protocol: str = "https",
    ) -> list[str]:
        """从文本中提取所有HTTP/HTTPS URL链接

        使用正则表达式匹配文本中的URL，支持：
        - HTTP和HTTPS协议
        - 各种常见的URL格式
        - 排除中文等非ASCII字符作为URL的一部分
        - 可选识别无协议头的URL（如 www.example.com）

        Args:
            text: 要从中提取URL的文本内容
            enable_no_protocol: 是否识别无协议头的URL
            default_protocol: 无协议头URL使用的默认协议（http或https）

        Returns:
            包含所有提取到的URL的列表
        """
        urls = self._extract_protocol_urls(text)
        if enable_no_protocol:
            no_protocol_urls = self._extract_no_protocol_urls(
                text, urls, default_protocol
            )
            urls.extend(no_protocol_urls)
        return urls

    def _extract_protocol_urls(self, text: str) -> list[str]:
        """提取带协议头的URL"""
        url_pattern = r"https?://[^\s\u4e00-\u9fff]+"
        return re.findall(url_pattern, text)

    def _extract_no_protocol_urls(
        self, text: str, existing_urls: list[str], default_protocol: str
    ) -> list[str]:
        """提取无协议头的URL"""
        text_for_no_protocol = self._remove_existing_urls(text, existing_urls)
        no_protocol_urls = self._find_no_protocol_urls(text_for_no_protocol)
        return self._format_no_protocol_urls(no_protocol_urls, default_protocol)

    def _remove_existing_urls(self, text: str, urls: list[str]) -> str:
        """从文本中移除已提取的URL"""
        text_for_no_protocol = text
        for url in urls:
            text_for_no_protocol = text_for_no_protocol.replace(url, "")
        return text_for_no_protocol

    def _find_no_protocol_urls(self, text: str) -> list[str]:
        """查找无协议头的URL"""
        no_protocol_pattern = r"(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9](?:\.[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9])+(?:/[^\s\u4e00-\u9fff]*)?"
        return re.findall(no_protocol_pattern, text)

    def _format_no_protocol_urls(
        self, urls: list[str], default_protocol: str
    ) -> list[str]:
        """格式化无协议头的URL"""
        formatted_urls = []
        for url in urls:
            cleaned_url = url.rstrip(".,;:!?)'\"")
            full_url = f"{default_protocol}://{cleaned_url}"
            formatted_urls.append(full_url)
        return formatted_urls

    def is_valid_url(self, url: str) -> bool:
        """验证URL格式是否有效

        检查URL是否符合基本格式要求：
        - 必须包含有效的协议（仅允许 http/https）
        - 必须包含有效的域名或IP地址
        - URL中直接使用的IP地址不能是私有/回环地址（防止SSRF）
        - 注意：不检查DNS解析结果，因为本地代理工具会劫持DNS

        Args:
            url: 要验证的URL字符串

        Returns:
            True表示URL格式有效，False表示无效
        """
        try:
            result = urlparse(url)
            # 协议白名单，仅允许 http 和 https
            if result.scheme.lower() not in ("http", "https"):
                return False
            if not result.netloc:
                return False
            # 提取主机名
            hostname = result.hostname
            if not hostname:
                return False
            # 检查URL中直接使用的IP地址是否为私有/回环地址
            # 仅检查字面IP，不检查DNS解析结果（代理工具会劫持DNS）
            try:
                addr = ipaddress.ip_address(hostname)
                if (
                    addr.is_private
                    or addr.is_loopback
                    or addr.is_link_local
                    or addr.is_reserved
                ):
                    # 阻止内网/回环/链路本地地址；is_reserved 额外拦截 IANA 保留地址（如 IETF 协议保留、
                    # 广播地址等），防止通过保留地址段绕过 SSRF 防护
                    return False
            except ValueError:
                # 域名（非IP地址），直接通过
                pass
            return True
        except Exception:
            return False

    def normalize_url(self, url: str) -> str:
        """规范化URL，统一格式

        对URL进行规范化处理：
        - 🔄  转换为小写
        - 📏  统一处理尾部斜杠
        - 🧹  去除多余的查询参数和片段（可选）
        - 🌐  统一域名格式（如google.com和www.google.com视为同一域名）

        Args:
            url: 要规范化的URL字符串

        Returns:
            规范化后的URL字符串
        """
        try:
            parsed = urlparse(url)
            netloc = self._normalize_netloc(parsed.netloc.lower())
            normalized = parsed._replace(
                scheme=parsed.scheme.lower(),
                netloc=netloc,
                path=parsed.path.rstrip("/"),
            )
            return normalized.geturl()
        except Exception:
            return url

    def _normalize_netloc(self, netloc: str) -> str:
        """规范化网络位置（域名或IP）"""
        if not self.enable_unified_domain or not netloc or "." not in netloc:
            return netloc
        if netloc.startswith("www.") or ".www." in netloc:
            return netloc
        if self._is_ip_address(netloc):
            return netloc
        return f"www.{netloc}"

    def _is_ip_address(self, netloc: str) -> bool:
        """检查是否为IP地址"""
        try:
            import ipaddress

            ipaddress.ip_address(netloc)
            return True
        except ValueError:
            return False

    async def fetch_webpage(self, url: str) -> str:
        """异步抓取网页HTML内容

        根据配置的抓取模式选择不同的抓取方式：
        - httpx: 使用HTTP客户端轻量快速抓取
        - browser: 使用系统浏览器渲染抓取，支持JS动态内容

        浏览器模式失败时会自动回退到httpx模式。

        Args:
            url: 要抓取的网页URL

        Returns:
            网页的HTML文本内容

        Raises:
            NetworkError: 当网络请求失败时抛出
        """
        # 浏览器模式：系统浏览器渲染抓取，失败时回退到httpx
        if self.fetch_mode == "browser":
            try:
                return await self._fetch_with_browser(url)
            except Exception as e:
                logger.warning(f"浏览器抓取失败，回退到httpx: {url}, 错误: {e}")

        # httpx模式：轻量快速HTTP请求
        headers = self._build_http_headers()
        return await self._fetch_with_retry(url, headers)

    def _build_http_headers(self) -> dict:
        """构造HTTP请求头

        Returns:
            包含完整请求头的字典
        """
        return {
            "User-Agent": self._current_request_snapshot()["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
            "Sec-GPC": "1",
        }

    async def _fetch_with_retry(self, url: str, headers: dict) -> str:
        """执行带重试机制的HTTP请求

        Args:
            url: 目标URL
            headers: HTTP请求头

        Returns:
            网页HTML内容

        Raises:
            NetworkError: 当所有重试都失败时抛出
        """
        import asyncio

        snapshot = self._current_request_snapshot()
        client = self._current_client()
        for attempt in range(snapshot["retry_count"] + 1):
            try:
                response = await client.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()

                # 检查响应大小，防止超大响应导致OOM（10MB限制）
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        content_length_int = int(content_length)
                    except ValueError:
                        content_length_int = None
                    if content_length_int and content_length_int > 10 * 1024 * 1024:
                        raise NetworkError(
                            f"响应体过大({content_length_int}字节)，已跳过: {url}"
                        )

                logger.info(
                    f"抓取网页成功: {url} (尝试 {attempt + 1}/{self.retry_count + 1})"
                )
                return response.text
            except Exception as e:
                if attempt < self.retry_count:
                    # 还有重试次数，等待 retry_delay 秒后重试
                    logger.warning(
                        f"抓取网页失败，将重试: {url}, 错误: {e} (尝试 {attempt + 1}/{self.retry_count + 1})"
                    )
                    await asyncio.sleep(snapshot["retry_delay"])
                else:
                    # 重试次数用完，抛出网络错误
                    logger.error(
                        f"抓取网页失败: {url}, 错误: {e} (尝试 {attempt + 1}/{self.retry_count + 1})"
                    )
                    raise NetworkError(f"抓取网页失败: {url}, 错误: {str(e)}") from e

    async def _fetch_with_browser(self, url: str) -> str:
        """使用系统浏览器抓取网页HTML内容

        通过浏览器渲染获取JavaScript动态生成的内容，可绕过部分反爬机制。

        Args:
            url: 要抓取的网页URL

        Returns:
            渲染后的网页HTML文本内容

        Raises:
            NetworkError: 当浏览器抓取失败时抛出
        """
        # 确保系统浏览器可用
        await self._ensure_browser_detected()
        # 清理浏览器池中的无效实例
        await self._cleanup_browser_pool()

        browser = None
        page = None
        success = False

        try:
            # Acquire one browser exclusively for this operation.
            browser, _ = await self._get_or_create_browser()

            # 创建新页面
            page = await browser.new_page(user_agent=self.user_agent)

            # 隐藏IP：注入脚本屏蔽WebRTC，防止IP泄漏
            if self.hide_ip and self.proxy:
                await page.add_init_script(_WEBRTC_BLOCK_JS)

            # 导航到目标URL，等待DOM加载完成
            await page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout * 1000
            )

            # 等待动态内容渲染
            await page.wait_for_timeout(1000)

            # 获取渲染后的HTML内容
            html = await page.content()

            logger.info(f"浏览器抓取网页成功: {url}")
            success = True
            return html

        except Exception as e:
            logger.error(f"浏览器抓取网页失败: {url}, 错误: {e}")
            raise NetworkError(f"浏览器抓取网页失败: {url}, 错误: {str(e)}") from e

        finally:
            try:
                if page:
                    try:
                        await page.close()
                    except BaseException:
                        # Never re-pool a browser whose page cleanup was interrupted.
                        success = False
                        raise
            finally:
                if browser:
                    try:
                        if success:
                            await self._recycle_browser(browser)
                        else:
                            try:
                                await browser.close()
                            finally:
                                WebAnalyzer._browser_instances.discard(browser)
                    except Exception as e:
                        logger.warning(f"Browser cleanup failed: {e}")

    def extract_content(self, html: str, url: str) -> dict:
        """从HTML中提取结构化的网页内容

        解析HTML文档，提取关键内容：
        - 网页标题
        - 主要正文内容
        - 支持多种内容选择策略

        使用BeautifulSoup进行HTML解析，优先选择语义化标签
        （如article、main等）提取内容，确保提取的内容质量。

        Args:
            html: 网页的HTML文本内容
            url: 网页的原始URL，用于结果返回

        Returns:
            包含标题、内容和URL的字典

        Raises:
            ParsingError: 当HTML解析失败时抛出
        """
        try:
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html, "lxml")

            # 提取网页标题
            title_text = self._extract_title(soup)

            # 提取文章内容
            content_text = self._extract_main_content(soup)

            # 限制内容长度，防止内容过大
            content_text = self._limit_content_length(content_text)

            return {"title": title_text, "content": content_text, "url": url}
        except Exception as e:
            logger.error(f"解析网页内容失败: {e}")
            raise ParsingError(f"解析网页内容失败: {url}, 错误: {str(e)}") from e

    def _get_content_selectors(self) -> list[str]:
        """获取内容选择器列表（优先级从高到低）

        Returns:
            CSS选择器列表，按优先级排序
        """
        return [
            "article",  # 语义化文章标签
            "main",  # 语义化主内容标签
            ".article-content",  # 常见文章内容类名
            ".post-content",  # 常见博客内容类名
            ".content",  # 通用内容类名
            "body",  # 兜底：使用整个body
        ]

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """从BeautifulSoup对象中提取网页标题

        Args:
            soup: BeautifulSoup对象

        Returns:
            网页标题文本
        """
        title = soup.find("title")
        return title.get_text().strip() if title else "无标题"

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """从BeautifulSoup对象中提取主要内容

        使用多策略内容提取算法:
        1. 优先选择语义化标签(article, main)
        2. 选择常见的内容类名
        3. 最后使用整个body作为兜底

        Args:
            soup: BeautifulSoup对象

        Returns:
            提取的主要内容文本
        """
        # 获取内容选择器列表
        content_selectors = self._get_content_selectors()

        # 尝试从各个选择器中提取内容，选择最长的作为结果
        content_text = self._try_extract_from_selectors(soup, content_selectors)

        # 如果没找到合适的内容，使用body作为最后的兜底方案
        if not content_text:
            content_text = self._extract_from_body(soup)

        return content_text

    def _try_extract_from_selectors(
        self, soup: BeautifulSoup, selectors: list[str]
    ) -> str:
        """尝试从多个选择器中提取内容

        Args:
            soup: BeautifulSoup对象
            selectors: CSS选择器列表

        Returns:
            提取的最长内容文本
        """
        content_text = ""
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # 清理内容，移除脚本和样式标签
                cleaned_element = self._clean_content_element(element)
                text = cleaned_element.get_text(separator="\n", strip=True)
                # 选择最长的内容作为结果
                if len(text) > len(content_text):
                    content_text = text

        return content_text

    def _extract_from_body(self, soup: BeautifulSoup) -> str:
        """从body标签中提取内容（兜底方案）

        Args:
            soup: BeautifulSoup对象

        Returns:
            提取的内容文本
        """
        body = soup.find("body")
        if body:
            cleaned_body = self._clean_content_element(body)
            return cleaned_body.get_text(separator="\n", strip=True)
        return ""

    def _clean_content_element(self, element: BeautifulSoup) -> BeautifulSoup:
        """清理内容元素，移除脚本和样式标签

        Args:
            element: BeautifulSoup元素

        Returns:
            清理后的BeautifulSoup元素
        """
        # 直接处理元素，不需要创建副本
        # 移除脚本和样式标签，避免干扰内容提取
        for script in element.find_all(["script", "style"]):
            script.decompose()
        return element

    def _limit_content_length(self, content: str) -> str:
        """限制内容长度，防止内容过大

        Args:
            content: 原始内容文本

        Returns:
            限制长度后的内容文本
        """
        if len(content) > self.max_content_length:
            return content[: self.max_content_length] + "..."
        return content

    def crop_screenshot(
        self, screenshot_bytes: bytes, crop_area: tuple[int, int, int, int]
    ) -> bytes:
        """裁剪截图

        Args:
            screenshot_bytes: 原始截图二进制数据
            crop_area: 裁剪区域，格式为 (left, top, right, bottom)

        Returns:
            裁剪后的截图二进制数据
        """
        try:
            # 将二进制数据转换为Image对象
            image = Image.open(io.BytesIO(screenshot_bytes))

            # 裁剪图片
            cropped_image = image.crop(crop_area)

            # 将裁剪后的图片转换回二进制数据
            output = io.BytesIO()
            cropped_image.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            logger.error(f"裁剪截图失败: {e}")
            raise ScreenshotError(f"裁剪截图失败: {str(e)}") from e

    async def capture_screenshot(
        self,
        url: str,
        quality: int = 80,
        width: int = 1280,
        height: int = 720,
        full_page: bool = False,
        wait_time: int = 2000,
        wait_strategy: str = "fixed",
        format: str = "jpeg",
    ) -> bytes:
        """使用系统浏览器捕获网页截图

        自动检测系统已安装的浏览器（Chrome / Edge / Chromium），支持：
        - 自定义分辨率和质量
        - 全屏截图或可视区域截图
        - 自定义等待时间，确保页面加载完成
        - 支持JPEG、PNG格式

        Args:
            url: 要截图的网页URL
            quality: 截图质量，范围1-100（仅适用于JPEG格式）
            width: 截图宽度（像素）
            height: 截图高度（像素）
            full_page: 是否截取整个页面，False仅截取可视区域
            wait_time: 页面加载后等待的时间（毫秒），确保动态内容加载
            format: 截图格式，支持"jpeg"、"png"

        Returns:
            截图的二进制数据

        Raises:
            ScreenshotError: 当截图失败时抛出
        """
        browser = None
        try:
            await self._ensure_browser_detected()
            await self._cleanup_browser_pool()
            browser, from_pool = await self._get_or_create_browser()
            attempts = 2 if from_pool else 1
            for attempt in range(attempts):
                success = False
                try:
                    result = await self._perform_screenshot(
                        browser=browser,
                        url=url,
                        width=width,
                        height=height,
                        quality=quality,
                        full_page=full_page,
                        wait_time=wait_time,
                        wait_strategy=wait_strategy,
                        format=format,
                    )
                    success = True
                    return result
                except Exception:
                    if attempt + 1 == attempts:
                        raise
                    logger.warning(
                        "Pooled browser failed; retrying with a new instance"
                    )
                finally:
                    owned, browser = browser, None
                    if success:
                        await self._recycle_browser(owned)
                    else:
                        try:
                            await owned.close()
                        finally:
                            WebAnalyzer._browser_instances.discard(owned)
                browser = await self._create_new_browser()
        except Exception as e:
            logger.error(f"Screenshot capture failed: {url}: {e}")
            raise ScreenshotError(f"捕获网页截图失败: {url}, 错误: {e}") from e

    async def _ensure_browser_detected(self) -> str:
        """确保已检测到系统可用的浏览器（结果缓存于类级别）

        Returns:
            str: 浏览器可执行文件路径

        Raises:
            ScreenshotError: 未检测到系统浏览器时抛出
        """
        import asyncio
        import os

        if WebAnalyzer._shutting_down:
            raise RuntimeError("插件正在关闭，拒绝浏览器操作")

        cached_path = WebAnalyzer._detected_browser_path
        if cached_path and os.path.isfile(cached_path):
            return cached_path

        # 浏览器检测涉及子进程调用，放到线程池避免阻塞事件循环
        loop = asyncio.get_event_loop()
        found, browser_path, browser_name, version = await loop.run_in_executor(
            None,
            lambda: detect_system_browser(exclude_paths=WebAnalyzer._browser_blacklist),
        )
        if not found:
            error_msg = (
                "未检测到系统已安装的浏览器！\n"
                "本插件直接使用系统已安装的 Chrome / Edge / Chromium，无需额外下载。\n"
                "请安装其中任意一款浏览器后重试"
            )
            logger.error(error_msg)
            raise ScreenshotError(error_msg) from None

        WebAnalyzer._detected_browser_path = browser_path
        WebAnalyzer._detected_browser_name = browser_name
        WebAnalyzer._detected_browser_version = version
        return browser_path

    def _get_legacy_playwright_artifacts(self) -> dict:
        """定位旧版本插件通过 Playwright 下载的浏览器残留文件

        Returns:
            dict: {"install_dir": Path | None, "status_file": Path | None}
        """
        from pathlib import Path

        artifacts: dict = {"install_dir": None, "status_file": None}

        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            data_path_raw = get_astrbot_data_path()
            data_path = (
                Path(data_path_raw)
                if not isinstance(data_path_raw, Path)
                else data_path_raw
            )
            artifacts["install_dir"] = (
                data_path
                / "plugin_data"
                / "astrbot_plugin_web_analyzer"
                / "playwright_browsers"
            )
            artifacts["status_file"] = (
                data_path
                / "plugin_data"
                / "astrbot_plugin_web_analyzer"
                / "browser_install_status.json"
            )
        except Exception as e:
            logger.debug(f"获取 AstrBot 数据路径失败，无法定位旧版残留文件: {e}")

        return artifacts

    @staticmethod
    def _dir_size_mb(path) -> float:
        """统计目录总大小（MB），失败时返回 0.0"""
        from pathlib import Path

        try:
            total = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
            return round(total / (1024 * 1024), 1)
        except Exception:
            return 0.0

    async def uninstall_browser(self) -> dict:
        """清理旧版本插件通过 Playwright 下载的浏览器残留文件

        新版本直接使用系统已安装的浏览器，不再下载浏览器文件。
        该命令用于清理旧版本留下的 playwright_browsers 目录和状态文件。

        Returns:
            dict: 清理结果，包含 success(bool)、message(str)、detail(str)
        """
        import shutil

        result = {"success": False, "message": "", "detail": ""}

        try:
            # System browser instances are unrelated to legacy downloaded files.

            # 2. 删除旧版 Playwright 浏览器目录
            artifacts = self._get_legacy_playwright_artifacts()
            install_dir = artifacts.get("install_dir")
            deleted_files = False

            if install_dir and install_dir.exists():
                try:
                    size_mb = self._dir_size_mb(install_dir)
                    shutil.rmtree(install_dir)
                    deleted_files = True
                    logger.info(
                        f"已删除旧版浏览器目录: {install_dir}（释放 {size_mb:.1f} MB 空间）"
                    )
                    result["detail"] = f"已释放 {size_mb:.1f} MB 磁盘空间"
                except PermissionError as e:
                    result["message"] = (
                        f"删除旧版浏览器目录失败（权限不足）: {install_dir}\n"
                        f"错误: {e}\n"
                        f"请手动删除该目录，或使用管理员权限运行"
                    )
                    logger.error(f"删除旧版浏览器目录权限不足: {e}")
                    return result
                except Exception as e:
                    result["message"] = (
                        f"删除旧版浏览器目录失败: {install_dir}\n"
                        f"错误: {e}\n"
                        f"请手动删除该目录"
                    )
                    logger.error(f"删除旧版浏览器目录失败: {e}")
                    return result
            else:
                logger.info("旧版浏览器目录不存在，跳过删除")
                result["detail"] = "旧版浏览器目录不存在（可能已被清理）"

            # 3. 删除旧版安装状态文件
            status_file = artifacts.get("status_file")
            if status_file and status_file.exists():
                try:
                    status_file.unlink()
                    logger.info(f"已删除旧版安装状态文件: {status_file}")
                except Exception as e:
                    logger.warning(f"删除旧版安装状态文件失败（非致命）: {e}")

            # 4. 重置浏览器检测结果缓存，下次使用时重新检测
            WebAnalyzer._detected_browser_path = ""
            WebAnalyzer._detected_browser_name = ""
            WebAnalyzer._detected_browser_version = ""

            result["success"] = True
            if deleted_files:
                result["message"] = "✅ 旧版浏览器文件清理成功"
            else:
                result["message"] = "✅ 清理完成（未发现需要删除的旧版浏览器文件）"

            logger.info("旧版浏览器文件清理完成")

        except Exception as e:
            result["message"] = f"清理旧版浏览器文件时发生意外错误: {str(e)}"
            logger.error(f"清理旧版浏览器文件时发生意外错误: {e}")

        return result

    async def get_browser_status(self) -> dict:
        """获取系统浏览器可用性和实例池状态

        Returns:
            dict: 浏览器状态信息
        """
        import asyncio
        from pathlib import Path

        # 检测系统浏览器（优先使用类级别缓存）
        detected = False
        browser_path = WebAnalyzer._detected_browser_path
        if browser_path and Path(browser_path).is_file():
            detected = True
        else:
            try:
                loop = asyncio.get_event_loop()
                found, path, name, version = await loop.run_in_executor(
                    None, lambda: detect_system_browser(WebAnalyzer._browser_blacklist)
                )
                if found:
                    detected = True
                    browser_path = path
                    WebAnalyzer._detected_browser_path = path
                    WebAnalyzer._detected_browser_name = name
                    WebAnalyzer._detected_browser_version = version
            except Exception as e:
                logger.debug(f"检测系统浏览器失败: {e}")

        browser_type_map = {
            "Google Chrome": "chrome",
            "Microsoft Edge": "edge",
            "Chromium": "chromium",
        }

        # 旧版 Playwright 残留文件信息
        artifacts = self._get_legacy_playwright_artifacts()
        legacy_dir = artifacts.get("install_dir")
        legacy_dir_exists = bool(legacy_dir and legacy_dir.exists())
        legacy_size_mb = self._dir_size_mb(legacy_dir) if legacy_dir_exists else 0.0

        # 字段名与旧版保持一致，供命令输出和前端兼容
        status_info = {
            "installed": detected,
            "install_path": browser_path if detected else "",
            "install_time": "",
            "browser_type": browser_type_map.get(
                WebAnalyzer._detected_browser_name,
                WebAnalyzer._detected_browser_name or "",
            ),
            "browser_version": WebAnalyzer._detected_browser_version or "",
            "browser_pool_size": len(WebAnalyzer._browser_pool),
            "is_installing": False,
            "install_dir_exists": legacy_dir_exists,
            "install_dir_size_mb": legacy_size_mb,
        }

        return status_info

    async def _get_or_create_browser(self) -> tuple:
        """从池中获取或创建新的浏览器实例

        Returns:
            tuple: (浏览器实例, 是否来自实例池)
        """
        if WebAnalyzer._shutting_down:
            raise RuntimeError("插件正在关闭，拒绝创建新的浏览器实例")

        browser = await self._try_get_browser_from_pool()

        if browser:
            return browser, True

        # 创建新的浏览器实例
        return await self._create_new_browser(), False

    def _browser_pool_key(self):
        """Keep browser-level proxy and sandbox settings isolated between users."""
        return (self.sandbox_mode, self.hide_ip, self.proxy if self.hide_ip else None)

    async def _try_get_browser_from_pool(self):
        """Check out a connected browser with compatible launch settings."""
        async with WebAnalyzer._browser_lock:
            for candidate in list(WebAnalyzer._browser_pool):
                if not candidate.is_connected():
                    WebAnalyzer._browser_pool.remove(candidate)
                    WebAnalyzer._browser_last_used.pop(id(candidate), None)
                    try:
                        await candidate.close()
                    finally:
                        WebAnalyzer._browser_instances.discard(candidate)
                elif candidate.pool_key == self._browser_pool_key():
                    WebAnalyzer._browser_pool.remove(candidate)
                    WebAnalyzer._browser_last_used.pop(id(candidate), None)
                    return candidate
        return None

    async def _create_new_browser(self) -> BrowserInstance:
        """创建新的浏览器实例（启动系统已安装的浏览器进程）

        Returns:
            BrowserInstance: 新的浏览器实例
        """
        logger.debug("创建新的浏览器实例")

        # Cleanup is filesystem-only and verifies profile ownership.
        if time.time() - WebAnalyzer._last_profile_sweep > 3600:
            WebAnalyzer._last_profile_sweep = time.time()
            await sweep_stale_browser_artifacts()

        launch_args = self._build_browser_launch_args()
        while not WebAnalyzer._shutting_down:
            browser_path = await self._ensure_browser_detected()
            instance = BrowserInstance(
                executable_path=browser_path,
                extra_args=launch_args,
                proxy_credentials=self._browser_proxy_credentials,
            )
            instance.pool_key = self._browser_pool_key()
            WebAnalyzer._browser_instances.add(instance)
            try:
                await instance.start()
                if WebAnalyzer._shutting_down:
                    await instance.close()
                    raise RuntimeError("Plugin is shutting down")
                WebAnalyzer._detected_browser_version = instance.version
                return instance
            except BrowserLaunchError:
                WebAnalyzer._browser_instances.discard(instance)
                WebAnalyzer._browser_blacklist.add(browser_path)
                WebAnalyzer._detected_browser_path = ""
                WebAnalyzer._detected_browser_name = ""
                WebAnalyzer._detected_browser_version = ""
                logger.warning(
                    "System browser failed to launch; trying another candidate"
                )
            except BaseException:
                try:
                    await instance.close()
                finally:
                    WebAnalyzer._browser_instances.discard(instance)
                raise
        raise RuntimeError("Plugin is shutting down")

    async def _perform_screenshot(
        self,
        browser,
        url: str,
        width: int,
        height: int,
        quality: int,
        full_page: bool,
        wait_time: int,
        wait_strategy: str = "fixed",
        format: str = "jpeg",
    ) -> bytes:
        """执行实际的截图操作

        Args:
            browser: 浏览器实例
            url: 目标URL
            width: 视口宽度
            height: 视口高度
            quality: 截图质量
            full_page: 是否全页截图
            wait_time: 等待时间（毫秒）
            wait_strategy: 等待策略(fixed/networkidle/smart)
            format: 截图格式

        Returns:
            截图的二进制数据
        """
        # 创建新页面
        page = await browser.new_page(
            viewport={"width": width, "height": height},
            user_agent=self.user_agent,
        )

        try:
            if self.hide_ip and self.proxy:
                await page.add_init_script(_WEBRTC_BLOCK_JS)

            # 导航到目标URL
            await page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout * 1000
            )

            # 根据策略等待页面加载
            if wait_strategy == "networkidle":
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=wait_time if wait_time > 0 else 30000
                    )
                except Exception:
                    logger.info("networkidle等待超时，继续截图")
            elif wait_strategy == "smart":
                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=min(wait_time if wait_time > 0 else 5000, 5000),
                    )
                except Exception:
                    logger.info("smart模式networkidle超时，使用固定等待")
                await page.wait_for_timeout(500)
            else:  # fixed
                await page.wait_for_timeout(wait_time)

            # 构建截图参数
            screenshot_params = {
                "full_page": full_page,
                "format": format,
            }

            # quality 参数只适用于 jpeg 格式
            if format.lower() == "jpeg":
                screenshot_params["quality"] = quality

            # 捕获截图
            screenshot_bytes = await page.screenshot(**screenshot_params)

            logger.info("截图成功")
            return screenshot_bytes

        finally:
            await page.close()

    def extract_specific_content(
        self, html: str, url: str, extract_types: list[str]
    ) -> dict:
        """从HTML中提取特定类型的内容

        根据指定的提取类型，从HTML文档中提取结构化数据：
        - 标题（title）
        - 正文内容（content）
        - 图片链接（images）
        - 超链接（links）
        - 表格（tables）
        - 列表（lists）
        - 代码块（code）
        - 元信息（meta）
        - 视频链接（videos）
        - 音频链接（audios）
        - 引用块（quotes）
        - 标题列表（headings）
        - 段落（paragraphs）
        - 按钮（buttons）
        - 表单（forms）

        Args:
            html: 网页的HTML文本内容
            url: 网页的原始URL，用于处理相对路径
            extract_types: 要提取的内容类型列表

        Returns:
            包含提取内容的字典，键为提取类型，值为对应内容
        """
        try:
            soup = BeautifulSoup(html, "lxml")
            extracted_content = {}

            # 提取标题
            if "title" in extract_types:
                title = soup.find("title")
                extracted_content["title"] = (
                    title.get_text().strip() if title else "无标题"
                )

            # 提取正文内容
            if "content" in extract_types:
                content_selectors = [
                    "article",  # 语义化文章标签
                    "main",  # 语义化主内容标签
                    ".article-content",  # 常见文章内容类名
                    ".post-content",  # 常见博客内容类名
                    ".content",  # 通用内容类名
                    "body",  # 兜底方案
                ]

                content_text = ""
                for selector in content_selectors:
                    element = soup.select_one(selector)
                    if element:
                        # 移除脚本和样式标签，避免干扰内容提取
                        for script in element.find_all(["script", "style"]):
                            script.decompose()
                        text = element.get_text(separator="\n", strip=True)
                        if len(text) > len(content_text):
                            content_text = text

                # 限制内容长度
                if len(content_text) > self.max_content_length:
                    content_text = content_text[: self.max_content_length] + "..."

                extracted_content["content"] = content_text

            # 提取图片链接，最多提取10张
            if "images" in extract_types:
                images = []
                for img in soup.find_all("img"):
                    src = img.get("src")
                    if src:
                        # 处理相对路径，转换为绝对URL
                        full_url = urljoin(url, src)
                        alt_text = img.get("alt", "").strip()
                        images.append({"url": full_url, "alt": alt_text})
                extracted_content["images"] = images[:10]  # 限制最多10张图片

            # 提取超链接，最多提取20个
            if "links" in extract_types:
                links = []
                for a in soup.find_all("a", href=True):
                    href = a.get("href")
                    if href and not href.startswith("#"):  # 跳过锚点链接
                        full_url = urljoin(url, href)
                        text = a.get_text().strip() or full_url  # 链接文本为空时使用URL
                        links.append({"text": text, "url": full_url})
                extracted_content["links"] = links[:20]  # 限制最多20个链接

            # 提取表格，最多提取5个
            if "tables" in extract_types:
                tables = []
                for table in soup.find_all("table"):
                    table_data = []
                    # 提取表头
                    headers = []
                    thead = table.find("thead")
                    if thead:
                        for th in thead.find_all("th"):
                            headers.append(th.get_text().strip())

                    # 提取表体
                    tbody = table.find("tbody") or table  # 没有tbody时使用table本身
                    for row in tbody.find_all("tr"):
                        row_data = []
                        for cell in row.find_all(["td", "th"]):  # 同时处理td和th
                            row_data.append(cell.get_text().strip())
                        if row_data:  # 跳过空行
                            table_data.append(row_data)

                    if table_data:  # 只添加有数据的表格
                        tables.append({"headers": headers, "rows": table_data})
                extracted_content["tables"] = tables[:5]  # 限制最多5个表格

            # 提取列表，最多提取10个
            if "lists" in extract_types:
                lists = []
                # 提取无序列表
                for ul in soup.find_all("ul"):
                    list_items = []
                    for li in ul.find_all("li"):
                        list_items.append(li.get_text().strip())
                    if list_items:  # 只添加有内容的列表
                        lists.append(
                            {
                                "type": "ul",  # 列表类型：无序列表
                                "items": list_items[:20],  # 每个列表最多20项
                            }
                        )

                # 提取有序列表
                for ol in soup.find_all("ol"):
                    list_items = []
                    for li in ol.find_all("li"):
                        list_items.append(li.get_text().strip())
                    if list_items:  # 只添加有内容的列表
                        lists.append(
                            {
                                "type": "ol",  # 列表类型：有序列表
                                "items": list_items[:20],  # 每个列表最多20项
                            }
                        )
                extracted_content["lists"] = lists[:10]  # 限制最多10个列表

            # 提取代码块，最多提取5个
            if "code" in extract_types:
                code_blocks = []
                for code in soup.find_all(["pre", "code"]):  # 同时处理pre和code标签
                    code_text = code.get_text().strip()
                    if code_text and len(code_text) > 10:  # 跳过短代码块
                        # 获取语言类型
                        language = ""
                        if code.parent.name == "pre":
                            # 检查pre标签是否有语言类名
                            for cls in code.parent.get("class", []):
                                if cls.startswith("language-"):
                                    language = cls[9:]
                                    break
                                if cls.startswith("lang-"):
                                    language = cls[5:]
                                    break
                        elif code.get("class"):
                            # 检查code标签是否有语言类名
                            for cls in code.get("class", []):
                                if cls.startswith("language-"):
                                    language = cls[9:]
                                    break
                                if cls.startswith("lang-"):
                                    language = cls[5:]
                                    break

                        # 限制单个代码块长度
                        truncated_code = (
                            code_text[:1000] + "..."
                            if len(code_text) > 1000
                            else code_text
                        )
                        code_blocks.append(
                            {"code": truncated_code, "language": language}
                        )
                extracted_content["code_blocks"] = code_blocks[:5]  # 限制最多5个代码块

            # 提取元信息
            if "meta" in extract_types:
                meta_info = {}
                # 提取描述
                description = soup.find("meta", attrs={"name": "description"})
                if description:
                    meta_info["description"] = description.get("content", "").strip()

                # 提取关键词
                keywords = soup.find("meta", attrs={"name": "keywords"})
                if keywords:
                    meta_info["keywords"] = keywords.get("content", "").strip()

                # 提取作者
                author = soup.find("meta", attrs={"name": "author"})
                if author:
                    meta_info["author"] = author.get("content", "").strip()

                # 提取发布时间
                publish_time = soup.find(
                    "meta", attrs={"property": "article:published_time"}
                )
                if not publish_time:
                    publish_time = soup.find("meta", attrs={"name": "publish_date"})
                if publish_time:
                    meta_info["publish_time"] = publish_time.get("content", "").strip()

                # 提取网站名称
                site_name = soup.find("meta", attrs={"property": "og:site_name"})
                if site_name:
                    meta_info["site_name"] = site_name.get("content", "").strip()

                # 提取og:title
                og_title = soup.find("meta", attrs={"property": "og:title"})
                if og_title:
                    meta_info["og_title"] = og_title.get("content", "").strip()

                # 提取og:description
                og_description = soup.find("meta", attrs={"property": "og:description"})
                if og_description:
                    meta_info["og_description"] = og_description.get(
                        "content", ""
                    ).strip()

                extracted_content["meta"] = meta_info

            # 提取视频链接，最多提取5个
            if "videos" in extract_types:
                videos = []
                # 查找video标签
                for video in soup.find_all("video"):
                    src = video.get("src")
                    if src:
                        full_url = urljoin(url, src)
                        videos.append({"url": full_url, "type": "video"})
                # 查找iframe标签（可能包含视频）
                for iframe in soup.find_all("iframe"):
                    src = iframe.get("src")
                    if src:
                        full_url = urljoin(url, src)
                        videos.append({"url": full_url, "type": "iframe"})
                extracted_content["videos"] = videos[:5]  # 限制最多5个视频

            # 提取音频链接，最多提取5个
            if "audios" in extract_types:
                audios = []
                # 查找audio标签
                for audio in soup.find_all("audio"):
                    src = audio.get("src")
                    if src:
                        full_url = urljoin(url, src)
                        audios.append(full_url)
                # 查找embed标签（可能包含音频）
                for embed in soup.find_all("embed"):
                    src = embed.get("src")
                    if src and (
                        src.endswith(".mp3")
                        or src.endswith(".wav")
                        or src.endswith(".ogg")
                    ):
                        full_url = urljoin(url, src)
                        audios.append(full_url)
                extracted_content["audios"] = audios[:5]  # 限制最多5个音频

            # 提取引用块，最多提取10个
            if "quotes" in extract_types:
                quotes = []
                # 查找blockquote标签
                for blockquote in soup.find_all("blockquote"):
                    quote_text = blockquote.get_text().strip()
                    if quote_text:
                        # 查找引用的作者
                        cite = blockquote.find("cite")
                        author = cite.get_text().strip() if cite else ""
                        quotes.append({"text": quote_text, "author": author})
                extracted_content["quotes"] = quotes[:10]  # 限制最多10个引用块

            # 提取标题列表
            if "headings" in extract_types:
                headings = []
                # 查找所有h1-h6标签
                for level in range(1, 7):
                    for heading in soup.find_all(f"h{level}"):
                        headings.append(
                            {
                                "level": level,
                                "text": heading.get_text().strip(),
                                "id": heading.get("id", ""),
                            }
                        )
                extracted_content["headings"] = headings

            # 提取段落，最多提取20个
            if "paragraphs" in extract_types:
                paragraphs = []
                for p in soup.find_all("p"):
                    text = p.get_text().strip()
                    if text:
                        paragraphs.append(text)
                extracted_content["paragraphs"] = paragraphs[:20]  # 限制最多20个段落

            # 提取按钮，最多提取10个
            if "buttons" in extract_types:
                buttons = []
                for button in soup.find_all("button"):
                    text = button.get_text().strip()
                    onclick = button.get("onclick", "").strip()
                    buttons.append(
                        {
                            "text": text,
                            "onclick": onclick,
                            "type": button.get("type", "button"),
                        }
                    )
                extracted_content["buttons"] = buttons[:10]  # 限制最多10个按钮

            # 提取表单，最多提取5个
            if "forms" in extract_types:
                forms = []
                for form in soup.find_all("form"):
                    form_data = {
                        "action": form.get("action", ""),
                        "method": form.get("method", "get"),
                        "inputs": [],
                        "buttons": [],
                    }
                    # 提取表单输入
                    for input_elem in form.find_all("input"):
                        form_data["inputs"].append(
                            {
                                "type": input_elem.get("type", "text"),
                                "name": input_elem.get("name", ""),
                                "value": input_elem.get("value", ""),
                            }
                        )
                    # 提取表单文本域
                    for textarea in form.find_all("textarea"):
                        form_data["inputs"].append(
                            {
                                "type": "textarea",
                                "name": textarea.get("name", ""),
                                "value": textarea.get_text().strip(),
                            }
                        )
                    # 提取表单选择
                    for select in form.find_all("select"):
                        options = []
                        for option in select.find_all("option"):
                            options.append(
                                {
                                    "value": option.get("value", ""),
                                    "text": option.get_text().strip(),
                                    "selected": bool(option.get("selected")),
                                }
                            )
                        form_data["inputs"].append(
                            {
                                "type": "select",
                                "name": select.get("name", ""),
                                "options": options,
                            }
                        )
                    # 提取表单按钮
                    for button in form.find_all("button"):
                        form_data["buttons"].append(
                            {
                                "text": button.get_text().strip(),
                                "type": button.get("type", "submit"),
                            }
                        )
                    forms.append(form_data)
                extracted_content["forms"] = forms[:5]  # 限制最多5个表单

            return extracted_content
        except Exception as e:
            logger.error(f"提取特定内容失败: {e}")
            raise ContentExtractionError(f"提取特定内容失败: {str(e)}") from e
