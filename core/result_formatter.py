
"""
结果格式化模块

负责格式化分析结果、应用模板、折叠长内容等。
"""

from datetime import datetime


class ResultFormatter:
    """结果格式化器类"""

    def __init__(self, enable_emoji: bool = True, enable_statistics: bool = True):
        """初始化结果格式化器

        Args:
            enable_emoji: 是否启用emoji
            enable_statistics: 是否显示统计信息
        """
        self.enable_emoji = enable_emoji
        self.enable_statistics = enable_statistics

    def apply_result_settings(
        self, result: str, url: str, content_data: dict = None, **kwargs
    ) -> str:
        """应用所有结果设置（模板渲染和折叠）

        Args:
            result: 分析结果
            url: 网页URL
            content_data: 内容数据（可选）
            **kwargs: 其他配置参数

        Returns:
            格式化后的结果
        """
        enable_custom_template = kwargs.get("enable_custom_template", False)
        result_template = kwargs.get("result_template", "default")
        enable_collapsible = kwargs.get("enable_collapsible", False)
        collapse_threshold = kwargs.get("collapse_threshold", 1500)
        template_content = kwargs.get("template_content", "")

        # 首先应用模板渲染
        if enable_custom_template and content_data:
            rendered_result = self._render_custom_template(
                content_data, result, url, template_content
            )
        else:
            rendered_result = self._render_result_template(result, url, result_template)

        # 然后应用结果折叠
        final_result = self._collapse_result(
            rendered_result, enable_collapsible, collapse_threshold
        )

        return final_result

    def _render_result_template(self, result: str, url: str, template_type: str) -> str:
        """根据模板类型渲染分析结果

        Args:
            result: 分析结果
            url: 网页URL
            template_type: 模板类型

        Returns:
            渲染后的结果
        """
        if template_type == "detailed":
            return (
                f"【详细分析结果】\n\n📌 分析URL：{url}\n\n{result}\n\n--- 分析结束 ---"
            )
        elif template_type == "compact":
            lines = result.splitlines()
            compact_result = []
            for line in lines:
                if line.strip() and not line.startswith("⚠️"):
                    compact_result.append(line)
                    if len(compact_result) >= 10:
                        break
            return (
                f"【紧凑分析结果】\n{url}\n\n"
                + "\n".join(compact_result)
                + "\n\n... 更多内容请查看完整分析"
            )
        elif template_type == "markdown":
            return f"# 网页分析结果\n\n## URL\n{url}\n\n## 分析内容\n{result}\n\n---\n*分析完成于 {self._get_current_time()}*"
        elif template_type == "simple":
            return f"{url}\n\n{result}"
        else:
            return f"【网页分析结果】\n{url}\n\n{result}"

    def _render_custom_template(
        self, content_data: dict, analysis_result: str, url: str, template_content: str
    ) -> str:
        """使用自定义模板渲染分析结果

        Args:
            content_data: 包含标题、内容等信息的字典
            analysis_result: 当前的分析结果
            url: 网页URL
            template_content: 模板内容

        Returns:
            渲染后的结果
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        content = content_data.get("content", "")
        content_stats = self._calculate_content_statistics(content)

        stats_str = """
- 字符数: {char_count:,}
- 词数: {word_count:,}
- 段落数: {paragraph_count}
"""
        paragraph_count = len([p.strip() for p in content.split("\n") if p.strip()])
        stats = stats_str.format(
            char_count=content_stats["char_count"],
            word_count=content_stats["word_count"],
            paragraph_count=paragraph_count,
        )

        summary = content[:150] + "..." if len(content) > 150 else content
        content_type = self._detect_content_type(content)

        template_vars = {
            "title": content_data.get("title", "无标题"),
            "url": url,
            "content": content,
            "summary": summary,
            "analysis_result": analysis_result,
            "screenshot": "[截图]",
            "content_type": content_type,
            "stats": stats,
            "date": date_str,
            "time": time_str,
        }

        rendered_template = template_content
        for var_name, var_value in template_vars.items():
            rendered_template = rendered_template.replace(f"{{{var_name}}}", str(var_value))

        return rendered_template

    def _collapse_result(
        self, result: str, enable_collapsible: bool, collapse_threshold: int
    ) -> str:
        """根据配置折叠长结果

        Args:
            result: 分析结果
            enable_collapsible: 是否启用折叠
            collapse_threshold: 折叠阈值

        Returns:
            折叠后的结果
        """
        if enable_collapsible and len(result) > collapse_threshold:
            collapse_pos = collapse_threshold
            while collapse_pos < len(result) and result[collapse_pos] != "\n":
                collapse_pos += 1
            if collapse_pos == len(result):
                collapse_pos = collapse_threshold

            collapsed_content = result[:collapse_pos]
            remaining_content = result[collapse_pos:]
            return f"{collapsed_content}\n\n[展开全文]\n\n{remaining_content}"
        return result

    def _get_current_time(self) -> str:
        """获取当前时间的格式化字符串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _calculate_content_statistics(self, content: str) -> dict:
        """计算内容统计信息"""
        char_count = len(content)
        word_count = len(content.split())
        return {"char_count": char_count, "word_count": word_count}

    def _detect_content_type(self, content: str) -> str:
        """智能检测内容类型"""
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
            "娱乐资讯": [
                "娱乐",
                "明星",
                "电影",
                "音乐",
                "综艺",
                "演唱会",
                "首映",
                "新歌",
            ],
            "体育新闻": [
                "体育",
                "比赛",
                "赛事",
                "比分",
                "运动员",
                "冠军",
                "亚军",
                "季军",
            ],
            "教育资讯": [
                "教育",
                "学校",
                "招生",
                "考试",
                "培训",
                "学习",
                "课程",
                "教材",
            ],
        }

    def build_enhanced_analysis(self, content_data: dict) -> str:
        """构建增强版基础分析结果

        Args:
            content_data: 内容数据字典

        Returns:
            格式化的分析结果
        """
        title = content_data["title"]
        content = content_data["content"]
        url = content_data["url"]

        content_stats = self._calculate_content_statistics(content)
        content_type = self._detect_content_type(content)

        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        key_sentences = paragraphs[:3]

        quality_indicator = self._evaluate_content_quality(content_stats["char_count"])

        result_parts = []
        result_parts.append(self._build_analysis_header())
        result_parts.append(
            self._build_basic_info(title, url, content_type, quality_indicator)
        )
        result_parts.append(self._build_statistics_info(content_stats, paragraphs))
        result_parts.append(self._build_content_summary(key_sentences))
        result_parts.append(self._build_analysis_note())

        return "".join(result_parts)

    def _build_analysis_header(self) -> str:
        """构建分析结果的标题部分"""
        robot_emoji = "🤖" if self.enable_emoji else ""
        page_emoji = "📄" if self.enable_emoji else ""
        return f"{robot_emoji} **智能网页分析** {page_emoji}\n\n"

    def _build_basic_info(
        self, title: str, url: str, content_type: str, quality_indicator: str
    ) -> str:
        """构建分析结果的基本信息部分"""
        info_emoji = "📝" if self.enable_emoji else ""

        basic_info = []
        if self.enable_emoji:
            basic_info.append(f"**{info_emoji} 基本信息**\n")
        else:
            basic_info.append("**基本信息**\n")

        basic_info.append(f"- **标题**: {title}\n")
        basic_info.append(f"- **链接**: {url}\n")
        basic_info.append(f"- **内容类型**: {content_type}\n")
        basic_info.append(f"- **质量评估**: {quality_indicator}\n\n")

        return "".join(basic_info)

    def _build_statistics_info(self, content_stats: dict, paragraphs: list) -> str:
        """构建分析结果的统计信息部分"""
        if not self.enable_statistics:
            return ""

        stats_emoji = "📊" if self.enable_emoji else ""

        stats_info = []
        if self.enable_emoji:
            stats_info.append(f"**{stats_emoji} 内容统计**\n")
        else:
            stats_info.append("**内容统计**\n")

        stats_info.append(f"- 字符数: {content_stats['char_count']:,}\n")
        stats_info.append(f"- 段落数: {len(paragraphs)}\n")
        stats_info.append(f"- 词数: {content_stats['word_count']:,}\n\n")

        return "".join(stats_info)

    def _build_content_summary(self, key_sentences: list) -> str:
        """构建分析结果的内容摘要部分"""
        search_emoji = "🔍" if self.enable_emoji else ""

        summary_info = []
        if self.enable_emoji:
            summary_info.append(f"**{search_emoji} 内容摘要**\n")
        else:
            summary_info.append("**内容摘要**\n")

        formatted_sentences = []
        for sentence in key_sentences:
            truncated = sentence[:100] + ("..." if len(sentence) > 100 else "")
            formatted_sentences.append(f"• {truncated}")

        summary_info.append(f"{chr(10).join(formatted_sentences)}\n\n")
        return "".join(summary_info)

    def _build_analysis_note(self) -> str:
        """构建分析结果的分析说明部分"""
        light_emoji = "💡" if self.enable_emoji else ""

        note_info = []
        if self.enable_emoji:
            note_info.append(f"**{light_emoji} 分析说明**\n")
        else:
            note_info.append("**分析说明**\n")

        note_info.append(
            "此分析基于网页内容提取，如需更深入的AI智能分析，请确保AstrBot已正确配置LLM功能。\n\n"
        )
        note_info.append("*提示：完整内容预览请查看原始网页*")

        return "".join(note_info)

    def _evaluate_content_quality(self, char_count: int) -> str:
        """评估内容质量"""
        if char_count > 5000:
            return "内容详实"
        elif char_count > 1000:
            return "内容丰富"
        else:
            return "内容简洁"
