"""
网页分析插件 - 缓存管理模块

这个模块负责管理网页分析结果的缓存，包括：
- 内存缓存和磁盘缓存的双层存储
- 缓存的自动过期和清理机制
- 截图等二进制数据的特殊处理
- 缓存统计信息的收集

使用缓存可以显著提高插件的响应速度，避免重复分析相同的网页内容。
"""

import os
import json
import time
import hashlib
from typing import Dict, Optional, Any

# 条件导入 logger，用于测试
logger = None
try:
    from astrbot.api import logger
except ImportError:
    # 测试环境下，创建一个简单的 logger 替代
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器

    负责管理网页分析结果的缓存，包括内存缓存和磁盘缓存。
    支持自动清理过期缓存和超出大小限制的缓存。
    """

    def __init__(
        self, cache_dir: str = None, max_size: int = 100, expire_time: int = 1440
    ):
        """初始化缓存管理器

        Args:
            cache_dir: 缓存文件存储目录，默认使用插件目录下的data/cache
            max_size: 最大缓存数量，超过会自动删除最旧的缓存
            expire_time: 缓存过期时间，单位为分钟
        """
        # 设置缓存目录
        if cache_dir:
            self.cache_dir = cache_dir
        else:
            # 默认缓存目录
            self.cache_dir = os.path.join(os.path.dirname(__file__), "data", "cache")

        # 确保缓存目录存在
        os.makedirs(self.cache_dir, exist_ok=True)

        self.max_size = max_size
        self.expire_time = expire_time * 60  # 转换为秒

        # 内存缓存
        self.memory_cache: Dict[str, Dict[str, Any]] = {}

        # 加载磁盘缓存到内存
        self._load_cache_from_disk()

    def _get_cache_file_path(self, url: str, file_type: str = "json") -> str:
        """根据URL生成唯一的缓存文件路径

        为了避免URL中的特殊字符导致的文件名问题，我们使用URL的MD5哈希值作为文件名。

        Args:
            url: 网页的完整URL
            file_type: 文件类型，json表示分析结果，screenshot表示截图

        Returns:
            完整的缓存文件路径
        """
        # 使用URL的MD5哈希作为文件名
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        if file_type == "screenshot":
            return os.path.join(self.cache_dir, f"{url_hash}_screenshot.bin")
        return os.path.join(self.cache_dir, f"{url_hash}.json")

    def _load_cache_from_disk(self):
        """从磁盘加载缓存到内存

        启动时调用，将磁盘中保存的缓存加载到内存中，
        只加载最新的不超过max_size个缓存文件，
        并自动修复损坏的缓存文件。
        """
        try:
            # 获取所有缓存文件
            cache_files = [f for f in os.listdir(self.cache_dir) if f.endswith(".json")]

            # 按修改时间排序，保留最新的缓存
            cache_files.sort(
                key=lambda f: os.path.getmtime(os.path.join(self.cache_dir, f)),
                reverse=True,
            )

            # 只加载不超过最大数量的缓存
            for cache_file in cache_files[: self.max_size]:
                file_path = os.path.join(self.cache_dir, cache_file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        url = cache_data.get("url")
                        if url:
                            # 检查是否有截图文件
                            result = cache_data.get("result", {})
                            if isinstance(result, dict) and result.get(
                                "has_screenshot", False
                            ):
                                # 读取截图文件
                                screenshot_path = self._get_cache_file_path(
                                    url, "screenshot"
                                )
                                if os.path.exists(screenshot_path):
                                    with open(screenshot_path, "rb") as sf:
                                        result["screenshot"] = sf.read()
                                    # 移除标记，因为现在已经有了实际的截图数据
                                    result.pop("has_screenshot", None)

                            self.memory_cache[url] = cache_data
                except Exception as e:
                    logger.error(f"加载缓存文件失败: {file_path}, 错误: {e}")
                    # 删除损坏的缓存文件
                    os.remove(file_path)
        except Exception as e:
            logger.error(f"从磁盘加载缓存失败: {e}")

    def _save_cache_to_disk(self, url: str, cache_data: Dict[str, Any]):
        """将缓存数据保存到磁盘

        处理缓存数据的持久化，包括：
        - 分析结果的JSON序列化
        - 截图等二进制数据的单独存储
        - 缓存数据的完整性验证

        Args:
            url: 网页的完整URL
            cache_data: 包含分析结果和时间戳的完整缓存数据
        """
        try:
            # 创建一个副本，避免修改原始数据
            cache_data_copy = cache_data.copy()
            result = cache_data_copy.get("result", {})
            has_screenshot = False

            # 处理截图数据，JSON不支持bytes类型
            if (
                isinstance(result, dict)
                and "screenshot" in result
                and isinstance(result["screenshot"], bytes)
            ):
                # 将截图保存为二进制文件
                screenshot_path = self._get_cache_file_path(url, "screenshot")
                with open(screenshot_path, "wb") as f:
                    f.write(result["screenshot"])
                has_screenshot = True

                # 从JSON数据中移除截图bytes，添加截图存在标记
                result_copy = result.copy()
                result_copy.pop("screenshot", None)
                result_copy["has_screenshot"] = True
                cache_data_copy["result"] = result_copy

            file_path = self._get_cache_file_path(url)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(cache_data_copy, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存到磁盘失败: {url}, 错误: {e}")

    def _remove_cache_from_disk(self, url: str):
        """从磁盘删除指定URL的缓存

        删除缓存文件，包括：
        - 分析结果的JSON文件
        - 对应的截图二进制文件（如果存在）

        Args:
            url: 要删除缓存的网页URL
        """
        try:
            # 删除JSON缓存文件
            file_path = self._get_cache_file_path(url)
            if os.path.exists(file_path):
                os.remove(file_path)

            # 删除截图文件
            screenshot_path = self._get_cache_file_path(url, "screenshot")
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
        except Exception as e:
            logger.error(f"从磁盘删除缓存失败: {url}, 错误: {e}")

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """获取指定URL的缓存结果

        检查缓存是否存在且未过期，如果缓存有效则返回分析结果，
        否则返回None并自动清理过期缓存。

        Args:
            url: 要获取缓存的网页URL

        Returns:
            缓存的分析结果，如果不存在或已过期则返回None
        """
        current_time = time.time()

        if url in self.memory_cache:
            cache_data = self.memory_cache[url]
            # 检查缓存是否过期
            if current_time - cache_data.get("timestamp", 0) < self.expire_time:
                return cache_data.get("result")
            else:
                # 缓存过期，删除
                self.delete(url)

        return None

    def set(self, url: str, result: Dict[str, Any]):
        """设置指定URL的缓存结果

        保存分析结果到缓存，包括：
        - 添加时间戳标记
        - 内存缓存的更新
        - 磁盘缓存的持久化
        - 超过大小限制时的自动清理

        Args:
            url: 网页的完整URL
            result: 网页分析结果，包含文本、截图等信息
        """
        current_time = time.time()

        # 创建缓存数据
        cache_data = {"url": url, "timestamp": current_time, "result": result}

        # 添加到内存缓存
        self.memory_cache[url] = cache_data

        # 保存到磁盘
        self._save_cache_to_disk(url, cache_data)

        # 检查缓存大小，超过最大限制则删除最旧的缓存
        self._cleanup()

    def delete(self, url: str):
        """删除指定URL的缓存

        从内存和磁盘中同时删除缓存数据，确保缓存的一致性。

        Args:
            url: 要删除缓存的网页URL
        """
        if url in self.memory_cache:
            # 从内存删除
            del self.memory_cache[url]
            # 从磁盘删除
            self._remove_cache_from_disk(url)

    def clear(self):
        """清空所有缓存数据

        清除内存中的所有缓存，并删除磁盘上的所有缓存文件，
        用于重置缓存状态或释放磁盘空间。
        """
        # 清空内存缓存
        self.memory_cache.clear()

        # 清空磁盘缓存
        try:
            for file in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, file)
                # 删除JSON缓存文件和截图文件
                if file.endswith(".json") or file.endswith("_screenshot.bin"):
                    os.remove(file_path)
        except Exception as e:
            logger.error(f"清空磁盘缓存失败: {e}")

    def _cleanup(self):
        """清理缓存，保持缓存的健康状态

        执行两项清理任务：
        1. 删除所有已过期的缓存（基于expire_time）
        2. 如果缓存数量超过max_size，删除最旧的缓存

        这个方法会在每次添加新缓存后自动调用。
        """
        current_time = time.time()

        # 清理过期缓存
        expired_urls = []
        for url, cache_data in self.memory_cache.items():
            if current_time - cache_data.get("timestamp", 0) >= self.expire_time:
                expired_urls.append(url)

        for url in expired_urls:
            self.delete(url)

        # 检查是否超出最大缓存大小
        if len(self.memory_cache) > self.max_size:
            # 按时间排序，删除最旧的缓存
            sorted_urls = sorted(
                self.memory_cache.keys(),
                key=lambda url: self.memory_cache[url].get("timestamp", 0),
            )

            # 删除超出部分
            for url in sorted_urls[: len(self.memory_cache) - self.max_size]:
                self.delete(url)

    def get_stats(self) -> Dict[str, int]:
        """获取缓存的统计信息

        提供缓存的整体状态，包括：
        - 总缓存数量
        - 有效缓存数量（未过期）
        - 过期缓存数量

        Returns:
            包含缓存统计数据的字典
        """
        current_time = time.time()
        valid_count = 0
        expired_count = 0

        for cache_data in self.memory_cache.values():
            if current_time - cache_data.get("timestamp", 0) < self.expire_time:
                valid_count += 1
            else:
                expired_count += 1

        return {
            "total": len(self.memory_cache),
            "valid": valid_count,
            "expired": expired_count,
        }
