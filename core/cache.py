"""
截图缓存模块

按 URL 与截图参数联合命中缓存：任何影响输出的参数变化都会产生新的缓存条目。
缓存为内存 LRU + 磁盘双层存储；截图二进制与 JSON 元数据同目录存放。

有效期只在构造时换算一次（分钟 → 秒），运行中更新直接以秒赋值，
避免历史版本中分钟被重复换算的问题。旧版本（仅按 URL 键控）的缓存文件
保留在原目录，在列表中按「旧版条目」展示，自然过期。
"""

import hashlib
import json
import os
import time
from typing import Any

from astrbot.api import logger

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path
except ImportError:  # 兼容旧版本
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path as _get_data

    def get_astrbot_plugin_data_path():
        import os

        return os.path.join(_get_data(), "plugin_data")


# 影响截图输出的参数字段，参与缓存键
_CACHE_PARAM_FIELDS = (
    "width",
    "height",
    "full_page",
    "format",
    "quality",
    "wait_strategy",
    "wait_time",
)


def build_cache_key(url: str, params: dict) -> str:
    """按 URL 与截图参数生成 32 位缓存键。"""
    parts = [str(params.get(field, "")) for field in _CACHE_PARAM_FIELDS]
    payload = url + "|" + "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class ScreenshotCache:
    """截图缓存管理器。"""

    def __init__(
        self,
        cache_dir: str | None = None,
        max_size: int = 100,
        expire_minutes: int = 1440,
        enabled: bool = True,
    ):
        """初始化缓存。

        Args:
            cache_dir: 缓存目录，默认使用插件数据目录下的 cache 子目录。
            max_size: 缓存条数上限，超出按 LRU 淘汰。
            expire_minutes: 有效期（分钟），只在构造时换算为秒。
            enabled: 是否启用缓存；停用时读不到、也不写入。
        """
        self.cache_dir = self._initialize_cache_dir(cache_dir)
        self.enabled = enabled
        self.max_size = max(1, int(max_size))
        # 唯一一次单位换算：之后 expire_seconds 直接以秒比较
        self.expire_seconds = max(1, int(expire_minutes)) * 60
        self._entries: dict[str, dict[str, Any]] = {}
        self._last_used: dict[str, float] = {}
        self._load_from_disk()

    def _initialize_cache_dir(self, cache_dir: str | None) -> str:
        """初始化并确保缓存目录存在。"""
        if not cache_dir:
            cache_dir = os.path.join(
                get_astrbot_plugin_data_path(),
                "astrbot_plugin_web_analyzer",
                "cache",
            )
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    # ==================== 读取 ====================

    def get(self, key: str) -> dict[str, Any] | None:
        """按缓存键取有效条目（LRU 触碰），过期或不存在返回 None。

        返回的条目包含 url / params / timestamp / result；
        截图二进制按需通过 get_screenshot 读取。
        """
        if not self.enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            self.delete(key)
            return None
        self._last_used[key] = time.time()
        return entry

    def get_screenshot(self, key: str) -> bytes | None:
        """读取缓存键对应的截图二进制。"""
        path = self._bin_path(key)
        try:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return f.read()
        except OSError as e:
            logger.warning(f"读取缓存截图失败: {path}, 错误: {e}")
        return None

    def _is_expired(self, entry: dict[str, Any]) -> bool:
        return time.time() - entry.get("timestamp", 0) >= self.expire_seconds

    # ==================== 写入 ====================

    def put(
        self,
        key: str,
        url: str,
        params: dict,
        result: dict[str, Any],
        screenshot: bytes | None = None,
    ):
        """写入一条缓存（内存 + 磁盘），并执行过期与容量清理。"""
        entry = {
            "url": url,
            "params": dict(params),
            "timestamp": time.time(),
            "result": dict(result),
        }
        self._entries[key] = entry
        self._last_used[key] = entry["timestamp"]
        self._save_to_disk(key, entry, screenshot)
        self._cleanup()

    # ==================== 删除与清空 ====================

    def delete(self, key: str):
        """删除指定缓存条目（内存 + 磁盘）。"""
        self._entries.pop(key, None)
        self._last_used.pop(key, None)
        for suffix in (".json", "_screenshot.bin"):
            path = os.path.join(self.cache_dir, f"{key}{suffix}")
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                logger.warning(f"删除缓存文件失败: {path}, 错误: {e}")

    def clear(self):
        """清空全部内存与磁盘缓存。"""
        self._entries.clear()
        self._last_used.clear()
        try:
            for name in os.listdir(self.cache_dir):
                if name.endswith(".json") or name.endswith("_screenshot.bin"):
                    try:
                        os.remove(os.path.join(self.cache_dir, name))
                    except OSError as e:
                        logger.warning(f"删除缓存文件失败: {name}, 错误: {e}")
        except OSError as e:
            logger.warning(f"清空缓存目录失败: {e}")

    # ==================== 列表与统计 ====================

    def get_stats(self) -> dict[str, int]:
        """返回 (总数, 有效, 过期) 统计。"""
        now = time.time()
        valid = sum(
            1
            for entry in self._entries.values()
            if now - entry.get("timestamp", 0) < self.expire_seconds
        )
        total = len(self._entries)
        return {"total": total, "valid": valid, "expired": total - valid}

    def list_entries(self, query: str = "") -> list[dict[str, Any]]:
        """按时间倒序列出缓存条目（含磁盘上的旧版条目），可按 URL 过滤。

        每个条目包含 id / url / title / params / timestamp / expired /
        has_screenshot / legacy。
        """
        now = time.time()
        items: dict[str, dict[str, Any]] = {}

        for key, entry in self._entries.items():
            result = entry.get("result", {})
            items[key] = {
                "id": key,
                "url": entry.get("url", ""),
                "title": result.get("title", ""),
                "params": entry.get("params", {}),
                "timestamp": entry.get("timestamp", 0),
                "expired": self._is_expired(entry),
                "has_screenshot": bool(result.get("has_screenshot")),
                "legacy": False,
            }

        # 磁盘上的旧版条目（仅按 URL 键控，内存中未加载）
        legacy_params = {"wait_time": "", "legacy": True}
        for name in os.listdir(self.cache_dir):
            if not name.endswith(".json"):
                continue
            key = name[: -len(".json")]
            if key in items:
                continue
            path = os.path.join(self.cache_dir, name)
            try:
                mtime = os.path.getmtime(path)
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                url = data.get("url", "")
                if query and query.lower() not in url.lower():
                    continue
                result = data.get("result", {})
                has_screenshot = bool(
                    isinstance(result, dict) and result.get("has_screenshot")
                ) or os.path.exists(self._bin_path(key))
                items[key] = {
                    "id": key,
                    "url": url,
                    "title": (
                        result.get("title", "") if isinstance(result, dict) else ""
                    ),
                    "params": legacy_params,
                    "timestamp": data.get("timestamp", mtime),
                    "expired": now - data.get("timestamp", mtime)
                    >= self.expire_seconds,
                    "has_screenshot": has_screenshot,
                    "legacy": True,
                }
            except (OSError, ValueError) as e:
                logger.debug(f"跳过无法读取的缓存文件 {name}: {e}")

        query_lower = query.lower()
        results = [
            item
            for item in items.values()
            if not query_lower or query_lower in item["url"].lower()
        ]
        results.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
        return results

    def get_file_path(self, key: str) -> str | None:
        """返回缓存截图文件路径（供页面预览直接读取）。"""
        path = self._bin_path(key)
        return path if os.path.exists(path) else None

    # ==================== 磁盘持久化 ====================

    def _json_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.json")

    def _bin_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}_screenshot.bin")

    def _load_from_disk(self):
        """启动时加载最新的不超过上限的缓存元数据（不含截图二进制）。"""
        try:
            names = [n for n in os.listdir(self.cache_dir) if n.endswith(".json")]
            names.sort(
                key=lambda n: os.path.getmtime(os.path.join(self.cache_dir, n)),
                reverse=True,
            )
            for name in names[: self.max_size]:
                path = os.path.join(self.cache_dir, name)
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    key = name[: -len(".json")]
                    if data.get("url"):
                        self._entries[key] = data
                except (OSError, ValueError) as e:
                    logger.debug(f"跳过损坏的缓存文件 {name}: {e}")
                    self._remove_files_quietly(name[: -len(".json")])
        except OSError as e:
            logger.error(f"从磁盘加载缓存失败: {e}")

    def _save_to_disk(self, key: str, entry: dict[str, Any], screenshot: bytes | None):
        """写入元数据 JSON 与截图二进制。"""
        try:
            if screenshot is not None:
                with open(self._bin_path(key), "wb") as f:
                    f.write(screenshot)
                entry.setdefault("result", {})["has_screenshot"] = True
            with open(self._json_path(key), "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
        except OSError as e:
            logger.warning(f"写入缓存失败: {key}, 错误: {e}")

    def _remove_files_quietly(self, key: str):
        for suffix in (".json", "_screenshot.bin"):
            try:
                os.remove(os.path.join(self.cache_dir, f"{key}{suffix}"))
            except OSError:
                pass

    # ==================== 清理 ====================

    def _cleanup(self):
        """删除过期条目，再按 LRU 淘汰超出上限的部分。"""
        now = time.time()
        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.get("timestamp", 0) >= self.expire_seconds
        ]
        for key in expired:
            self.delete(key)
        if len(self._entries) > self.max_size:
            ordered = sorted(
                self._entries,
                key=lambda key: self._last_used.get(key, 0),
            )
            for key in ordered[: len(self._entries) - self.max_size]:
                self.delete(key)
