"""
消息辅助模块

发送"正在截图"提示消息并按配置自动撤回（QQ / Telegram）。
"""

import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class MessageHelpers:
    """提示消息发送与撤回辅助方法"""

    @staticmethod
    async def send_processing_message(
        event: AstrMessageEvent,
        message: str,
        enable_processing_message: bool,
        enable_recall: bool,
        recall_type: str,
        recall_time_s: int,
        smart_recall_enabled: bool,
        recall_tasks: list,
    ) -> tuple:
        """发送处理提示消息并设置自动撤回。

        Args:
            event: 消息事件。
            message: 提示文本。
            enable_processing_message: 是否发送提示。
            enable_recall: 是否自动撤回。
            recall_type: 撤回时机（time_based/smart）。
            recall_time_s: 定时撤回延迟秒数。
            smart_recall_enabled: 完成后立即撤回。
            recall_tasks: 撤回任务列表（由插件持有）。

        Returns:
            (message_id, bot 或 client)；未发送时为 (None, None)。
        """
        if not enable_processing_message:
            return None, None

        platform_name = (
            event.get_platform_name() if hasattr(event, "get_platform_name") else None
        )
        bot = event.bot if hasattr(event, "bot") else None
        client = event.client if hasattr(event, "client") else None
        message_id = None

        try:
            group_id = event.get_group_id() if hasattr(event, "get_group_id") else None
            user_id = event.get_sender_id() if hasattr(event, "get_sender_id") else None

            send_result = None

            if platform_name == "telegram" and client:
                chat_id = group_id or user_id
                if chat_id:
                    if "#" in str(chat_id):
                        chat_id = str(chat_id).split("#")[0]
                    msg = await client.send_message(chat_id=int(chat_id), text=message)
                    message_id = msg.message_id
                else:
                    if hasattr(event, "send"):
                        await event.send(event.plain_result(message))
                    return None, client
            elif bot and (group_id or user_id):
                if group_id and hasattr(bot, "send_group_msg"):
                    send_result = await bot.send_group_msg(
                        group_id=group_id, message=message
                    )
                elif user_id and hasattr(bot, "send_private_msg"):
                    send_result = await bot.send_private_msg(
                        user_id=user_id, message=message
                    )
                else:
                    if hasattr(event, "send"):
                        await event.send(event.plain_result(message))
                    return None, bot
            else:
                if hasattr(event, "send"):
                    await event.send(event.plain_result(message))
                return None, bot or client

            if send_result is not None:
                if isinstance(send_result, dict):
                    message_id = send_result.get("message_id")
                elif hasattr(send_result, "message_id"):
                    message_id = send_result.message_id

            logger.debug(f"已发送处理提示消息，message_id: {message_id}")

            if message_id and enable_recall and (bot or client):
                if recall_type == "time_based":
                    MessageHelpers._schedule_timed_recall(
                        event,
                        message_id,
                        bot,
                        client,
                        platform_name,
                        recall_time_s,
                        recall_tasks,
                    )
                elif recall_type == "smart" and smart_recall_enabled:
                    logger.debug("智能撤回模式：等待结果发送完成后立即撤回提示消息")

        except Exception as e:
            logger.error(f"发送处理提示消息失败: {e}")

        return message_id, bot or client

    @staticmethod
    def _schedule_timed_recall(
        event, message_id, bot, client, platform_name, delay_s, recall_tasks
    ):
        """创建定时撤回任务并登记到插件的任务列表。"""

        async def _recall_task():
            try:
                await asyncio.sleep(delay_s)
                await MessageHelpers.recall_message(
                    event, message_id, bot or client, platform_name
                )
            except Exception as e:
                logger.error(f"定时撤回消息失败: {e}")

        task = asyncio.create_task(_recall_task())
        recall_tasks.append(task)

        def _remove_task(done):
            try:
                recall_tasks.remove(done)
            except ValueError:
                pass

        task.add_done_callback(_remove_task)

    @staticmethod
    async def recall_message(event, message_id, bot, platform_name):
        """撤回一条提示消息，失败时最多重试 3 次。"""
        for attempt in range(3):
            try:
                if platform_name == "telegram" and bot:
                    chat_id = (
                        event.get_group_id() if hasattr(event, "get_group_id") else None
                    )
                    if not chat_id and hasattr(event, "get_sender_id"):
                        chat_id = event.get_sender_id()
                    if chat_id:
                        if "#" in str(chat_id):
                            chat_id = str(chat_id).split("#")[0]
                        await bot.delete_message(
                            chat_id=int(chat_id), message_id=int(message_id)
                        )
                elif bot:
                    await bot.delete_msg(message_id=message_id)
                logger.debug(f"已撤回提示消息: {message_id}")
                return
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    logger.error(f"撤回提示消息失败（已重试）: {e}")

    @staticmethod
    async def recall_processing_message(
        event: AstrMessageEvent,
        message_id,
        bot,
        recall_type: str,
        smart_recall_enabled: bool,
        recall_time_s: int,
    ):
        """按配置撤回提示消息：smart 立即撤回，time_based 到延迟后撤回。"""
        if not message_id or not bot:
            return
        platform_name = (
            event.get_platform_name() if hasattr(event, "get_platform_name") else ""
        )
        if recall_type == "smart" and smart_recall_enabled:
            wait = 0
        else:
            wait = recall_time_s
        if wait > 0:
            await asyncio.sleep(wait)
        await MessageHelpers.recall_message(event, message_id, bot, platform_name)
