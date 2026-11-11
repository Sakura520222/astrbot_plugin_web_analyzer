"""Drive an installed Chrome/Edge/Chromium over the DevTools Protocol.

Each instance owns an isolated temporary profile and a headless process. The
only automation dependency is websockets; no browser is downloaded or attached
to the user's interactive browser/profile.
"""

import asyncio
import base64
import json
import os
import platform
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import psutil

try:
    from websockets.asyncio.client import connect as _ws_connect
except ImportError:  # websockets 12 uses the legacy asyncio implementation.
    from websockets import connect as _ws_connect

from astrbot.api import logger

PROFILE_DIR_PREFIX = "astrbot_wa_profile_"
_WS_MAX_SIZE = 64 * 1024 * 1024
_LAUNCH_TIMEOUT = 20.0
_DEFAULT_CMD_TIMEOUT = 30.0
# Bound raw pixels before compression/base64 so PNG cannot exhaust the transport.
_MAX_SCREENSHOT_PIXELS = 10_000_000
_MAX_HTML_CHARS = 8_000_000


class BrowserError(Exception):
    """Report an unusable browser or a failed protocol operation."""


class BrowserLaunchError(BrowserError):
    """Report failure to start or connect to the browser."""


class CdpError(BrowserError):
    """Report an error response from Chrome DevTools Protocol."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class CdpNavigationError(BrowserError):
    """Report a failed navigation, such as a DNS or connection failure."""


class CdpTimeoutError(BrowserError):
    """Report a protocol command or page readiness timeout."""


def detect_system_browser(
    exclude_paths: set[str] | None = None,
) -> tuple[bool, str, str, str]:
    """Locate an installed browser, preferring Chrome, then Edge, then Chromium.

    Args:
        exclude_paths: Executables previously rejected during this session.

    Returns:
        Whether a browser was found, executable path, name and optional version.
    """
    excluded = {os.path.normcase(p) for p in (exclude_paths or ())}
    candidates = []
    system = platform.system()
    if system == "Windows":
        roots = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")),
        ]
        candidates = [
            (
                "Google Chrome",
                ["chrome"],
                [p / "Google/Chrome/Application/chrome.exe" for p in roots],
            ),
            (
                "Microsoft Edge",
                ["msedge"],
                [p / "Microsoft/Edge/Application/msedge.exe" for p in roots],
            ),
            (
                "Chromium",
                ["chromium"],
                [p / "Chromium/Application/chrome.exe" for p in roots],
            ),
        ]
    elif system == "Darwin":
        for name, executable in (
            ("Google Chrome", "Google Chrome"),
            ("Microsoft Edge", "Microsoft Edge"),
            ("Chromium", "Chromium"),
        ):
            candidates.append(
                (
                    name,
                    [],
                    [
                        root / f"{name}.app/Contents/MacOS/{executable}"
                        for root in (
                            Path("/Applications"),
                            Path.home() / "Applications",
                        )
                    ],
                )
            )
    elif system == "Linux":
        candidates = [
            (
                "Google Chrome",
                ["google-chrome", "google-chrome-stable"],
                [Path("/opt/google/chrome/google-chrome")],
            ),
            ("Microsoft Edge", ["microsoft-edge", "microsoft-edge-stable"], []),
            (
                "Chromium",
                ["chromium", "chromium-browser"],
                [Path("/snap/bin/chromium")],
            ),
        ]
    for name, commands, paths in candidates:
        options = [shutil.which(command) for command in commands] + [
            str(p) for p in paths
        ]
        for path in options:
            if (
                not path
                or os.path.normcase(path) in excluded
                or not Path(path).is_file()
            ):
                continue
            # GUI executables on Windows may open a window even with --version.
            # Read the authoritative version later via Browser.getVersion instead.
            version = ""
            if system != "Windows":
                try:
                    result = subprocess.run(
                        [path, "--version"], capture_output=True, text=True, timeout=5
                    )
                    version = result.stdout.strip()
                except (OSError, subprocess.TimeoutExpired):
                    pass
            logger.debug(f"Detected system browser: {name}: {path}")
            return True, path, name, version
    return False, "", "", ""


async def sweep_stale_browser_artifacts() -> None:
    """Remove old profiles only when their recorded owners have exited.

    Never kill processes by matching a command-line prefix: another bot on this
    machine may be using it. Unmarked profiles are left untouched.
    """

    def sweep():
        cutoff = time.time() - 6 * 3600
        for path in Path(tempfile.gettempdir()).glob(f"{PROFILE_DIR_PREFIX}*"):
            try:
                if path.is_symlink() or path.stat().st_mtime >= cutoff:
                    continue
                marker = path / "astrbot-owner.json"
                if not marker.is_file():
                    continue
                owners = json.loads(marker.read_text(encoding="utf-8"))
                alive = False
                for owner in owners:
                    try:
                        if (
                            psutil.Process(owner["pid"]).create_time()
                            == owner["created"]
                        ):
                            alive = True
                            break
                    except psutil.NoSuchProcess:
                        continue
                if not alive:
                    shutil.rmtree(path)
            except (OSError, ValueError, KeyError, TypeError, psutil.Error):
                continue

    await asyncio.to_thread(sweep)


class CDPPage:
    """Represent one isolated tab with navigation, rendering and capture APIs."""

    def __init__(
        self,
        browser: "BrowserInstance",
        target_id: str,
        session_id: str,
        context_id: str | None = None,
    ):
        self._browser = browser
        self.target_id = target_id
        self.session_id = session_id
        self._context_id = context_id
        self._closed = False
        self._inflight_requests: set[str] = set()
        self._last_network_change = time.monotonic()
        self._lifecycle_events: set[tuple[str, str, str]] = set()
        self._lifecycle_changed = asyncio.Event()
        self._event_tasks: set[asyncio.Task] = set()
        self._auth_attempts: set[str] = set()

    def _on_event(self, method: str, params: dict):
        """Update navigation/network state without blocking the shared reader."""
        request_id = params.get("requestId")
        if method == "Page.lifecycleEvent":
            self._lifecycle_events.add(
                (
                    params.get("frameId", ""),
                    params.get("loaderId", ""),
                    params.get("name", ""),
                )
            )
            self._lifecycle_changed.set()
        elif method == "Network.requestWillBeSent":
            if request_id and params.get("type") not in ("WebSocket", "EventSource"):
                self._inflight_requests.add(request_id)
                self._last_network_change = time.monotonic()
        elif method in ("Network.loadingFinished", "Network.loadingFailed"):
            if request_id in self._inflight_requests:
                self._inflight_requests.discard(request_id)
                self._last_network_change = time.monotonic()
        elif method in ("Fetch.requestPaused", "Fetch.authRequired"):
            task = asyncio.create_task(self._handle_fetch_event(method, params))
            self._event_tasks.add(task)
            task.add_done_callback(self._event_tasks.discard)

    async def _handle_fetch_event(self, method: str, params: dict):
        """Continue intercepted requests, sending credentials only to a proxy."""
        request_id = params["requestId"]
        try:
            if method == "Fetch.requestPaused":
                await self._send("Fetch.continueRequest", {"requestId": request_id})
                return
            challenge = params.get("authChallenge", {})
            response = {"response": "Default"}
            credentials = self._browser._proxy_credentials
            if challenge.get("source") == "Proxy" and credentials:
                if request_id in self._auth_attempts:
                    response = {"response": "CancelAuth"}
                else:
                    self._auth_attempts.add(request_id)
                    response = {
                        "response": "ProvideCredentials",
                        "username": credentials[0],
                        "password": credentials[1],
                    }
            await self._send(
                "Fetch.continueWithAuth",
                {"requestId": request_id, "authChallengeResponse": response},
            )
        except BrowserError:
            logger.debug("Could not continue an intercepted request on a closing page")

    async def _send(
        self, method: str, params: dict | None = None, timeout: float | None = None
    ):
        return await self._browser.send_command(
            method, params, session_id=self.session_id, timeout=timeout
        )

    async def _enable_domains(self):
        await self._send("Page.enable")
        await self._send("Network.enable")
        await self._send("Page.setLifecycleEventsEnabled", {"enabled": True})
        if self._browser._proxy_credentials:
            await self._send("Fetch.enable", {"handleAuthRequests": True})

    async def set_user_agent(self, user_agent: str):
        await self._send("Emulation.setUserAgentOverride", {"userAgent": user_agent})

    async def set_viewport(self, width: int, height: int):
        await self._send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": int(width),
                "height": int(height),
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )

    async def add_init_script(self, source: str):
        await self._send("Page.addScriptToEvaluateOnNewDocument", {"source": source})

    async def goto(
        self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000
    ):
        """Navigate and wait for this navigation's frame/loader lifecycle event.

        Args:
            url: Destination URL.
            wait_until: domcontentloaded or load.
            timeout: Total navigation timeout in milliseconds.

        Raises:
            CdpNavigationError: Chrome reports a navigation failure.
            CdpTimeoutError: Navigation does not finish within the deadline.
        """
        name = {"domcontentloaded": "DOMContentLoaded", "load": "load"}.get(wait_until)
        if name is None:
            raise ValueError(f"Unsupported navigation wait strategy: {wait_until}")
        self._lifecycle_events.clear()
        try:
            async with asyncio.timeout(timeout / 1000):
                result = await self._send(
                    "Page.navigate", {"url": url}, timeout=timeout / 1000
                )
                if result.get("errorText"):
                    raise CdpNavigationError(
                        f"Navigation failed: {result['errorText']}"
                    )
                # Same-document navigations have no new loader or lifecycle event.
                if not result.get("loaderId"):
                    return
                expected = (result["frameId"], result["loaderId"], name)
                while expected not in self._lifecycle_events:
                    if not self._browser.is_connected():
                        raise BrowserError("Browser disconnected during navigation")
                    self._lifecycle_changed.clear()
                    await self._lifecycle_changed.wait()
        except TimeoutError:
            raise CdpTimeoutError(
                f"Page navigation timed out after {timeout}ms"
            ) from None

    async def wait_for_load_state(
        self, state: str = "networkidle", timeout: int = 30000
    ):
        """Wait for 500ms without tracked requests; long-polling may time out.

        Args:
            state: Only networkidle is supported.
            timeout: Maximum wait in milliseconds.

        Raises:
            CdpTimeoutError: The page never becomes idle.
        """
        if state != "networkidle":
            raise ValueError(f"Unsupported load state: {state}")
        deadline = time.monotonic() + timeout / 1000
        while (
            self._inflight_requests
            or time.monotonic() - self._last_network_change < 0.5
        ):
            if not self._browser.is_connected():
                raise BrowserError(
                    "Browser disconnected while waiting for network idle"
                )
            if time.monotonic() >= deadline:
                raise CdpTimeoutError(f"Network idle timed out after {timeout}ms")
            await asyncio.sleep(0.05)

    async def wait_for_timeout(self, timeout_ms: int):
        await asyncio.sleep(max(0, timeout_ms) / 1000)

    async def content(self) -> str:
        """Return rendered HTML, rejecting oversized DOMs before serialization."""
        result = await self._send(
            "Runtime.evaluate",
            {
                "expression": f"(() => {{const s = document.documentElement.outerHTML; if (s.length > {_MAX_HTML_CHARS}) throw new Error('Rendered HTML exceeds size limit'); return s;}})()",
                "returnByValue": True,
            },
        )
        if result.get("exceptionDetails"):
            raise BrowserError(
                "Unable to serialize rendered HTML within the size limit"
            )
        return result.get("result", {}).get("value", "")

    async def screenshot(
        self,
        full_page: bool = False,
        format: str = "jpeg",
        quality: int | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """Capture a viewport or a full page, within a bounded pixel budget.

        Args:
            full_page: Capture the document rather than only the viewport.
            format: jpeg or png.
            quality: JPEG quality, from 1 to 100.
            timeout: Protocol timeout in seconds.

        Returns:
            Encoded image bytes. Oversized captures fail explicitly.

        Raises:
            BrowserError: The image exceeds the pixel budget.
        """
        format = format.lower()
        if format not in ("jpeg", "png"):
            raise ValueError(f"Unsupported screenshot format: {format}")
        metrics = await self._send("Page.getLayoutMetrics")
        size = metrics["cssContentSize"] if full_page else metrics["cssLayoutViewport"]
        width = size.get("width", size.get("clientWidth", 0))
        height = size.get("height", size.get("clientHeight", 0))
        if width * height > _MAX_SCREENSHOT_PIXELS:
            raise BrowserError(
                f"Screenshot exceeds {_MAX_SCREENSHOT_PIXELS:,} pixel limit ({width}x{height})"
            )
        params = {
            "format": format,
            "fromSurface": True,
            "captureBeyondViewport": full_page,
        }
        if format == "jpeg" and quality is not None:
            params["quality"] = max(1, min(100, int(quality)))
        result = await self._send("Page.captureScreenshot", params, timeout=timeout)
        return base64.b64decode(result["data"])

    async def close(self):
        """Close the target and cancel any pending authentication continuations."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._context_id:
                await self._browser.send_command(
                    "Target.disposeBrowserContext",
                    {"browserContextId": self._context_id},
                    timeout=5,
                )
            else:
                await self._browser.send_command(
                    "Target.closeTarget", {"targetId": self.target_id}, timeout=5
                )
        except BrowserError:
            pass
        finally:
            self._browser.remove_page(self)
            tasks = list(self._event_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


class BrowserInstance:
    """Own one headless process, temporary profile and multiplexed connection."""

    def __init__(
        self,
        executable_path: str,
        extra_args: list[str] | None = None,
        command_timeout: float = _DEFAULT_CMD_TIMEOUT,
        proxy_credentials: tuple | None = None,
    ):
        self.executable_path = executable_path
        self.extra_args = extra_args or []
        self.command_timeout = command_timeout
        self._proxy_credentials = proxy_credentials
        self.version = ""
        self.pool_key = None
        self._process = None
        self._ws = None
        self._reader_task = None
        self._launch_task = None
        self._close_task = None
        self._profile_dir = ""
        self._closed = False
        self._ws_alive = False
        self._next_command_id = 0
        self._send_lock = asyncio.Lock()
        self._pending_commands: dict[int, asyncio.Future] = {}
        self._pages: dict[str, CDPPage] = {}

    async def start(self):
        """Launch an isolated headless browser and establish a CDP connection.

        Raises:
            BrowserLaunchError: Launch or connection handshake fails.
        """
        self._profile_dir = tempfile.mkdtemp(prefix=PROFILE_DIR_PREFIX)
        args = [
            self.executable_path,
            "--headless=new",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={self._profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--mute-audio",
            "--hide-scrollbars",
        ] + self.extra_args
        kwargs = (
            {"creationflags": subprocess.CREATE_NO_WINDOW}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        try:
            # Shield the thread: a cancelled await must still obtain the Popen
            # result before cleanup, otherwise a late-spawned process is lost.
            self._launch_task = asyncio.create_task(
                asyncio.to_thread(
                    subprocess.Popen,
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs,
                )
            )
            self._process = await asyncio.shield(self._launch_task)
            owners = [
                {"pid": os.getpid(), "created": psutil.Process().create_time()},
                {"pid": self.pid, "created": psutil.Process(self.pid).create_time()},
            ]
            (Path(self._profile_dir) / "astrbot-owner.json").write_text(
                json.dumps(owners), encoding="utf-8"
            )
            ws_url = await self._wait_for_devtools_port()
            # No proxy is ever used for this loopback control connection. The
            # legacy websockets implementation ignores ambient proxy settings;
            # websockets 15+ needs an explicit proxy=None.
            ws_kwargs = {"max_size": _WS_MAX_SIZE, "open_timeout": 10}
            import inspect

            if "proxy" in inspect.signature(_ws_connect).parameters:
                ws_kwargs["proxy"] = None
            self._ws = await _ws_connect(ws_url, **ws_kwargs)
            self._ws_alive = True
            self._reader_task = asyncio.create_task(self._reader_loop())
            info = await self.send_command("Browser.getVersion", timeout=10)
            self.version = info.get("product", "")
        except BaseException as exc:
            await self.close()
            if isinstance(exc, (asyncio.CancelledError, BrowserLaunchError)):
                raise
            if not isinstance(exc, Exception):
                raise
            raise BrowserLaunchError(f"Failed to start system browser: {exc}") from exc

    async def _wait_for_devtools_port(self) -> str:
        port_file = Path(self._profile_dir) / "DevToolsActivePort"
        deadline = time.monotonic() + _LAUNCH_TIMEOUT
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise BrowserLaunchError(
                    f"Browser exited with code {self._process.returncode}"
                )
            try:
                lines = port_file.read_text(encoding="utf-8").splitlines()
                if (
                    len(lines) >= 2
                    and lines[0].isdigit()
                    and lines[1].startswith("/devtools/browser/")
                ):
                    return f"ws://127.0.0.1:{lines[0]}{lines[1]}"
            except OSError:
                pass
            await asyncio.sleep(0.05)
        raise BrowserLaunchError("Timed out waiting for the browser debugging endpoint")

    def is_connected(self) -> bool:
        return (
            not self._closed
            and self._close_task is None
            and self._ws_alive
            and self._process is not None
            and self._process.poll() is None
        )

    async def close(self):
        """Close once, preserving cleanup even if the calling task is cancelled."""
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self):
        try:
            if self._launch_task and self._process is None:
                try:
                    self._process = await self._launch_task
                except Exception:
                    pass
            if self._ws_alive:
                try:
                    await self.send_command("Browser.close", timeout=2)
                except BrowserError:
                    pass
            await self._terminate_process()
        finally:
            self._closed = True
            self._ws_alive = False
            if self._reader_task:
                self._reader_task.cancel()
                await asyncio.gather(self._reader_task, return_exceptions=True)
            if self._ws:
                await self._ws.close()
            self._fail_pending_commands("Browser closed")
            for page in list(self._pages.values()):
                for task in page._event_tasks:
                    task.cancel()
            self._pages.clear()
            await self._cleanup_profile_dir()

    async def _terminate_process(self):
        proc = self._process
        if proc is None or proc.poll() is not None:
            return
        try:
            await asyncio.to_thread(proc.wait, timeout=1)
            return
        except subprocess.TimeoutExpired:
            pass
        if os.name == "nt":
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await asyncio.to_thread(proc.wait, timeout=10)

    async def _cleanup_profile_dir(self):
        profile = self._profile_dir
        if not profile:
            return
        for attempt in range(3):
            await asyncio.to_thread(shutil.rmtree, profile, True)
            if not Path(profile).exists():
                self._profile_dir = ""
                return
            await asyncio.sleep(0.2 * (attempt + 1))
        logger.debug(
            "Temporary browser profile is still locked; leaving it for a later sweep"
        )

    async def send_command(
        self,
        method: str,
        params: dict | None = None,
        session_id: str | None = None,
        timeout: float | None = None,
    ) -> dict:
        """Send a CDP command and route its response by unique command ID.

        Args:
            method: CDP method name.
            params: Method arguments.
            session_id: Flattened target session for page-level commands.
            timeout: Total send/response deadline in seconds.

        Returns:
            The response result object.

        Raises:
            BrowserError: Disconnection, protocol failure or timeout.
        """
        if self._closed or not self._ws_alive:
            raise BrowserError("Browser connection is closed")
        self._next_command_id += 1
        command_id = self._next_command_id
        future = asyncio.get_running_loop().create_future()
        self._pending_commands[command_id] = future
        message = {"id": command_id, "method": method, "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        try:
            async with asyncio.timeout(
                timeout if timeout is not None else self.command_timeout
            ):
                async with self._send_lock:
                    await self._ws.send(json.dumps(message))
                return await future
        except TimeoutError:
            raise CdpTimeoutError(f"CDP command timed out: {method}") from None
        except (asyncio.CancelledError, BrowserError):
            raise
        except Exception as exc:
            raise BrowserError(f"CDP command failed: {method}") from exc
        finally:
            self._pending_commands.pop(command_id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()

    async def _reader_loop(self):
        try:
            async for raw in self._ws:
                message = json.loads(raw)
                if "id" in message:
                    future = self._pending_commands.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            error = message["error"]
                            future.set_exception(
                                CdpError(
                                    error.get("message", "Unknown CDP error"),
                                    error.get("code"),
                                )
                            )
                        else:
                            future.set_result(message.get("result", {}))
                elif message.get("sessionId") in self._pages:
                    self._pages[message["sessionId"]]._on_event(
                        message["method"], message.get("params", {})
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Browser DevTools connection ended")
        finally:
            self._ws_alive = False
            self._fail_pending_commands("Browser DevTools connection disconnected")

    def _fail_pending_commands(self, reason: str):
        for future in self._pending_commands.values():
            if not future.done():
                future.set_exception(BrowserError(reason))
        for page in self._pages.values():
            page._lifecycle_changed.set()

    async def new_page(
        self, viewport: dict | None = None, user_agent: str | None = None
    ) -> CDPPage:
        """Create and initialize an isolated tab, closing it on setup failure."""
        context = await self.send_command(
            "Target.createBrowserContext", {"disposeOnDetach": True}, timeout=15
        )
        context_id = context["browserContextId"]
        page = None
        try:
            result = await self.send_command(
                "Target.createTarget",
                {"url": "about:blank", "browserContextId": context_id},
                timeout=15,
            )
            target_id = result["targetId"]
            attached = await self.send_command(
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
                timeout=15,
            )
            page = CDPPage(
                self, target_id, attached["sessionId"], context_id=context_id
            )
            self._pages[page.session_id] = page
            await page._enable_domains()
            if user_agent:
                await page.set_user_agent(user_agent)
            if viewport:
                await page.set_viewport(viewport["width"], viewport["height"])
            return page
        except BaseException:
            if page:
                await page.close()
            else:
                try:
                    await self.send_command(
                        "Target.disposeBrowserContext",
                        {"browserContextId": context_id},
                        timeout=5,
                    )
                except BrowserError:
                    pass
            raise

    def remove_page(self, page: CDPPage):
        self._pages.pop(page.session_id, None)

    @property
    def page_count(self) -> int:
        return len(self._pages)

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    @property
    def profile_dir(self) -> str:
        return self._profile_dir
