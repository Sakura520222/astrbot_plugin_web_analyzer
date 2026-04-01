"""
插件辅助方法模块

提供各种辅助检查和处理方法，包括：
- 群组和域名检查
- 错误处理
- 结果格式化应用
- 消息发送和撤回
"""

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .error_handler import ErrorHandler
from .result_formatter import ResultFormatter
from .utils import WebAnalyzerUtils


class PluginHelpers:
    """插件辅助方法类，提供静态辅助方法"""

    @staticmethod
    def is_group_blacklisted(group_id: str, group_blacklist: list) -> bool:
        """检查指定群聊是否在黑名单中

        Args:
            group_id: 群聊ID
            group_blacklist: 群聊黑名单列表

        Returns:
            是否在黑名单中
        """
        if not group_id or not group_blacklist:
            return False
        return group_id in group_blacklist

    @staticmethod
    def get_group_id(event: AstrMessageEvent) -> str | None:
        """从事件对象中获取群聊ID，兼容不同版本的事件对象

        Args:
            event: 消息事件对象

        Returns:
            群聊ID字符串或None
        """
        group_id = None
        if hasattr(event, "unified_msg_origin"):
            umo = event.unified_msg_origin
            if isinstance(umo, str):
                # 如果是字符串，无法获取 group_id
                group_id = None
            elif hasattr(umo, "group_id"):
                group_id = umo.group_id
        elif hasattr(event, "group_id"):
            group_id = event.group_id
        return group_id

    @staticmethod
    def is_domain_allowed(
        url: str, allowed_domains: list, blocked_domains: list
    ) -> bool:
        """检查指定URL的域名是否允许访问

        Args:
            url: 网页URL
            allowed_domains: 允许的域名列表
            blocked_domains: 禁止的域名列表

        Returns:
            是否允许访问
        """
        return WebAnalyzerUtils.is_domain_allowed(url, allowed_domains, blocked_domains)

    @staticmethod
    def handle_error(
        error_type: str,
        original_error: Exception,
        url: str | None = None,
        context: dict | None = None,
    ) -> str:
        """统一错误处理方法

        Args:
            error_type: 错误类型
            original_error: 原始异常
            url: 网页URL（可选）
            context: 上下文信息（可选）

        Returns:
            格式化的错误消息
        """
        return ErrorHandler.handle_error(error_type, original_error, url, context)

    @staticmethod
    def get_error_type(exception: Exception) -> str:
        """根据异常类型获取对应的错误类型

        Args:
            exception: 异常对象

        Returns:
            错误类型字符串
        """
        return ErrorHandler.get_error_type(exception)

    @staticmethod
    def apply_result_settings(
        result_formatter: ResultFormatter,
        result: str,
        url: str,
        content_data: dict = None,
        **kwargs,
    ) -> str:
        """应用所有结果设置

        Args:
            result_formatter: 结果格式化器实例
            result: 分析结果
            url: 网页URL
            content_data: 内容数据（可选）
            **kwargs: 其他配置参数

        Returns:
            格式化后的结果
        """
        return result_formatter.apply_result_settings(
            result=result,
            url=url,
            content_data=content_data,
            **kwargs,
        )

    @staticmethod
    def get_enhanced_analysis(
        result_formatter: ResultFormatter, content_data: dict
    ) -> str:
        """获取增强版基础分析

        Args:
            result_formatter: 结果格式化器实例
            content_data: 内容数据字典

        Returns:
            格式化的增强分析结果
        """
        return result_formatter.build_enhanced_analysis(content_data)


class MessageHelpers:
    """消息发送和撤回辅助方法类"""

    @staticmethod
    async def send_processing_message(
        event: AstrMessageEvent,
        message: str,
        enable_recall: bool,
        recall_type: str,
        recall_time_s: int,
        smart_recall_enabled: bool,
        recall_tasks: list,
    ) -> tuple:
        """发送处理提示消息并设置自动撤回

        Args:
            event: 消息事件对象
            message: 要发送的消息
            enable_recall: 是否启用撤回
            recall_type: 撤回类型
            recall_time_s: 撤回时间（秒）
            smart_recall_enabled: 是否启用智能撤回
            recall_tasks: 撤回任务列表

        Returns:
            (message_id, bot) 元组
        """
        import asyncio

        # 获取平台名称
        platform_name = (
            event.get_platform_name() if hasattr(event, "get_platform_name") else None
        )

        # 获取bot/client实例（兼容不同类型的事件）
        bot = event.bot if hasattr(event, "bot") else None
        # Telegram 平台使用 client 属性
        client = event.client if hasattr(event, "client") else None

        message_id = None

        # 直接调用bot/client的发送消息方法，获取消息ID
        try:
            # 根据事件类型选择发送方法
            send_result = None
            group_id = None
            user_id = None

            # 方法1：使用AiocqhttpMessageEvent的方法获取
            if hasattr(event, "get_group_id"):
                group_id = event.get_group_id()
            if hasattr(event, "get_sender_id"):
                user_id = event.get_sender_id()

            # 方法2：判断是否为私聊
            is_private = False
            if hasattr(event, "is_private_chat"):
                is_private = event.is_private_chat()

            # Telegram 平台特殊处理
            if platform_name == "telegram" and client:
                chat_id = group_id if group_id else user_id
                if chat_id:
                    # 处理 topic 群组的 chat_id（去掉 # 后面的 thread_id）
                    if "#" in chat_id:
                        chat_id = chat_id.split("#")[0]
                    # Telegram 发送消息并获取 message_id
                    msg = await client.send_message(chat_id=int(chat_id), text=message)
                    message_id = msg.message_id
                    logger.debug(f"发送 Telegram 处理消息: {message} 到 {chat_id}")
                else:
                    logger.warning("无法获取 Telegram chat_id，使用原始方式发送消息")
                    response = event.plain_result(message)
                    if hasattr(event, "send"):
                        await event.send(response)
                    return None, client

            # QQ 平台发送消息
            elif bot and group_id:
                # 群聊消息
                send_result = await bot.send_group_msg(
                    group_id=group_id, message=message
                )
                logger.debug(f"发送群聊处理消息: {message} 到群 {group_id}")
            elif bot and (user_id or is_private):
                # 私聊消息
                if not user_id and hasattr(event, "get_sender_id"):
                    user_id = event.get_sender_id()

                if user_id:
                    send_result = await bot.send_private_msg(
                        user_id=user_id, message=message
                    )
                    logger.debug(f"发送私聊处理消息: {message} 到用户 {user_id}")
                else:
                    # 无法获取user_id，使用原始方式发送
                    logger.warning(f"无法获取user_id，使用原始方式发送消息: {message}")
                    response = event.plain_result(message)
                    if hasattr(event, "send"):
                        await event.send(response)
                    return None, bot
            else:
                # 无法确定消息类型或没有bot/client实例，使用原始方式发送并记录详细信息
                logger.debug(
                    f"使用原始方式发送处理消息，event类型: {type(event)}, platform={platform_name}, has_bot={hasattr(event, 'bot')}, has_client={hasattr(event, 'client')}"
                )
                # 尝试使用event.plain_result发送，虽然无法获取message_id
                response = event.plain_result(message)
                # 使用event的send方法发送
                if hasattr(event, "send"):
                    await event.send(response)
                return None, bot or client

            # 检查send_result是否包含message_id（QQ 平台）
            if send_result is not None:
                if isinstance(send_result, dict):
                    message_id = send_result.get("message_id")
                elif hasattr(send_result, "message_id"):
                    message_id = send_result.message_id

            logger.debug(f"发送处理消息成功，message_id: {message_id}")

            # 如果获取到message_id且启用了自动撤回且有bot/client实例
            if message_id and enable_recall and (bot or client):
                # 定时撤回模式
                if recall_type == "time_based":
                    logger.info(
                        f"创建定时撤回任务，message_id: {message_id}，延迟: {recall_time_s}秒"
                    )

                    # 闭包捕获需要的变量
                    recall_bot = bot
                    recall_client = client
                    recall_platform = platform_name
                    recall_event = event
                    recall_message_id = message_id

                    async def _recall_task():
                        try:
                            await asyncio.sleep(recall_time_s)

                            if recall_platform == "telegram" and recall_client:
                                # Telegram 撤回
                                chat_id = None
                                if hasattr(recall_event, "get_group_id"):
                                    chat_id = recall_event.get_group_id()
                                if not chat_id and hasattr(
                                    recall_event, "get_sender_id"
                                ):
                                    chat_id = recall_event.get_sender_id()
                                if chat_id:
                                    # 处理 topic 群组的 chat_id
                                    if "#" in chat_id:
                                        chat_id = chat_id.split("#")[0]
                                    await recall_client.delete_message(
                                        chat_id=int(chat_id),
                                        message_id=int(recall_message_id),
                                    )
                            elif recall_bot:
                                # QQ 平台撤回
                                await recall_bot.delete_msg(
                                    message_id=recall_message_id
                                )
                            logger.info(f"已定时撤回消息: {recall_message_id}")
                        except Exception as e:
                            logger.error(f"定时撤回消息失败: {e}")

                    task = asyncio.create_task(_recall_task())

                    # 将任务添加到列表中管理
                    recall_tasks.append(task)

                    # 添加完成回调，从列表中移除已完成的任务
                    def _remove_task(t):
                        try:
                            recall_tasks.remove(t)
                        except ValueError:
                            pass

                    task.add_done_callback(_remove_task)
                # 智能撤回模式 - 只发送消息，不创建定时任务，等待分析完成后立即撤回
                elif recall_type == "smart" and smart_recall_enabled:
                    logger.info(
                        f"已发送智能撤回消息，message_id: {message_id}，等待分析完成后立即撤回"
                    )

        except Exception as e:
            logger.error(f"发送处理消息或设置撤回失败: {e}")

        return message_id, bot or client

    @staticmethod
    async def recall_processing_message(
        event: AstrMessageEvent,
        message_id: str,
        bot: Any,
        delay: int,
        recall_type: str,
        smart_recall_enabled: bool,
    ):
        """撤回处理提示消息（优化版本，带重试机制）

        根据配置的撤回类型执行不同的撤回策略：
        - smart: 智能撤回，分析完成后立即撤回（无延迟）
        - time_based: 定时撤回，等待指定时间后撤回

        改进点：
        - 添加重试机制，最多重试3次
        - 增加超时时间，提高成功率
        - 改进错误处理和日志记录

        Args:
            event: 消息事件对象
            message_id: 消息ID
            bot: bot实例
            delay: 延迟时间（秒）
            recall_type: 撤回类型
            smart_recall_enabled: 是否启用智能撤回
        """
        # 获取平台名称
        platform_name = (
            event.get_platform_name() if hasattr(event, "get_platform_name") else None
        )

        # bot 参数对于 Telegram 平台实际上是 client，这里统一处理
        # 对于 Telegram 平台，bot 参数是从 send_processing_message 返回的 client
        # 对于 QQ 平台，bot 参数是真正的 bot 实例
        if not message_id or not bot:
            logger.warning("无法撤回消息：message_id 或 bot/client 为空")
            return

        import asyncio

        # 根据撤回类型设置等待时间
        if recall_type == "smart" and smart_recall_enabled:
            # 智能撤回：立即撤回，不需要延迟
            wait_time = 0
            logger.info(
                f"智能撤回：分析完成，立即撤回处理中消息，message_id: {message_id}"
            )
        else:
            # 定时撤回：等待指定时间后撤回
            wait_time = delay
            if delay > 0:
                logger.info(
                    f"定时撤回：等待 {delay} 秒后撤回消息，message_id: {message_id}"
                )

        # 等待指定时间
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        # 执行撤回，带重试机制
        max_retries = 3
        retry_delay = 1  # 每次重试间隔1秒

        for attempt in range(max_retries):
            try:
                # 根据平台使用不同的撤回 API
                if platform_name == "telegram":
                    # Telegram Bot API: deleteMessage(chat_id, message_id)
                    # 获取 chat_id
                    chat_id = None
                    if hasattr(event, "get_group_id"):
                        chat_id = event.get_group_id()
                    if not chat_id and hasattr(event, "get_sender_id"):
                        chat_id = event.get_sender_id()

                    if chat_id:
                        # 处理 topic 群组的 chat_id
                        if "#" in chat_id:
                            chat_id = chat_id.split("#")[0]
                        await bot.delete_message(
                            chat_id=int(chat_id), message_id=int(message_id)
                        )
                    else:
                        logger.warning("无法获取 Telegram chat_id，跳过撤回消息")
                else:
                    # QQ 平台: delete_msg(message_id)
                    await bot.delete_msg(message_id=message_id)

                if recall_type == "smart" and smart_recall_enabled:
                    logger.info(f"智能撤回成功，已撤回消息: {message_id}")
                else:
                    logger.info(f"定时撤回成功，已撤回消息: {message_id}")

                # 撤回成功，退出循环
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    # 还有重试次数，记录警告并等待后重试
                    logger.warning(
                        f"撤回消息失败（第 {attempt + 1}/{max_retries} 次尝试）: {e}，"
                        f"将在 {retry_delay} 秒后重试"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    # 重试次数用完，记录错误
                    logger.error(
                        f"撤回处理提示消息失败（已重试 {max_retries} 次）: {e}，"
                        f"message_id: {message_id}"
                    )
