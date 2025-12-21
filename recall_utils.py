import asyncio
from astrbot.api import logger


async def auto_recall_message(bot, message_id: int, recall_time: int) -> None:
    """
    自动撤回消息
    
    参数:
        bot: 机器人实例，用于发送撤回请求
        message_id: 要撤回的消息ID
        recall_time: 延迟撤回的时间（秒）
    """
    try:
        # 等待指定时间
        if recall_time > 0:
            await asyncio.sleep(recall_time)
        
        # 调用bot的delete_msg方法撤回消息
        await bot.delete_msg(message_id=message_id)
        logger.info(f"已撤回消息: {message_id}")
    except Exception as e:
        logger.error(f"撤回消息失败: {e}")


class RecallManager:
    """
    撤回任务管理器，用于管理和清理撤回任务
    """
    def __init__(self):
        # 撤回任务列表
        self.recall_tasks = []
    
    async def create_recall_task(self, bot, message_id: int, recall_time: int) -> asyncio.Task:
        """
        创建撤回任务
        
        参数:
            bot: 机器人实例，用于发送撤回请求
            message_id: 要撤回的消息ID
            recall_time: 延迟撤回的时间（秒）
        
        返回:
            asyncio.Task: 创建的撤回任务
        """
        # 创建撤回任务
        task = asyncio.create_task(auto_recall_message(bot, message_id, recall_time))
        
        # 将任务添加到列表中管理
        self.recall_tasks.append(task)
        
        # 添加完成回调，从列表中移除已完成的任务
        def _remove_task(t):
            try:
                self.recall_tasks.remove(t)
            except ValueError:
                pass
        
        task.add_done_callback(_remove_task)
        
        logger.debug(f"创建撤回任务，message_id: {message_id}，延迟: {recall_time}秒")
        return task
    
    def cancel_all_tasks(self) -> None:
        """
        取消所有撤回任务
        """
        for task in self.recall_tasks:
            task.cancel()
        self.recall_tasks.clear()
        logger.info("已取消所有撤回任务")
    
    def get_task_count(self) -> int:
        """
        获取当前撤回任务数量
        
        返回:
            int: 当前撤回任务数量
        """
        return len(self.recall_tasks)
