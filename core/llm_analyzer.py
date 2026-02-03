
"""
LLM 分析模块

负责调用大语言模型进行智能内容分析和总结。
"""

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class LLMAnalyzer:
    """LLM 分析器类"""

    def __init__(
        self,
        context: Any,
        llm_provider: str = "",
        custom_prompt: str = "",
        max_summary_length: int = 2000,
        enable_emoji: bool = True,
    ):
        """初始化 LLM 分析器

        Args:
            context: AstrBot 上下文对象
            llm_provider: LLM 提供商 ID
            custom_prompt: 自定义提示词
            max_summary_length: 最大摘要长度
            enable_emoji: 是否启用 emoji
        """
        self.context = context
        self.llm_provider = llm_provider
        self.custom_prompt = custom_prompt
        self.max_summary_length = max_summary_length
        self.enable_emoji = enable_emoji

    def check_llm_availability(self) -> bool:
        """检查 LLM 是否可用和启用

        Returns:
            LLM 是否可用
        """
        return hasattr(self.context, "llm_generate") and self.llm_enabled

    async def get_llm_provider(self, event: AstrMessageEvent) -> str:
        """获取合适的 LLM 提供商

        Args:
            event: 消息事件对象

        Returns:
            LLM 提供商 ID
        """
        # 优先使用配置的 LLM 提供商
        if self.llm_provider:
            return self.llm_provider

        # 如果没有配置，则使用当前会话的模型
        try:
            umo = event.unified_msg_origin
            return await self.context.get_current_chat_provider_id(umo=umo)
        except Exception as e:
            logger.error(f"获取当前会话的聊天模型 ID 失败: {e}")
            return ""

    def build_llm_prompt(self, content_data: dict, content_type: str) -> str:
        """构建优化的 LLM 提示词

        Args:
            content_data: 内容数据字典
            content_type: 内容类型

        Returns:
            LLM 提示词
        """
        title = content_data["title"]
        content = content_data["content"]
        url = content_data["url"]

        emoji_prefix = "每个要点用 emoji 图标标记" if self.enable_emoji else ""

        if self.custom_prompt:
            # 使用自定义提示词，替换变量
            return self.custom_prompt.format(
                title=title,
                url=url,
                content=content,
                max_length=self.max_summary_length,
                content_type=content_type,
            )
        else:
            # 根据内容类型获取相应的分析模板
            template = self._get_analysis_template(
                content_type, emoji_prefix, self.max_summary_length
            )
            # 替换模板中的变量
            return template.format(title=title, url=url, content=content)

    def _get_analysis_template(
        self, content_type: str, emoji_prefix: str, max_length: int
    ) -> str:
        """根据内容类型获取相应的分析模板

        Args:
            content_type: 内容类型
            emoji_prefix: emoji 前缀
            max_length: 最大长度

        Returns:
            分析模板
        """
        # 定义多种分析模板
        templates = {
            "新闻资讯": f"""请对以下新闻资讯进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**新闻内容**：
{{content}}

**分析要求**：
1. **核心事件**：用50-100字概括新闻的核心事件和背景
2. **关键信息**：提取3-5个最重要的事实要点
3. **事件影响**：分析事件可能产生的影响和意义
4. **相关背景**：补充必要的相关背景信息
5. **适用人群**：说明这条新闻对哪些人群最有价值

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",
            "教程指南": f"""请对以下教程指南进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**教程内容**：
{{content}}

**分析要求**：
1. **核心目标**：用50-100字概括教程的核心目标和适用场景
2. **学习价值**：分析该教程对学习者的价值和意义
3. **关键步骤**：提取教程的主要步骤和关键点
4. **技术要点**：总结教程中涉及的核心技术或知识点
5. **注意事项**：整理教程中的重要提示和注意事项
6. **适用人群**：说明适合学习该教程的人群

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",
            "默认": f"""请对以下网页内容进行专业分析和智能总结：

**网页信息**
- 标题：{{title}}
- 链接：{{url}}

**网页内容**：
{{content}}

**分析要求**：
1. **核心摘要**：用50-100字概括网页的核心内容和主旨
2. **关键要点**：提取2-3个最重要的信息点或观点
3. **内容类型**：判断网页属于什么类型（新闻、教程、博客、产品介绍等）
4. **价值评估**：简要评价内容的价值和实用性
5. **适用人群**：说明适合哪些人群阅读

**输出格式要求**：
- 使用清晰的分段结构
- {emoji_prefix}
- 语言简洁专业，避免冗余
- 保持客观中立的态度
- 总字数不超过{max_length}字

请确保分析准确、全面且易于理解。""",
        }

        # 返回对应的模板，如果没有则使用默认模板
        return templates.get(content_type, templates["默认"])

    def format_llm_result(
        self, content_data: dict, analysis_text: str, content_type: str
    ) -> str:
        """格式化 LLM 返回的结果

        Args:
            content_data: 内容数据字典
            analysis_text: LLM 分析文本
            content_type: 内容类型

        Returns:
            格式化后的结果
        """
        title = content_data["title"]
        url = content_data["url"]

        # 限制摘要长度，避免结果过长
        if len(analysis_text) > self.max_summary_length:
            analysis_text = analysis_text[: self.max_summary_length] + "..."

        # 添加标题和格式美化
        link_emoji = "🔗" if self.enable_emoji else ""
        title_emoji = "📝" if self.enable_emoji else ""
        type_emoji = "📋" if self.enable_emoji else ""

        formatted_result = "**AI智能网页分析报告**\n\n"
        formatted_result += f"{link_emoji} **分析链接**: {url}\n"
        formatted_result += f"{title_emoji} **网页标题**: {title}\n"
        formatted_result += f"{type_emoji} **内容类型**: {content_type}\n\n"
        formatted_result += "---\n\n"
        formatted_result += analysis_text
        formatted_result += "\n\n---\n"
        formatted_result += "*分析完成，希望对您有帮助！*"

        return formatted_result

    async def analyze_with_llm(
        self, event: AstrMessageEvent, content_data: dict, llm_enabled: bool = True
    ) -> str:
        """调用大语言模型(LLM)进行智能内容分析和总结

        Args:
            event: 消息事件对象
            content_data: 内容数据字典
            llm_enabled: LLM 是否启用

        Returns:
            分析结果字符串
        """
        try:
            content = content_data["content"]
            url = content_data["url"]

            # 检查 LLM 是否可用和启用
            if not llm_enabled or not hasattr(self.context, "llm_generate"):
                logger.info("LLM 未启用或不可用")
                return None

            # 获取 LLM 提供商
            provider_id = await self.get_llm_provider(event)
            if not provider_id:
                logger.error("无法获取 LLM 提供商，无法进行分析")
                return None

            # 智能检测内容类型
            content_type = self._detect_content_type(content)

            # 构建 LLM 提示词
            prompt = self.build_llm_prompt(content_data, content_type)

            # 调用 LLM 生成结果
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )

            if llm_resp and llm_resp.completion_text:
                # 格式化 LLM 结果
                return self.format_llm_result(
                    content_data, llm_resp.completion_text.strip(), content_type
                )
            else:
                logger.error("LLM 返回结果为空")
                return None

        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            return None

    def _detect_content_type(self, content: str) -> str:
        """智能检测内容类型

        Args:
            content: 网页内容

        Returns:
            内容类型字符串
        """
        content_lower = content.lower()
        rules = self._get_content_type_rules()

        for type_name, keywords in rules.items():
            if any(keyword in content_lower for keyword in keywords):
                return type_name
        return "文章"

    def _get_content_type_rules(self) -> dict[str, list[str]]:
        """获取内容类型检测规则"""
        return {
            "新闻资讯": [
                "新闻",
                "报道",
                "消息",
                "时事",
                "快讯",
                "头条",
                "要闻",
                "热点",
                "事件",
            ],
            "教程指南": [
                "教程",
                "指南",
                "教学",
                "步骤",
                "方法",
                "如何",
                "怎样",
                "攻略",
                "技巧",
            ],
            "个人博客": [
                "博客",
                "随笔",
                "日记",
                "个人",
                "观点",
                "感想",
                "感悟",
                "思考",
                "分享",
            ],
            "产品介绍": [
                "产品",
                "服务",
                "购买",
                "价格",
                "优惠",
                "功能",
                "特性",
                "参数",
                "规格",
                "评测",
            ],
            "技术文档": ["技术", "开发", "编程", "代码", "API", "SDK", "文档", "说明"],
            "学术论文": [
                "论文",
                "研究",
                "实验",
                "结论",
                "摘要",
                "关键词",
                "引用",
                "参考文献",
            ],
            "商业分析": [
                "分析",
                "报告",
                "数据",
                "统计",
                "趋势",
                "预测",
                "市场",
                "行业",
            ],
        }