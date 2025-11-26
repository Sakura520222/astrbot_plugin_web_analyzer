# -*- coding: utf-8 -*-
"""
AstrBot 网页分析插件
自动识别用户发送的网页链接，抓取内容并调用LLM进行分析和总结
"""

import re
import asyncio
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image


class WebAnalyzer:
    """网页分析器类"""
    
    def __init__(self, max_content_length: int = 10000, timeout: int = 30, user_agent: str = None):
        self.max_content_length = max_content_length
        self.timeout = timeout
        self.user_agent = user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        self.client = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.client:
            await self.client.aclose()
    
    def extract_urls(self, text: str) -> List[str]:
        """从文本中提取URL链接"""
        # 匹配常见的URL格式
        url_pattern = r'https?://[^\s\u4e00-\u9fff]+'
        urls = re.findall(url_pattern, text)
        return urls
    
    def is_valid_url(self, url: str) -> bool:
        """验证URL是否有效"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    async def fetch_webpage(self, url: str) -> Optional[str]:
        """抓取网页内容"""
        try:
            headers = {
                'User-Agent': self.user_agent
            }
            
            response = await self.client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            
            return response.text
        except Exception as e:
            logger.error(f"抓取网页失败: {url}, 错误: {e}")
            return None
    
    def extract_content(self, html: str, url: str) -> dict:
        """从HTML中提取主要内容"""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # 提取标题
            title = soup.find('title')
            title_text = title.get_text().strip() if title else "无标题"
            
            # 尝试提取文章内容（优先选择article、main等语义化标签）
            content_selectors = [
                'article',
                'main',
                '.article-content',
                '.post-content',
                '.content',
                'body'
            ]
            
            content_text = ""
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    # 移除脚本和样式标签
                    for script in element(['script', 'style']):
                        script.decompose()
                    
                    text = element.get_text(separator='\n', strip=True)
                    if len(text) > len(content_text):
                        content_text = text
            
            # 如果没找到合适的内容，使用body
            if not content_text:
                body = soup.find('body')
                if body:
                    for script in body(['script', 'style']):
                        script.decompose()
                    content_text = body.get_text(separator='\n', strip=True)
            
            # 限制内容长度
            if len(content_text) > self.max_content_length:
                content_text = content_text[:self.max_content_length] + "..."
            
            return {
                'title': title_text,
                'content': content_text,
                'url': url
            }
        except Exception as e:
            logger.error(f"解析网页内容失败: {e}")
            return None


from astrbot.api import AstrBotConfig

@register("web_analyzer", "开发者", "网页链接分析和总结插件", "1.0.0", "https://github.com/your-repo/astrbot_plugin_web_analyzer")
class WebAnalyzerPlugin(Star):
    """网页分析插件主类"""
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 从配置获取参数
        self.max_content_length = config.get('max_content_length', 10000)
        self.timeout = config.get('request_timeout', 30)
        self.llm_enabled = config.get('llm_enabled', True)
        self.auto_analyze = config.get('auto_analyze', True)
        self.user_agent = config.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        self.allowed_domains = self._parse_domain_list(config.get('allowed_domains', ''))
        self.blocked_domains = self._parse_domain_list(config.get('blocked_domains', ''))
        
        # 分析设置
        analysis_settings = config.get('analysis_settings', {})
        self.enable_emoji = analysis_settings.get('enable_emoji', True)
        self.enable_statistics = analysis_settings.get('enable_statistics', True)
        self.max_summary_length = analysis_settings.get('max_summary_length', 2000)
        
        # LLM提供商配置
        self.llm_provider = config.get('llm_provider', '')
        
        # 群聊黑名单配置
        group_blacklist_text = config.get('group_blacklist', '')
        self.group_blacklist = self._parse_group_list(group_blacklist_text)
        
        # 合并转发配置
        self.merge_forward_enabled = config.get('merge_forward_enabled', False)  # 是否启用合并转发
        
        # 自定义提示词配置
        self.custom_prompt = config.get('custom_prompt', '')  # 自定义分析提示词
        
        self.analyzer = WebAnalyzer(self.max_content_length, self.timeout)
    
    def _parse_domain_list(self, domain_text: str) -> List[str]:
        """解析域名列表文本为列表"""
        if not domain_text:
            return []
        domains = [domain.strip() for domain in domain_text.split('\n') if domain.strip()]
        return domains
    
    def _parse_group_list(self, group_text: str) -> List[str]:
        """解析群聊列表文本为列表"""
        if not group_text:
            return []
        groups = [group.strip() for group in group_text.split('\n') if group.strip()]
        return groups
    
    def _is_group_blacklisted(self, group_id: str) -> bool:
        """检查群聊是否在黑名单中"""
        if not group_id or not self.group_blacklist:
            return False
        return group_id in self.group_blacklist
    
    def _is_domain_allowed(self, url: str) -> bool:
        """检查域名是否允许访问"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # 检查是否在禁止列表中
            if self.blocked_domains:
                for blocked_domain in self.blocked_domains:
                    if blocked_domain.lower() in domain:
                        return False
            
            # 检查是否在允许列表中（如果允许列表不为空）
            if self.allowed_domains:
                for allowed_domain in self.allowed_domains:
                    if allowed_domain.lower() in domain:
                        return True
                return False  # 如果允许列表不为空但域名不在其中，则禁止
            
            return True  # 如果允许列表为空，则允许所有域名
        except Exception:
            return False
    
    @filter.command("网页分析", alias={'分析', '总结'})
    async def analyze_webpage(self, event: AstrMessageEvent, url: str = None):
        """手动分析指定网页链接"""
        if not url:
            yield event.plain_result("请提供要分析的网页链接，例如：/网页分析 https://example.com")
            return
        
        if not self.analyzer.is_valid_url(url):
            yield event.plain_result("无效的URL链接，请检查格式是否正确")
            return
        
        # 检查域名是否允许访问
        if not self._is_domain_allowed(url):
            yield event.plain_result("该域名不在允许访问的列表中，或已被禁止访问")
            return
        
        yield event.plain_result(f"正在分析网页: {url}")
        
        async with WebAnalyzer(self.max_content_length, self.timeout, self.user_agent) as analyzer:
            # 抓取网页内容
            html = await analyzer.fetch_webpage(url)
            if not html:
                yield event.plain_result("无法抓取网页内容，请检查链接是否可访问")
                return
            
            # 提取内容
            content_data = analyzer.extract_content(html, url)
            if not content_data:
                yield event.plain_result("无法解析网页内容")
                return
            
            # 调用LLM进行分析
            analysis_result = await self.analyze_with_llm(event, content_data)
            
            # 发送分析结果，使用async for迭代异步生成器
            async for result in self._send_analysis_result(event, analysis_result, url):
                yield result
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_detect_urls(self, event: AstrMessageEvent):
        """自动检测消息中的URL链接并进行分析"""
        # 检查是否启用自动分析
        if not self.auto_analyze:
            logger.info("自动分析功能已禁用")
            return
        
        # 检查群聊是否在黑名单中（仅群聊消息）
        # 尝试从不同位置获取群聊ID
        group_id = None
        
        # 方法1：从事件对象直接获取
        if hasattr(event, 'group_id') and event.group_id:
            group_id = event.group_id
        # 方法2：从消息对象获取
        elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'group_id') and event.message_obj.group_id:
            group_id = event.message_obj.group_id
        # 方法3：从原始消息获取
        elif hasattr(event, 'raw_message') and hasattr(event.raw_message, 'group_id') and event.raw_message.group_id:
            group_id = event.raw_message.group_id
        
        # 群聊在黑名单中时静默忽略
        if group_id and self._is_group_blacklisted(group_id):
            return  # 群聊在黑名单中，静默忽略
            
        message_text = event.message_str
        
        # 提取URL
        urls = self.analyzer.extract_urls(message_text)
        if not urls:
            return  # 没有URL，不处理
        
        valid_urls = [url for url in urls if self.analyzer.is_valid_url(url)]
        if not valid_urls:
            return
        
        # 只处理第一个URL，避免过多请求
        url = valid_urls[0]
        
        # 检查域名是否允许访问
        if not self._is_domain_allowed(url):
            return  # 域名不允许访问，静默忽略
        
        # 发送处理提示
        yield event.plain_result(f"检测到网页链接，正在分析: {url}")
        
        async with WebAnalyzer(self.max_content_length, self.timeout, self.user_agent) as analyzer:
            # 抓取网页内容
            html = await analyzer.fetch_webpage(url)
            if not html:
                yield event.plain_result("无法抓取网页内容")
                return
            
            # 提取内容
            content_data = analyzer.extract_content(html, url)
            if not content_data:
                yield event.plain_result("无法解析网页内容")
                return
            
            # 调用LLM进行分析
            analysis_result = await self.analyze_with_llm(event, content_data)
            
            # 发送分析结果，根据配置决定是否使用合并转发
            async for result in self._send_analysis_result(event, analysis_result, url):
                yield result
    
    async def analyze_with_llm(self, event: AstrMessageEvent, content_data: dict) -> str:
        """调用LLM进行内容分析和总结"""
        try:
            title = content_data['title']
            content = content_data['content']
            url = content_data['url']
            
            # 检查LLM是否可用和启用
            if not hasattr(self.context, 'llm_generate') or not self.llm_enabled:
                return self.get_enhanced_analysis(content_data)
            
            # 优先使用配置的LLM提供商，如果没有配置则使用当前会话的模型
            provider_id = self.llm_provider
            if not provider_id:
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)
            
            if not provider_id:
                return self.get_enhanced_analysis(content_data)
            
            # 构建优化的LLM提示词
            emoji_prefix = "每个要点用emoji图标标记" if self.enable_emoji else ""
            
            # 使用自定义提示词或默认提示词
            if self.custom_prompt:
                # 替换自定义提示词中的变量
                prompt = self.custom_prompt.format(
                    title=title,
                    url=url,
                    content=content,
                    max_length=self.max_summary_length
                )
            else:
                # 默认提示词
                prompt = f"""请对以下网页内容进行专业分析和智能总结：

**网页信息**
- 标题：{title}
- 链接：{url}

**网页内容**：
{content}

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
- 总字数不超过{self.max_summary_length}字

请确保分析准确、全面且易于理解。"""
            
            # 使用当前会话的聊天模型ID调用大模型
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,  # 使用当前会话的聊天模型
                prompt=prompt
            )
            
            if llm_resp and llm_resp.completion_text:
                # 美化LLM返回的结果
                analysis_text = llm_resp.completion_text.strip()
                
                # 限制摘要长度
                if len(analysis_text) > self.max_summary_length:
                    analysis_text = analysis_text[:self.max_summary_length] + "..."
                
                # 添加标题和格式美化
                link_emoji = "🔗" if self.enable_emoji else ""
                title_emoji = "📝" if self.enable_emoji else ""
                
                formatted_result = f"**AI智能网页分析报告**\n\n"
                formatted_result += f"{link_emoji} **分析链接**: {url}\n"
                formatted_result += f"{title_emoji} **网页标题**: {title}\n\n"
                formatted_result += "---\n\n"
                formatted_result += analysis_text
                formatted_result += "\n\n---\n"
                formatted_result += "*分析完成，希望对您有帮助！*"
                
                return formatted_result
            else:
                return self.get_enhanced_analysis(content_data)
                
        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            # 如果LLM分析失败，直接返回错误信息
            return f"❌ LLM分析过程中出现错误: {str(e)}"
    
    def get_enhanced_analysis(self, content_data: dict) -> str:
        """增强版基础分析（LLM不可用时使用）"""
        title = content_data['title']
        content = content_data['content']
        url = content_data['url']
        
        # 详细的内容统计
        char_count = len(content)
        line_count = len(content.split('\n'))
        word_count = len(content.split())
        
        # 智能内容类型检测
        content_lower = content.lower()
        content_type = "文章"
        if any(keyword in content_lower for keyword in ['新闻', '报道', '消息', '时事']):
            content_type = "新闻资讯"
        elif any(keyword in content_lower for keyword in ['教程', '指南', '教学', '步骤', '方法']):
            content_type = "教程指南"
        elif any(keyword in content_lower for keyword in ['博客', '随笔', '日记', '个人', '观点']):
            content_type = "个人博客"
        elif any(keyword in content_lower for keyword in ['产品', '服务', '购买', '价格', '优惠']):
            content_type = "产品介绍"
        elif any(keyword in content_lower for keyword in ['技术', '开发', '编程', '代码', 'API']):
            content_type = "技术文档"
        
        # 提取关键句子（前3个非空段落）
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        key_sentences = paragraphs[:3]
        
        # 检测内容质量
        quality_indicator = "内容丰富" if char_count > 1000 else "内容简洁"
        if char_count > 5000:
            quality_indicator = "内容详实"
        
        # 根据配置决定是否使用emoji
        robot_emoji = "🤖" if self.enable_emoji else ""
        page_emoji = "📄" if self.enable_emoji else ""
        info_emoji = "📝" if self.enable_emoji else ""
        stats_emoji = "📊" if self.enable_emoji else ""
        search_emoji = "🔍" if self.enable_emoji else ""
        light_emoji = "💡" if self.enable_emoji else ""
        
        result = f"{robot_emoji} **智能网页分析** {page_emoji}\n\n"
        
        if self.enable_emoji:
            result += f"**{info_emoji} 基本信息**\n"
        else:
            result += f"**基本信息**\n"
        result += f"- **标题**: {title}\n"
        result += f"- **链接**: {url}\n"
        result += f"- **内容类型**: {content_type}\n"
        result += f"- **质量评估**: {quality_indicator}\n\n"
        
        # 根据配置决定是否显示统计信息
        if self.enable_statistics:
            if self.enable_emoji:
                result += f"**{stats_emoji} 内容统计**\n"
            else:
                result += f"**内容统计**\n"
            result += f"- 字符数: {char_count:,}\n"
            result += f"- 段落数: {len(paragraphs)}\n"
            result += f"- 词数: {word_count:,}\n\n"
        
        if self.enable_emoji:
            result += f"**{search_emoji} 内容摘要**\n"
        else:
            result += f"**内容摘要**\n"
        result += f"{chr(10).join(['• ' + sentence[:100] + ('...' if len(sentence) > 100 else '') for sentence in key_sentences])}\n\n"
        
        if self.enable_emoji:
            result += f"**{light_emoji} 分析说明**\n"
        else:
            result += f"**分析说明**\n"
        result += "此分析基于网页内容提取，如需更深入的AI智能分析，请确保AstrBot已正确配置LLM功能。\n\n"
        result += "*提示：完整内容预览请查看原始网页*"
        
        return result
    
    @filter.command("web_config", alias={'网页分析配置', '网页分析设置'})
    async def show_config(self, event: AstrMessageEvent):
        """显示当前插件配置"""
        config_info = f"""**网页分析插件配置信息**

**基本设置**
- 最大内容长度: {self.max_content_length} 字符
- 请求超时时间: {self.timeout} 秒
- LLM智能分析: {'✅ 已启用' if self.llm_enabled else '❌ 已禁用'}
- 自动分析链接: {'✅ 已启用' if self.auto_analyze else '❌ 已禁用'}
- 合并转发功能: {'✅ 已启用' if self.merge_forward_enabled else '❌ 已禁用'}

**域名控制**
- 允许域名: {len(self.allowed_domains)} 个
- 禁止域名: {len(self.blocked_domains)} 个

**群聊控制**
- 群聊黑名单: {len(self.group_blacklist)} 个群聊

**分析设置**
- 启用emoji: {'✅ 已启用' if self.enable_emoji else '❌ 已禁用'}
- 显示统计: {'✅ 已启用' if self.enable_statistics else '❌ 已禁用'}
- 最大摘要长度: {self.max_summary_length} 字符

**LLM配置**
- 指定提供商: {self.llm_provider if self.llm_provider else '使用会话默认'}
- 自定义提示词: {'✅ 已启用' if self.custom_prompt else '❌ 未设置'}

*提示: 如需修改配置，请在AstrBot管理面板中编辑插件配置*"""
        
        yield event.plain_result(config_info)
    
    @filter.command("test_merge", alias={'测试合并转发', '测试转发'})
    async def test_merge_forward(self, event: AstrMessageEvent):
        '''测试合并转发功能'''
        from astrbot.api.message_components import Node, Plain, Nodes
        
        # 检查是否为群聊消息
        group_id = None
        if hasattr(event, 'group_id') and event.group_id:
            group_id = event.group_id
        elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'group_id') and event.message_obj.group_id:
            group_id = event.message_obj.group_id
        
        if group_id:
            # 创建测试用的合并转发节点
            nodes = []
            
            # 标题节点
            title_node = Node(
                uin=event.get_sender_id(),
                name="测试合并转发",
                content=[
                    Plain("这是合并转发测试消息")
                ]
            )
            nodes.append(title_node)
            
            # 内容节点1
            content_node1 = Node(
                uin=event.get_sender_id(),
                name="测试节点1",
                content=[
                    Plain("这是第一个测试节点内容")
                ]
            )
            nodes.append(content_node1)
            
            # 内容节点2
            content_node2 = Node(
                uin=event.get_sender_id(),
                name="测试节点2",
                content=[
                    Plain("这是第二个测试节点内容")
                ]
            )
            nodes.append(content_node2)
            
            # 使用Nodes包装所有节点，合并成一个合并转发消息
            merge_forward_message = Nodes(nodes)
            yield event.chain_result([merge_forward_message])
            logger.info(f"测试合并转发功能，群聊 {group_id}")
        else:
            yield event.plain_result("合并转发功能仅支持群聊消息测试")
            logger.info("私聊消息无法测试合并转发功能")
    
    @filter.command("group_blacklist", alias={'群黑名单', '黑名单'})
    async def manage_group_blacklist(self, event: AstrMessageEvent):
        """管理群聊黑名单"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()
        
        # 如果没有参数，显示当前黑名单
        if len(message_parts) <= 1:
            if not self.group_blacklist:
                yield event.plain_result("当前群聊黑名单为空")
                return
            
            blacklist_info = "**当前群聊黑名单**\n\n"
            for i, group_id in enumerate(self.group_blacklist, 1):
                blacklist_info += f"{i}. {group_id}\n"
            
            blacklist_info += "\n使用 `/group_blacklist add <群号>` 添加群聊到黑名单"
            blacklist_info += "\n使用 `/group_blacklist remove <群号>` 从黑名单移除群聊"
            blacklist_info += "\n使用 `/group_blacklist clear` 清空黑名单"
            
            yield event.plain_result(blacklist_info)
            return
        
        action = message_parts[1].lower() if len(message_parts) > 1 else ""
        group_id = message_parts[2] if len(message_parts) > 2 else ""
        
        if action == "add" and group_id:
            # 添加群聊到黑名单
            if group_id in self.group_blacklist:
                yield event.plain_result(f"群聊 {group_id} 已在黑名单中")
                return
            
            self.group_blacklist.append(group_id)
            self._save_group_blacklist()
            yield event.plain_result(f"✅ 已添加群聊 {group_id} 到黑名单")
            
        elif action == "remove" and group_id:
            # 从黑名单移除群聊
            if group_id not in self.group_blacklist:
                yield event.plain_result(f"群聊 {group_id} 不在黑名单中")
                return
            
            self.group_blacklist.remove(group_id)
            self._save_group_blacklist()
            yield event.plain_result(f"✅ 已从黑名单移除群聊 {group_id}")
            
        elif action == "clear":
            # 清空黑名单
            if not self.group_blacklist:
                yield event.plain_result("黑名单已为空")
                return
            
            self.group_blacklist.clear()
            self._save_group_blacklist()
            yield event.plain_result("✅ 已清空群聊黑名单")
            
        else:
            yield event.plain_result("无效的操作，请使用: add <群号>, remove <群号>, clear")
    
    def _save_group_blacklist(self):
        """保存群聊黑名单到配置"""
        try:
            # 将群聊列表转换为文本格式
            group_text = '\n'.join(self.group_blacklist)
            # 更新配置并保存
            self.config['group_blacklist'] = group_text
            self.config.save_config()
        except Exception as e:
            logger.error(f"保存群聊黑名单失败: {e}")
    
    async def _send_analysis_result(self, event, analysis_result, url):
        '''发送分析结果，根据开关决定是否使用合并转发'''
        from astrbot.api.message_components import Node, Plain, Nodes
        
        # 检查是否为群聊消息且合并转发功能已启用
        group_id = None
        if hasattr(event, 'group_id') and event.group_id:
            group_id = event.group_id
        elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'group_id') and event.message_obj.group_id:
            group_id = event.message_obj.group_id
        
        # 如果是群聊消息且合并转发功能已启用，使用合并转发
        if group_id and self.merge_forward_enabled:
            # 使用合并转发 - 将整个分析结果作为一个完整的节点发送
            nodes = []
            
            # 添加标题节点
            title_node = Node(
                uin=event.get_sender_id(),
                name="网页分析结果",
                content=[
                    Plain(f"网页分析结果 - {url}")
                ]
            )
            nodes.append(title_node)
            
            # 添加内容节点 - 整个分析结果作为一个节点，不分段
            content_node = Node(
                uin=event.get_sender_id(),
                name="详细分析",
                content=[
                    Plain(analysis_result)
                ]
            )
            nodes.append(content_node)
            
            # 使用Nodes包装所有节点，合并成一个合并转发消息
            merge_forward_message = Nodes(nodes)
            
            # 发送合并转发消息
            yield event.chain_result([merge_forward_message])
            logger.info(f"群聊 {group_id} 使用合并转发发送分析结果，不分段")
        else:
            # 普通发送
            result_text = f"网页分析结果：\n{analysis_result}"
            yield event.plain_result(result_text)
            message_type = "群聊" if group_id else "私聊"
            logger.info(f"{message_type}消息普通发送分析结果")
    
    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("网页分析插件已卸载")