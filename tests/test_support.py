"""Shared module loader for the plugin test suite.

Stubs ``astrbot.api`` and loads the plugin's core modules directly so tests
run without a live AstrBot instance.
"""

import importlib.util
import sys
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

_PACKAGE_NAME = "web_analyzer_test_package"
_CORE_MODULES = (
    "urls",
    "constants",
    "error_handler",
    "browser",
    "screenshot",
    "content_fetcher",
    "cache",
    "capture_pipeline",
    "messaging",
    "config_loader",
)


def _load_package():
    package = types.ModuleType(_PACKAGE_NAME)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules.setdefault(_PACKAGE_NAME, package)

    core_name = f"{_PACKAGE_NAME}.core"
    core_package = types.ModuleType(core_name)
    core_package.__path__ = [str(PLUGIN_ROOT / "core")]
    sys.modules.setdefault(core_name, core_package)

    # Force-stub the astrbot namespace so tests never touch the live
    # AstrBot data directory; plugin data resolves into a scratch dir.
    astrbot = types.ModuleType("astrbot")
    astrbot.__path__ = []
    sys.modules["astrbot"] = astrbot
    api = types.ModuleType("astrbot.api")
    api.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        critical=lambda *args, **kwargs: None,
        log=lambda *args, **kwargs: None,
    )
    api.AstrBotConfig = dict
    sys.modules["astrbot.api"] = api
    star = types.ModuleType("astrbot.api.star")
    star.Context = type("Context", (), {})
    sys.modules["astrbot.api.star"] = star
    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = type("AstrMessageEvent", (), {})
    sys.modules["astrbot.api.event"] = event

    core_pkg = types.ModuleType("astrbot.core")
    utils_pkg = types.ModuleType("astrbot.core.utils")
    astrbot_path = types.ModuleType("astrbot.core.utils.astrbot_path")
    astrbot_path.get_astrbot_plugin_data_path = lambda: str(
        PLUGIN_ROOT / "tests" / ".scratch" / "plugin_data"
    )
    astrbot_path.get_astrbot_data_path = lambda: str(PLUGIN_ROOT / "tests" / ".scratch")
    sys.modules["astrbot.core"] = core_pkg
    sys.modules["astrbot.core.utils"] = utils_pkg
    sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path

    # Minimal astrbot.api.web stand-in for dashboard handler tests.
    web = types.ModuleType("astrbot.api.web")

    def json_response(data, status_code=200):
        import json as _json

        return types.SimpleNamespace(
            body=_json.dumps(data, ensure_ascii=False), status_code=status_code
        )

    class _FakeRequest:
        def __init__(self):
            self.query = {}
            self._json = {}

        async def json(self, default=None):
            return (
                self._json if self._json else (default if default is not None else {})
            )

    web.json_response = json_response
    web.request = _FakeRequest()
    sys.modules["astrbot.api.web"] = web

    for module_name in _CORE_MODULES:
        full_name = f"{core_name}.{module_name}"
        if full_name in sys.modules:
            continue
        module_path = PLUGIN_ROOT / "core" / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(full_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)

    loaded = {name: sys.modules[f"{core_name}.{name}"] for name in _CORE_MODULES}
    return types.SimpleNamespace(**loaded)


modules = _load_package()

urls_module = modules.urls
constants_module = modules.constants
error_handler_module = modules.error_handler
browser_module = modules.browser
screenshot_module = modules.screenshot
content_fetcher_module = modules.content_fetcher
cache_module = modules.cache
capture_pipeline_module = modules.capture_pipeline
messaging_module = modules.messaging
config_loader_module = modules.config_loader

ScreenshotService = screenshot_module.ScreenshotService
ScreenshotError = screenshot_module.ScreenshotError
ContentFetcher = content_fetcher_module.ContentFetcher
FetchError = content_fetcher_module.FetchError
ScreenshotCache = cache_module.ScreenshotCache
CapturePipeline = capture_pipeline_module.CapturePipeline
CaptureSettings = capture_pipeline_module.CaptureSettings
ConfigLoader = config_loader_module.ConfigLoader
MessageHelpers = messaging_module.MessageHelpers
extract_urls = urls_module.extract_urls
is_valid_url = urls_module.is_valid_url
normalize_url = urls_module.normalize_url
is_domain_allowed = urls_module.is_domain_allowed
