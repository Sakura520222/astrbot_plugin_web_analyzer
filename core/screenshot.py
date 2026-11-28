"""
网页截图服务

管理基于 CDP 的系统浏览器实例池（借还、上限、异常重试），提供：
- 网页截图（视口 / 整页 / 裁剪）与页面渲染 HTML
- 系统浏览器检测、诊断状态和旧版残留清理

实例池逻辑沿用久经验证的实现：启动中、使用中和空闲实例共用总量上限；
达到上限的请求等待空闲实例；仅实例自身故障时更换实例重试。
"""

import asyncio
import gc
import io
import os
import time
from urllib.parse import unquote, urlparse

import psutil
from PIL import Image

from astrbot.api import logger

from .browser import (
    BrowserExecutableError,
    BrowserInstance,
    detect_system_browser,
    sweep_stale_browser_artifacts,
)
from .urls import is_container_environment

# 启用"隐藏IP"时注入的 WebRTC 屏蔽脚本，防止真实IP通过WebRTC泄漏
_WEBRTC_BLOCK_JS = """\
const originalRTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
if (originalRTC) {
    window.RTCPeerConnection = function() {
        const pc = new originalRTC(...arguments);
        const origSetLocalDescription = pc.setLocalDescription.bind(pc);
        pc.setLocalDescription = function(desc) {
            if (desc && desc.type === 'offer') {
                desc.sdp = desc.sdp.replace(/a=candidate:.+\\r\\n/g, '');
            }
            return pc;
        };
        return pc;
    };
    window.RTCPeerConnection.prototype = originalRTC.prototype;
}
Object.defineProperty(navigator, 'connection', { get: () => null });
"""

# 读取最终地址与页面标题的表达式；等号包裹保证属性访问失败时抛错而非返回 undefined
_PAGE_INFO_EXPR = "(() => ({url: location.href, title: document.title || ''}))()"


class ScreenshotError(Exception):
    """网页截图相关错误"""


class ScreenshotLimitError(ScreenshotError):
    """页面内容超出截图限制（像素预算等）"""


class ScreenshotService:
    """系统浏览器截图服务

    浏览器实例池为类级别状态：所有服务实例共享检测缓存、
    实例池与上限，避免同一机器上重复启动浏览器进程。
    """

    # ---- 类级别实例池与检测缓存（进程内共享） ----
    _browser_pool: list = []  # 空闲实例池
    _max_idle_browsers = 3
    _max_browser_instances = 3  # 启动中 + 使用中 + 空闲的总量上限
    _browser_last_used: dict = {}
    _browser_lock = None
    _browser_slot_released = None  # 实例归还或关闭时唤醒等待者
    _last_cleanup_time = 0
    _cleanup_interval = 60 * 5
    _instance_timeout = 60 * 30  # 空闲实例保留时长

    _detected_browser_path = ""
    _detected_browser_name = ""
    _detected_browser_version = ""
    _detect_lock = None
    _last_profile_sweep = 0
    # 无法启动的浏览器路径 -> (过期时刻, 原因)
    _browser_blacklist: dict[str, tuple[float, str]] = {}
    _browser_blacklist_ttl = 60 * 10
    _browser_instances: set = set()  # 使用中与启动中的实例
    _shutting_down = False

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = "",
        proxy: str = "",
        hide_ip: bool = False,
        sandbox_mode: str = "auto",
        max_browser_instances: int = 3,
        screenshot_retry_count: int = 1,
        enable_memory_monitor: bool = False,
        memory_threshold_percent: float = 80.0,
    ):
        """初始化截图服务。

        Args:
            timeout: 导航与实例等待的超时秒数。
            user_agent: 页面 User-Agent，留空使用浏览器默认值。
            proxy: HTTP 代理，可带认证信息。
            hide_ip: 截图走代理并屏蔽 WebRTC。
            sandbox_mode: 浏览器沙箱模式（auto/always_disabled/always_enabled）。
            max_browser_instances: 浏览器实例总量上限。
            screenshot_retry_count: 实例故障时更换实例重试的次数。
            enable_memory_monitor: 是否启用内存监控。
            memory_threshold_percent: 内存释放阈值百分比。
        """
        self.timeout = timeout
        self.user_agent = user_agent
        self.proxy = proxy
        self.hide_ip = hide_ip
        if self.hide_ip and not self.proxy:
            logger.warning("已启用截图隐藏IP，但未配置代理，IP隐藏功能将不会生效")
        valid_modes = ("auto", "always_disabled", "always_enabled")
        self.sandbox_mode = sandbox_mode if sandbox_mode in valid_modes else "auto"
        self.screenshot_retry_count = screenshot_retry_count
        self.enable_memory_monitor = enable_memory_monitor
        self.memory_threshold = memory_threshold_percent
        self._browser_proxy_credentials = self._parse_browser_proxy_credentials()
        self._sandbox_disabled = self._resolve_sandbox_disabled()
        self._memory_monitor_task = None
        self.last_memory_check = time.time()
        self.memory_check_interval = 60 * 5

        if not ScreenshotService._browser_lock:
            ScreenshotService._browser_lock = asyncio.Lock()
            ScreenshotService._detect_lock = asyncio.Lock()
            ScreenshotService._browser_slot_released = asyncio.Event()
        ScreenshotService._set_browser_instance_limit(max_browser_instances)

    # ==================== 配置应用 ====================

    async def apply_runtime_config(self, settings: dict) -> None:
        """应用运行中可变更的配置；浏览器级设置变化时关闭不兼容的空闲实例。"""
        simple = {
            "timeout": "timeout",
            "request_timeout_s": "timeout",
            "user_agent": "user_agent",
            "proxy": "proxy",
            "hide_ip": "hide_ip",
            "sandbox_mode": "sandbox_mode",
            "screenshot_retry_count": "screenshot_retry_count",
            "enable_memory_monitor": "enable_memory_monitor",
            "memory_threshold_percent": "memory_threshold",
        }
        for key, attr in simple.items():
            if key in settings:
                setattr(self, attr, settings[key])
        if "max_browser_instances" in settings:
            ScreenshotService._set_browser_instance_limit(
                settings["max_browser_instances"]
            )
            await self._trim_idle_browsers()
        launch_settings = {"sandbox_mode", "hide_ip", "proxy"}
        if ScreenshotService._browser_blacklist and launch_settings & settings.keys():
            ScreenshotService._reset_browser_detection()
        self._sandbox_disabled = self._resolve_sandbox_disabled()
        self._browser_proxy_credentials = self._parse_browser_proxy_credentials()
        self._sync_memory_monitor()
        # 启动参数已变化的空闲实例关闭后按新参数重建
        if launch_settings & settings.keys():
            await self._close_incompatible_idle_browsers()

    # ==================== 截图 ====================

    async def capture(
        self,
        url: str,
        width: int = 1280,
        height: int = 720,
        full_page: bool = False,
        format: str = "jpeg",
        quality: int = 80,
        wait_time: int = 2000,
        wait_strategy: str = "fixed",
    ) -> tuple[bytes, str, str]:
        """截取网页，返回 (图片数据, 页面标题, 最终 URL)。

        仅当故障指向浏览器实例本身时按配置次数更换实例重试；
        页面自身的问题（加载失败、内容超限）不重试。

        Raises:
            ScreenshotError: 截图失败。
        """
        browser = None
        try:
            await self._ensure_browser_detected()
            await self._cleanup_browser_pool()
            attempts = self.screenshot_retry_count + 1
            for attempt in range(attempts):
                browser, _ = await self._get_or_create_browser()
                success = False
                try:
                    result = await self._perform_screenshot(
                        browser=browser,
                        url=url,
                        width=width,
                        height=height,
                        full_page=full_page,
                        format=format,
                        quality=quality,
                        wait_time=wait_time,
                        wait_strategy=wait_strategy,
                    )
                    success = True
                    return result
                except Exception as exc:
                    retryable = getattr(exc, "instance_failure", False)
                    if attempt + 1 == attempts or not retryable:
                        raise
                    logger.warning(
                        f"Browser instance failed; retrying with another: {exc}"
                    )
                finally:
                    owned, browser = browser, None
                    try:
                        if success:
                            await self._recycle_browser(owned)
                        else:
                            try:
                                await owned.close()
                            finally:
                                ScreenshotService._browser_instances.discard(owned)
                    except Exception as exc:
                        # 清理失败不吞掉已生成的截图或原始错误，只释放名额
                        logger.warning(f"Browser cleanup failed: {exc}")
                        ScreenshotService._browser_instances.discard(owned)
        except ScreenshotError:
            raise
        except Exception as e:
            logger.error(f"Screenshot capture failed: {url}: {e}")
            raise ScreenshotError(f"捕获网页截图失败: {url}, 错误: {e}") from e

    async def render_html(self, url: str) -> tuple[str, str]:
        """渲染网页并返回 (最终 URL, 渲染后的 HTML)。

        供正文抓取的浏览器模式复用同一实例池。

        Raises:
            ScreenshotError: 渲染失败。
        """
        browser = None
        try:
            await self._ensure_browser_detected()
            await self._cleanup_browser_pool()
            browser, _ = await self._get_or_create_browser()
            success = False
            try:
                page = await browser.new_page(user_agent=self.user_agent)
                try:
                    if self.hide_ip and self.proxy:
                        await page.add_init_script(_WEBRTC_BLOCK_JS)
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout * 1000,
                    )
                    await page.wait_for_timeout(1000)
                    info = await page._send(
                        "Runtime.evaluate",
                        {"expression": _PAGE_INFO_EXPR, "returnByValue": True},
                    )
                    value = info.get("result", {}).get("value", {})
                    final_url = value.get("url") or url
                    html = await page.content()
                    success = True
                    return final_url, html
                finally:
                    await page.close()
            finally:
                owned, browser = browser, None
                try:
                    if success:
                        await self._recycle_browser(owned)
                    else:
                        try:
                            await owned.close()
                        finally:
                            ScreenshotService._browser_instances.discard(owned)
                except Exception as exc:
                    logger.warning(f"Browser cleanup failed: {exc}")
                    ScreenshotService._browser_instances.discard(owned)
        except ScreenshotError:
            raise
        except Exception as e:
            logger.error(f"Browser render failed: {url}: {e}")
            raise ScreenshotError(f"浏览器渲染失败: {url}, 错误: {e}") from e

    async def _perform_screenshot(
        self,
        browser,
        url: str,
        width: int,
        height: int,
        full_page: bool,
        format: str,
        quality: int,
        wait_time: int,
        wait_strategy: str,
    ) -> tuple[bytes, str, str]:
        """在给定实例上导航、等待并截图，返回 (数据, 标题, 最终 URL)。"""
        page = await browser.new_page(
            viewport={"width": width, "height": height},
            user_agent=self.user_agent,
        )
        try:
            if self.hide_ip and self.proxy:
                await page.add_init_script(_WEBRTC_BLOCK_JS)

            await page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout * 1000
            )

            if wait_strategy == "networkidle":
                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=wait_time if wait_time > 0 else 30000,
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

            params = {"full_page": full_page, "format": format}
            if format.lower() == "jpeg":
                params["quality"] = quality
            screenshot_bytes = await page.screenshot(**params)

            info = await page._send(
                "Runtime.evaluate",
                {"expression": _PAGE_INFO_EXPR, "returnByValue": True},
            )
            value = info.get("result", {}).get("value", {})
            return screenshot_bytes, value.get("title", ""), value.get("url", "") or url
        finally:
            await page.close()

    @staticmethod
    def crop_screenshot(
        screenshot_bytes: bytes, crop_area: tuple[int, int, int, int]
    ) -> bytes:
        """按 (left, top, right, bottom) 裁剪截图，输出 PNG。"""
        try:
            image = Image.open(io.BytesIO(screenshot_bytes))
            cropped = image.crop(tuple(crop_area))
            output = io.BytesIO()
            cropped.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            raise ScreenshotError(f"裁剪截图失败: {e}") from e

    @staticmethod
    def make_thumbnail(screenshot_bytes: bytes, width: int = 480) -> bytes | None:
        """生成等比缩小的 JPEG 缩略图，用于交互视图卡片。失败时返回 None。"""
        try:
            image = Image.open(io.BytesIO(screenshot_bytes))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            ratio = max(1, image.width) / max(1, width)
            height = max(1, round(image.height / ratio))
            thumb = image.resize((width, height))
            output = io.BytesIO()
            thumb.save(output, format="JPEG", quality=60)
            return output.getvalue()
        except Exception as e:
            logger.debug(f"生成缩略图失败: {e}")
            return None

    # ==================== 浏览器检测与状态 ====================

    async def _ensure_browser_detected(self) -> str:
        """确保检测到可用的系统浏览器，返回可执行文件路径。"""
        if ScreenshotService._shutting_down:
            raise RuntimeError("插件正在关闭，拒绝浏览器操作")
        found, browser_path, _name, _version = await self._detect_browser()
        if not found:
            error_msg = self._browser_not_found_message()
            logger.error(error_msg)
            raise ScreenshotError(error_msg) from None
        return browser_path

    async def _detect_browser(self) -> tuple:
        """检测系统浏览器并缓存结果；并发调用只执行一次检测。"""
        async with ScreenshotService._detect_lock:
            cached_path = ScreenshotService._detected_browser_path
            if cached_path and os.path.isfile(cached_path):
                return (
                    True,
                    cached_path,
                    ScreenshotService._detected_browser_name,
                    ScreenshotService._detected_browser_version,
                )
            now = time.monotonic()
            for path, (until, _why) in list(
                ScreenshotService._browser_blacklist.items()
            ):
                if until <= now:
                    del ScreenshotService._browser_blacklist[path]
            excluded = set(ScreenshotService._browser_blacklist)
            loop = asyncio.get_running_loop()
            found, browser_path, browser_name, version = await loop.run_in_executor(
                None, lambda: detect_system_browser(exclude_paths=excluded)
            )
            if found:
                ScreenshotService._detected_browser_path = browser_path
                ScreenshotService._detected_browser_name = browser_name
                ScreenshotService._detected_browser_version = version
            return found, browser_path, browser_name, version

    @classmethod
    def _browser_not_found_message(cls) -> str:
        """生成检测失败提示，区分未安装与启动失败被暂时跳过。"""
        if not cls._browser_blacklist:
            return (
                "未检测到系统已安装的浏览器！\n"
                "本插件直接使用系统已安装的 Chrome / Edge / Chromium，无需额外下载。\n"
                "请安装其中任意一款浏览器后重试"
            )
        failures = "\n".join(
            f"{path}: {reason}"
            for path, (_expires, reason) in cls._browser_blacklist.items()
        )
        wait = max(
            int((expires - time.monotonic()) / 60) + 1
            for expires, _reason in cls._browser_blacklist.values()
        )
        return (
            f"系统浏览器启动失败，已暂时跳过：\n{failures}\n"
            f"约 {wait} 分钟后自动重试；修复运行环境后可重载插件立即重试"
        )

    @classmethod
    def reset_browser_session(cls) -> None:
        """插件加载或重载时恢复浏览器操作，并清除上次会话的检测缓存。"""
        cls._shutting_down = False
        cls._reset_browser_detection()

    @classmethod
    def _reset_browser_detection(cls) -> None:
        """清除启动失败记录与检测结果缓存，下次使用时重新检测。"""
        cls._browser_blacklist.clear()
        cls._detected_browser_path = ""
        cls._detected_browser_name = ""
        cls._detected_browser_version = ""

    @classmethod
    def _set_browser_instance_limit(cls, value) -> None:
        """应用实例总量上限（最小为 1），并唤醒等待实例的请求。"""
        try:
            limit = max(1, int(value))
        except (TypeError, ValueError):
            limit = 3
        cls._max_browser_instances = limit
        if cls._browser_slot_released is not None:
            cls._browser_slot_released.set()

    async def get_browser_status(self) -> dict:
        """获取系统浏览器可用性和实例池状态，供命令与诊断页展示。"""
        detected = False
        browser_path = ""
        try:
            detected, browser_path, _name, _version = await self._detect_browser()
        except Exception as e:
            logger.debug(f"检测系统浏览器失败: {e}")

        artifacts = self._get_legacy_playwright_artifacts()
        legacy_dir = artifacts.get("install_dir")
        legacy_dir_exists = bool(legacy_dir and legacy_dir.exists())
        legacy_size_mb = self._dir_size_mb(legacy_dir) if legacy_dir_exists else 0.0

        return {
            "installed": detected,
            "install_path": browser_path if detected else "",
            "browser_type": ScreenshotService._detected_browser_name or "",
            "browser_version": ScreenshotService._detected_browser_version or "",
            "browser_pool_size": len(ScreenshotService._browser_pool),
            "browser_instances": len(ScreenshotService._browser_instances),
            "max_browser_instances": ScreenshotService._max_browser_instances,
            "skipped_browsers": {
                path: {
                    "reason": reason,
                    "expires_in_min": max(
                        0, int((expires - time.monotonic()) / 60) + 1
                    ),
                }
                for path, (expires, reason) in (
                    ScreenshotService._browser_blacklist.items()
                )
            },
            "legacy_dir_exists": legacy_dir_exists,
            "legacy_dir_size_mb": legacy_size_mb,
        }

    # ==================== 旧版残留清理 ====================

    def _get_legacy_playwright_artifacts(self) -> dict:
        """定位旧版本插件通过 Playwright 下载的浏览器残留文件。"""
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
            logger.debug(f"获取数据路径失败，无法定位旧版残留文件: {e}")
        return artifacts

    @staticmethod
    def _dir_size_mb(path) -> float:
        """统计目录总大小（MB），失败时返回 0.0。"""
        from pathlib import Path

        try:
            total = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
            return round(total / (1024 * 1024), 1)
        except Exception:
            return 0.0

    async def uninstall_legacy_artifacts(self) -> dict:
        """清理旧版本 Playwright 浏览器残留文件并重置检测缓存。"""
        import shutil

        result = {"success": False, "message": "", "detail": ""}
        try:
            artifacts = self._get_legacy_playwright_artifacts()
            install_dir = artifacts.get("install_dir")
            deleted_files = False

            if install_dir and install_dir.exists():
                try:
                    size_mb = self._dir_size_mb(install_dir)
                    shutil.rmtree(install_dir)
                    deleted_files = True
                    logger.info(f"已删除旧版浏览器目录: {install_dir}")
                    result["detail"] = f"已释放 {size_mb:.1f} MB 磁盘空间"
                except Exception as e:
                    result["message"] = (
                        f"删除旧版浏览器目录失败: {install_dir}，错误: {e}"
                    )
                    logger.error(f"删除旧版浏览器目录失败: {e}")
                    return result
            else:
                result["detail"] = "旧版浏览器目录不存在（可能已被清理）"

            status_file = artifacts.get("status_file")
            if status_file and status_file.exists():
                try:
                    status_file.unlink()
                except Exception as e:
                    logger.warning(f"删除旧版状态文件失败（非致命）: {e}")

            self._reset_browser_detection()
            result["success"] = True
            result["message"] = (
                "✅ 旧版浏览器文件清理成功"
                if deleted_files
                else "✅ 清理完成（未发现需要删除的旧版浏览器文件）"
            )
        except Exception as e:
            result["message"] = f"清理旧版浏览器文件时发生意外错误: {e}"
            logger.error(f"清理旧版浏览器文件时发生意外错误: {e}")
        return result

    # ==================== 启动参数 ====================

    def _resolve_sandbox_disabled(self) -> bool:
        """按 sandbox_mode 与运行环境决定是否禁用浏览器沙箱。"""
        if self.sandbox_mode == "always_disabled":
            return True
        if self.sandbox_mode == "always_enabled":
            return False
        is_container = is_container_environment()
        if is_container:
            logger.info("检测到容器环境，将禁用浏览器沙箱")
        return is_container

    def _build_browser_launch_args(self) -> list[str]:
        """构建浏览器启动参数（沙箱与代理策略）。"""
        args = []
        if self._sandbox_disabled:
            args.extend(["--no-sandbox", "--disable-setuid-sandbox"])
        self._apply_ip_hide_args(args)
        return args

    def _apply_ip_hide_args(self, args: list[str]) -> None:
        """把代理与 WebRTC 屏蔽参数加入启动参数。

        Chromium 的 --proxy-server 不支持内嵌认证，带凭据的代理会被解析为
        无效代理并静默回退直连（导致真实IP泄漏），因此先拆出凭据，
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

    def _parse_browser_proxy_credentials(self):
        """从代理 URL 拆出 (用户名, 密码)；未启用隐藏IP或无凭据时返回 None。"""
        if not self.hide_ip or not self.proxy:
            return None
        parsed = urlparse(self.proxy)
        if parsed.username is None and parsed.password is None:
            return None
        return (unquote(parsed.username or ""), unquote(parsed.password or ""))

    def _browser_pool_key(self):
        """隔离浏览器级代理与沙箱设置不同的实例。"""
        return (self.sandbox_mode, self.hide_ip, self.proxy if self.hide_ip else None)

    # ==================== 实例池 ====================

    @staticmethod
    async def _cleanup_browser_pool():
        """移除过期、断连或超出空闲上限的实例。"""
        now = time.time()
        if now - ScreenshotService._last_cleanup_time < (
            ScreenshotService._cleanup_interval
        ):
            return
        async with ScreenshotService._browser_lock:
            ScreenshotService._last_cleanup_time = now
            keep = []
            discard = []
            for browser in dict.fromkeys(ScreenshotService._browser_pool):
                last_used = ScreenshotService._browser_last_used.get(id(browser), 0)
                if (
                    browser.is_connected()
                    and now - last_used < ScreenshotService._instance_timeout
                    and len(keep) < ScreenshotService._max_idle_browsers
                ):
                    keep.append(browser)
                else:
                    discard.append(browser)
            ScreenshotService._browser_pool = keep
        for browser in discard:
            try:
                await browser.close()
            except Exception as exc:
                logger.warning(f"Failed to close an expired browser: {exc}")
            finally:
                ScreenshotService._browser_instances.discard(browser)
                ScreenshotService._browser_last_used.pop(id(browser), None)

    async def _get_or_create_browser(self) -> tuple:
        """获取一个独占的浏览器实例：优先复用池中空闲实例，否则启动新实例。

        启动中、使用中和空闲实例的总量不超过 ``_max_browser_instances``。

        Returns:
            (浏览器实例, 是否来自实例池)。

        Raises:
            ScreenshotError: 没有可用浏览器、启动失败或等待实例超时。
        """
        if ScreenshotService._shutting_down:
            raise RuntimeError("插件正在关闭，拒绝创建新的浏览器实例")

        launch_args = self._build_browser_launch_args()
        while True:
            browser_path = await self._ensure_browser_detected()
            if time.time() - ScreenshotService._last_profile_sweep > 3600:
                ScreenshotService._last_profile_sweep = time.time()
                await sweep_stale_browser_artifacts()
            browser, instance = await self._claim_browser_capacity(
                browser_path, launch_args
            )
            if browser:
                return browser, True
            logger.debug("创建新的浏览器实例")
            try:
                return await self._start_browser(instance), False
            except BrowserExecutableError as exc:
                self._reject_browser(browser_path, exc)

    async def _claim_browser_capacity(self, browser_path: str, launch_args: list):
        """取出池中的空闲实例，或为启动新实例预留名额。

        实例数达到上限时等待其他请求归还或关闭实例；等待期间只要有实例
        归还到池中，就优先复用它。

        Returns:
            (池中的实例或 None, 已登记但尚未启动的新实例或 None)。
        """
        released = ScreenshotService._browser_slot_released
        deadline = time.monotonic() + self.timeout
        while True:
            async with ScreenshotService._browser_lock:
                # 先清空信号再检查状态，之后发生的归还或关闭不会遗漏
                released.clear()
                if ScreenshotService._shutting_down:
                    raise RuntimeError("插件正在关闭，拒绝创建新的浏览器实例")
                browser, dead = self._take_from_pool()
            # 关闭失效实例放在登记新实例之前：此处被取消不会留下已占用的名额
            await self._close_browsers(dead)
            if browser:
                return browser, None
            if dead:
                continue
            async with ScreenshotService._browser_lock:
                if (
                    len(ScreenshotService._browser_instances)
                    < ScreenshotService._max_browser_instances
                ):
                    # 登记新实例与上限检查在同一临界区内完成，并发请求不会超限；
                    # 临界区内没有 await，登记之后不会在此被取消
                    instance = BrowserInstance(
                        executable_path=browser_path,
                        extra_args=launch_args,
                        proxy_credentials=self._browser_proxy_credentials,
                    )
                    instance.pool_key = self._browser_pool_key()
                    instance.on_closed = released.set
                    ScreenshotService._browser_instances.add(instance)
                    return None, instance
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ScreenshotError(
                    f"浏览器实例已达上限（{ScreenshotService._max_browser_instances} 个），"
                    f"等待 {self.timeout} 秒仍无空闲实例，请稍后重试或调大最大实例数"
                )
            logger.debug("浏览器实例已达上限，等待空闲实例")
            try:
                await asyncio.wait_for(released.wait(), remaining)
            except TimeoutError:
                pass

    def _take_from_pool(self) -> tuple:
        """在实例池锁内取出可用实例，并摘除已断开连接的实例。"""
        picked = None
        dead = []
        for candidate in list(ScreenshotService._browser_pool):
            if not candidate.is_connected():
                dead.append(candidate)
            elif candidate.pool_key == self._browser_pool_key() and picked is None:
                picked = candidate
            else:
                continue
            ScreenshotService._browser_pool.remove(candidate)
            ScreenshotService._browser_last_used.pop(id(candidate), None)
        return picked, dead

    async def _close_browsers(self, browsers) -> None:
        """关闭实例并移出在用集合；在实例池锁外执行。"""
        for browser in browsers:
            try:
                await browser.close()
            except Exception as exc:
                logger.warning(f"Failed to close a browser: {exc}")
            finally:
                ScreenshotService._browser_instances.discard(browser)
                ScreenshotService._browser_last_used.pop(id(browser), None)

    async def _start_browser(self, instance: BrowserInstance) -> BrowserInstance:
        """启动已登记的浏览器实例；失败时关闭实例并移出在用集合。"""
        try:
            await instance.start()
            if ScreenshotService._shutting_down:
                await instance.close()
                raise RuntimeError("Plugin is shutting down")
            ScreenshotService._detected_browser_version = instance.version
            return instance
        except BrowserExecutableError:
            ScreenshotService._browser_instances.discard(instance)
            raise
        except BaseException:
            try:
                await instance.close()
            finally:
                ScreenshotService._browser_instances.discard(instance)
            raise

    @classmethod
    def _reject_browser(cls, browser_path: str, error: Exception) -> None:
        """暂时跳过无法启动的浏览器，让下一次检测尝试其他候选。"""
        cls._browser_blacklist[browser_path] = (
            time.monotonic() + cls._browser_blacklist_ttl,
            str(error),
        )
        cls._detected_browser_path = ""
        cls._detected_browser_name = ""
        cls._detected_browser_version = ""
        logger.warning(
            f"System browser cannot run here and is skipped for now: "
            f"{browser_path}: {error}"
        )

    async def _recycle_browser(self, browser):
        """把独占使用的浏览器实例归还到有界的空闲池。"""
        async with ScreenshotService._browser_lock:
            if browser in ScreenshotService._browser_pool:
                return
            if (
                not ScreenshotService._shutting_down
                and browser.is_connected()
                and getattr(browser, "pool_key", None) == self._browser_pool_key()
                and len(ScreenshotService._browser_pool)
                < ScreenshotService._max_idle_browsers
            ):
                ScreenshotService._browser_last_used[id(browser)] = time.time()
                ScreenshotService._browser_pool.append(browser)
                # 实例数达到上限时，等待中的请求可以直接复用它
                ScreenshotService._browser_slot_released.set()
                return
        try:
            await browser.close()
        finally:
            ScreenshotService._browser_instances.discard(browser)
            ScreenshotService._browser_last_used.pop(id(browser), None)

    async def _trim_idle_browsers(self) -> None:
        """关闭超出实例总量上限的空闲实例。"""
        async with ScreenshotService._browser_lock:
            surplus = ScreenshotService._browser_pool[
                ScreenshotService._max_browser_instances :
            ]
            del ScreenshotService._browser_pool[
                ScreenshotService._max_browser_instances :
            ]
        await self._close_browsers(surplus)

    async def _close_incompatible_idle_browsers(self):
        """关闭与当前启动参数不匹配的空闲实例。"""
        async with ScreenshotService._browser_lock:
            old = [
                browser
                for browser in ScreenshotService._browser_pool
                if getattr(browser, "pool_key", None) != self._browser_pool_key()
            ]
            ScreenshotService._browser_pool = [
                browser
                for browser in ScreenshotService._browser_pool
                if browser not in old
            ]
        await self._close_browsers(old)

    @classmethod
    async def close_all_browsers(cls) -> None:
        """关闭所有空闲、使用中和启动中的实例（插件卸载时调用）。"""
        browsers = set(cls._browser_pool) | cls._browser_instances
        cls._browser_pool.clear()
        cls._browser_last_used.clear()
        for browser in browsers:
            try:
                await browser.close()
            except Exception as exc:
                logger.warning(f"Failed to close a browser during shutdown: {exc}")
        cls._browser_instances.clear()

    # ==================== 内存监控 ====================

    @staticmethod
    def _get_memory_usage_percent() -> float:
        """读取内存使用率；存在 cgroup 限制时按限制计算（容器内准确）。"""
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
                limit = int(raw) if raw.isdigit() else 0
                if limit > 0:
                    return used / limit * 100
            except (OSError, ValueError):
                continue
        return psutil.virtual_memory().percent

    def _check_memory_usage(self) -> bool:
        """内存超过阈值时执行垃圾回收并缩减实例池。"""
        current_time = time.time()
        if current_time - self.last_memory_check < self.memory_check_interval:
            return False
        self.last_memory_check = current_time
        try:
            usage = self._get_memory_usage_percent()
            if usage > self.memory_threshold:
                logger.warning(
                    f"内存使用超过阈值 ({self.memory_threshold}%), 自动释放资源"
                )
                self._release_memory()
                return True
        except Exception as e:
            logger.error(f"检查内存使用情况失败: {e}")
        return False

    def _release_memory(self):
        """垃圾回收并按内存压力缩减空闲实例池。"""
        try:
            collected = gc.collect()
            logger.info(f"执行垃圾回收，释放内存，回收了 {collected} 个对象")
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._optimize_browser_pool())
            except Exception as e:
                logger.error(f"执行浏览器实例池优化失败: {e}")
        except Exception as e:
            logger.error(f"释放内存资源失败: {e}")

    async def _optimize_browser_pool(self):
        """按内存使用率决定保留的空闲实例数量。"""
        try:
            async with ScreenshotService._browser_lock:
                usage = self._get_memory_usage_percent()
                if usage > 90:
                    max_keep = 0
                elif usage > 80:
                    max_keep = 1
                elif usage > 70:
                    max_keep = 2
                else:
                    max_keep = ScreenshotService._max_idle_browsers - 1
                while len(ScreenshotService._browser_pool) > max_keep:
                    browser = ScreenshotService._browser_pool.pop()
                    try:
                        await browser.close()
                    except Exception as e:
                        logger.error(f"Failed to release an idle browser: {e}")
                    finally:
                        ScreenshotService._browser_instances.discard(browser)
                        ScreenshotService._browser_last_used.pop(id(browser), None)
        except Exception as e:
            logger.error(f"优化浏览器实例池失败: {e}")

    def _sync_memory_monitor(self):
        """按配置启动或停用后台内存监控任务。"""
        task = self._memory_monitor_task
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
        """定期检查内存使用情况。"""
        try:
            while self.enable_memory_monitor:
                await asyncio.sleep(self.memory_check_interval)
                if self.enable_memory_monitor:
                    self._check_memory_usage()
        except asyncio.CancelledError:
            pass
