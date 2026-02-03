
"""
截图临时文件管理模块

负责管理截图临时文件的创建、复用和清理，使用 TTL 机制避免并发问题。
"""

import os
import time
import asyncio
from collections import OrderedDict
from typing import Optional
from pathlib import Path

# 条件导入 logger
logger = None
try:
    from astrbot.api import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class ScreenshotTempManager:
    """截图临时文件管理器
    
    管理截图临时文件的创建、复用和自动清理，使用 TTL 机制确保文件生命周期。
    """

    def __init__(
        self,
        temp_dir: str = None,
        ttl: int = 60,
        cleanup_interval: int = 60,
        max_memory_cache: int = 30
    ):
        """初始化临时文件管理器
        
        Args:
            temp_dir: 临时文件目录，默认使用项目根目录下的 data/temp
            ttl: 文件生存期（秒），默认 60 秒
            cleanup_interval: 清理任务执行间隔（秒），默认 60 秒
            max_memory_cache: 内存缓存最大容量，默认 30 张截图
        """
        # 初始化临时文件目录
        self.temp_dir = self._initialize_temp_dir(temp_dir)
        
        # 配置参数
        self.ttl = ttl
        self.cleanup_interval = cleanup_interval
        self.max_memory_cache = max_memory_cache
        
        # 文件元数据记录：{url_hash: {"path": str, "created_at": float}}
        self._file_metadata: dict[str, dict] = {}
        
        # 内存缓存：使用 OrderedDict 实现 LRU 缓存
        self._memory_cache: OrderedDict[str, bytes] = OrderedDict()
        
        # 清理任务引用
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # 启动后台清理任务
        self._start_cleanup_task()
        
        logger.info(
            f"ScreenshotTempManager 初始化完成: "
            f"temp_dir={self.temp_dir}, ttl={ttl}s, "
            f"max_memory_cache={max_memory_cache}"
        )

    def _initialize_temp_dir(self, temp_dir: str | None) -> str:
        """初始化临时文件目录
        
        Args:
            temp_dir: 用户指定的临时目录
            
        Returns:
            最终使用的临时目录路径
        """
        if not temp_dir:
            # 使用默认临时目录（项目根目录下的 data/temp）
            project_root = os.path.dirname(os.path.dirname(__file__))
            temp_dir = os.path.join(project_root, "data", "temp")
        
        # 确保目录存在
        os.makedirs(temp_dir, exist_ok=True)
        
        return temp_dir

    def _start_cleanup_task(self):
        """启动后台清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("后台清理任务已启动")

    async def _cleanup_loop(self):
        """后台清理循环，定期清理过期的临时文件"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired_files()
            except asyncio.CancelledError:
                logger.info("清理任务被取消")
                break
            except Exception as e:
                logger.error(f"清理任务执行失败: {e}")

    async def _cleanup_expired_files(self):
        """清理所有过期的临时文件"""
        current_time = time.time()
        expired_hashes = []
        
        # 查找过期的文件
        for url_hash, metadata in self._file_metadata.items():
            if current_time - metadata["created_at"] > self.ttl:
                expired_hashes.append(url_hash)
        
        # 删除过期文件
        for url_hash in expired_hashes:
            await self._remove_file(url_hash)
        
        if expired_hashes:
            logger.info(f"清理了 {len(expired_hashes)} 个过期的临时文件")

    async def _remove_file(self, url_hash: str):
        """删除指定的临时文件
        
        Args:
            url_hash: URL 哈希值
        """
        if url_hash not in self._file_metadata:
            return
        
        metadata = self._file_metadata[url_hash]
        file_path = metadata["path"]
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"删除临时文件: {file_path}")
        except Exception as e:
            logger.error(f"删除临时文件失败: {file_path}, 错误: {e}")
        finally:
            # 从元数据中移除
            del self._file_metadata[url_hash]
            # 从内存缓存中移除
            if url_hash in self._memory_cache:
                del self._memory_cache[url_hash]

    def _get_url_hash(self, url: str) -> str:
        """计算 URL 的哈希值
        
        Args:
            url: 网页 URL
            
        Returns:
            URL 的 MD5 哈希值
        """
        import hashlib
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def _update_lru_cache(self, url_hash: str):
        """更新 LRU 缓存顺序
        
        Args:
            url_hash: URL 哈希值
        """
        if url_hash in self._memory_cache:
            # 移动到末尾（最近使用）
            self._memory_cache.move_to_end(url_hash)

    def _ensure_cache_size(self):
        """确保内存缓存不超过最大容量"""
        while len(self._memory_cache) >= self.max_memory_cache:
            # 移除最久未使用的项
            oldest_hash, _ = self._memory_cache.popitem(last=False)
            logger.debug(f"LRU 缓存已满，移除最久未使用的截图: {oldest_hash}")

    def get_from_memory(self, url: str) -> Optional[bytes]:
        """从内存缓存获取截图数据
        
        Args:
            url: 网页 URL
            
        Returns:
            截图二进制数据，如果不存在则返回 None
        """
        url_hash = self._get_url_hash(url)
        if url_hash in self._memory_cache:
            # 更新 LRU 顺序
            self._update_lru_cache(url_hash)
            logger.debug(f"从内存缓存获取截图: {url}")
            return self._memory_cache[url_hash]
        return None

    def put_to_memory(self, url: str, screenshot: bytes):
        """将截图数据放入内存缓存
        
        Args:
            url: 网页 URL
            screenshot: 截图二进制数据
        """
        url_hash = self._get_url_hash(url)
        
        # 确保缓存不超过最大容量
        self._ensure_cache_size()
        
        # 添加到缓存
        self._memory_cache[url_hash] = screenshot
        logger.debug(f"截图已添加到内存缓存: {url}, 大小: {len(screenshot)} 字节")

    async def get_or_create_temp_path(
        self, 
        url: str, 
        screenshot: Optional[bytes] = None,
        screenshot_format: str = "jpeg",
        cache_dir: Optional[str] = None
    ) -> Optional[str]:
        """获取缓存截图文件路径
        
        优先返回缓存目录中的截图文件路径。如果截图数据存在但缓存文件不存在，
        则创建缓存文件并返回其路径。
        
        Args:
            url: 网页 URL
            screenshot: 截图二进制数据（可选，用于保存到缓存）
            screenshot_format: 截图格式（jpeg, png 等）
            cache_dir: 缓存目录路径
            
        Returns:
            缓存文件路径，如果获取失败则返回 None
        """
        if not cache_dir:
            cache_dir = self.temp_dir
        
        url_hash = self._get_url_hash(url)
        
        # 构建缓存截图文件路径
        cache_screenshot_path = os.path.join(cache_dir, f"{url_hash}_screenshot.bin")
        
        # 检查缓存文件是否存在
        if os.path.exists(cache_screenshot_path):
            logger.debug(f"使用缓存截图文件: {cache_screenshot_path}")
            
            # 如果有新的截图数据，更新内存缓存
            if screenshot:
                self.put_to_memory(url, screenshot)
            
            return cache_screenshot_path
        
        # 缓存文件不存在，如果有截图数据则创建缓存文件
        if screenshot:
            try:
                # 写入缓存文件
                with open(cache_screenshot_path, "wb") as f:
                    f.write(screenshot)
                
                # 添加到内存缓存
                self.put_to_memory(url, screenshot)
                
                logger.info(
                    f"创建缓存截图文件: {cache_screenshot_path}, "
                    f"大小: {len(screenshot)} 字节"
                )
                return cache_screenshot_path
                
            except Exception as e:
                logger.error(f"创建缓存截图文件失败: {cache_screenshot_path}, 错误: {e}")
                return None
        
        logger.warning(f"无截图数据且缓存文件不存在: {url}")
        return None

    async def prepare_screenshots(
        self,
        urls_and_screenshots: list[tuple[str, Optional[bytes]]],
        screenshot_format: str = "jpeg"
    ) -> list[Optional[str]]:
        """批量准备截图临时文件路径
        
        Args:
            urls_and_screenshots: (url, screenshot) 元组列表
            screenshot_format: 截图格式
            
        Returns:
            临时文件路径列表
        """
        # 并发准备所有截图
        tasks = [
            self.get_or_create_temp_path(url, screenshot, screenshot_format)
            for url, screenshot in urls_and_screenshots
        ]
        return await asyncio.gather(*tasks)

    async def get_screenshot_for_send(
        self,
        url: str,
        load_from_disk_func=None,
        screenshot_format: str = "jpeg"
    ) -> Optional[str]:
        """获取用于发送的截图路径
        
        按以下优先级查找：
        1. 内存缓存
        2. 临时文件（未过期）
        3. 从磁盘加载（通过提供的回调函数）
        
        Args:
            url: 网页 URL
            load_from_disk_func: 从磁盘加载截图的回调函数
            screenshot_format: 截图格式
            
        Returns:
            临时文件路径，如果获取失败则返回 None
        """
        url_hash = self._get_url_hash(url)
        
        # 1. 检查内存缓存
        if url_hash in self._memory_cache:
            screenshot = self._memory_cache[url_hash]
            self._update_lru_cache(url_hash)
            return await self.get_or_create_temp_path(url, screenshot, screenshot_format)
        
        # 2. 检查是否有未过期的临时文件
        if url_hash in self._file_metadata:
            metadata = self._file_metadata[url_hash]
            if time.time() - metadata["created_at"] <= self.ttl:
                file_path = metadata["path"]
                if os.path.exists(file_path):
                    # 文件存在且未过期，直接使用
                    return file_path
        
        # 3. 从磁盘加载
        if load_from_disk_func:
            try:
                screenshot = load_from_disk_func(url)
                if screenshot:
                    return await self.get_or_create_temp_path(url, screenshot, screenshot_format)
            except Exception as e:
                logger.error(f"从磁盘加载截图失败: {url}, 错误: {e}")
        
        return None

    def clear_all(self):
        """清空所有临时文件和缓存"""
        # 清空内存缓存
        self._memory_cache.clear()
        
        # 删除所有临时文件
        for url_hash, metadata in list(self._file_metadata.items()):
            try:
                file_path = metadata["path"]
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"删除临时文件失败: {metadata['path']}, 错误: {e}")
        
        # 清空元数据
        self._file_metadata.clear()
        
        logger.info("已清空所有临时文件和缓存")

    async def shutdown(self):
        """关闭管理器，停止清理任务"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("ScreenshotTempManager 已关闭")

    def get_stats(self) -> dict:
        """获取统计信息
        
        Returns:
            包含统计数据的字典
        """
        current_time = time.time()
        active_files = sum(
            1 for metadata in self._file_metadata.values()
            if current_time - metadata["created_at"] <= self.ttl
        )
        
        return {
            "temp_dir": self.temp_dir,
            "memory_cache_size": len(self._memory_cache),
            "memory_cache_max": self.max_memory_cache,
            "active_files": active_files,
            "total_files": len(self._file_metadata),
            "ttl": self.ttl
        }