"""
AstrBot 网页分析插件
自动识别用户发送的网页链接，抓取内容并调用LLM进行分析和总结
"""

import re
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


class WebAnalyzer:
    """网页分析器类"""
    
    def __init__(self, max_content_length: int = 10000, timeout: int = 30, user_agent: str = None):
        self.max_content_length = max_content_length
        self.timeout = timeout
        self.user_agent = user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        self.client = None
        self.browser = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.client:
            await self.client.aclose()
        if self.browser:
            await self.browser.close()
    
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
    
    async def capture_screenshot(self, url: str, quality: int = 80, width: int = 1280, full_page: bool = False, wait_time: int = 2000) -> Optional[bytes]:
        """捕获网页截图"""
        try:
            from playwright.async_api import async_playwright
            import sys
            import subprocess
            
            # 首先尝试安装浏览器（无论是否已安装，playwright install都会检查并更新）
            logger.info("正在检查并安装浏览器...")
            result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"浏览器安装失败: {result.stderr}")
                return None
            
            logger.info("浏览器安装成功，正在尝试截图...")
            
            # 尝试启动playwright并截图
            async with async_playwright() as p:
                # 启动浏览器（无头模式）
                self.browser = await p.chromium.launch(
                    headless=True,
                    # 添加额外的启动参数，提高兼容性
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--remote-debugging-port=9222'
                    ]
                )
                page = await self.browser.new_page(
                    viewport={'width': width, 'height': 720},
                    user_agent=self.user_agent
                )
                
                # 导航到目标URL，使用更宽松的等待条件
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                
                # 等待指定时间，确保页面完全加载
                await page.wait_for_timeout(wait_time)
                
                # 捕获截图
                screenshot_bytes = await page.screenshot(
                    full_page=full_page,
                    quality=quality,
                    type='jpeg'
                )
                
                await self.browser.close()
                self.browser = None
                
                logger.info("截图成功")
                return screenshot_bytes
        except Exception as e:
            logger.error(f"捕获网页截图失败: {url}, 错误: {e}")
            if self.browser:
                await self.browser.close()
                self.browser = None
            return None


@register("astrbot_plugin_web_analyzer", "Sakura520222", "自动识别网页链接并进行内容分析和总结", "1.0.0", "https://github.com/Sakura520222/astrbot_plugin_web_analyzer")
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
        # 截图设置
        self.enable_screenshot = analysis_settings.get('enable_screenshot', True)
        self.screenshot_quality = analysis_settings.get('screenshot_quality', 80)
        self.screenshot_width = analysis_settings.get('screenshot_width', 1280)
        self.screenshot_full_page = analysis_settings.get('screenshot_full_page', False)
        self.screenshot_wait_time = analysis_settings.get('screenshot_wait_time', 2000)
        
        # LLM提供商配置
        self.llm_provider = config.get('llm_provider', '')
        
        # 群聊黑名单配置
        group_blacklist_text = config.get('group_blacklist', '')
        self.group_blacklist = self._parse_group_list(group_blacklist_text)
        
        # 合并转发配置
        self.merge_forward_enabled = config.get('merge_forward_enabled', False)  # 是否启用合并转发
        
        # 自定义提示词配置
        self.custom_prompt = config.get('custom_prompt', '')  # 自定义分析提示词
        
        # 翻译设置
        translation_settings = config.get('translation_settings', {})
        self.enable_translation = translation_settings.get('enable_translation', False)
        self.target_language = translation_settings.get('target_language', 'zh')
        self.translation_provider = translation_settings.get('translation_provider', 'llm')
        self.custom_translation_prompt = translation_settings.get('custom_translation_prompt', '')
        
        # 缓存设置
        cache_settings = config.get('cache_settings', {})
        self.enable_cache = cache_settings.get('enable_cache', True)
        self.cache_expire_time = cache_settings.get('cache_expire_time', 1440)  # 分钟
        self.max_cache_size = cache_settings.get('max_cache_size', 100)
        
        # 初始化缓存
        self.cache = {}
        
        # 内容提取设置
        content_extraction_settings = config.get('content_extraction_settings', {})
        self.enable_specific_extraction = content_extraction_settings.get('enable_specific_extraction', False)
        extract_types_text = content_extraction_settings.get('extract_types', 'title\ncontent')
        self.extract_types = [t.strip() for t in extract_types_text.split('\n') if t.strip()]
        
        self.analyzer = WebAnalyzer(self.max_content_length, self.timeout, self.user_agent)
    
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
    async def analyze_webpage(self, event: AstrMessageEvent):
        """手动分析指定网页链接"""
        message_text = event.message_str
        
        # 提取所有URL
        urls = self.analyzer.extract_urls(message_text)
        if not urls:
            yield event.plain_result("请提供要分析的网页链接，例如：/网页分析 https://example.com")
            return
        
        # 验证URL并过滤掉不允许访问的域名
        valid_urls = [url for url in urls if self.analyzer.is_valid_url(url)]
        if not valid_urls:
            yield event.plain_result("无效的URL链接，请检查格式是否正确")
            return
        
        allowed_urls = [url for url in valid_urls if self._is_domain_allowed(url)]
        if not allowed_urls:
            yield event.plain_result("所有域名都不在允许访问的列表中，或已被禁止访问")
            return
        
        # 发送处理提示
        if len(allowed_urls) == 1:
            yield event.plain_result(f"正在分析网页: {allowed_urls[0]}")
        else:
            yield event.plain_result(f"正在分析{len(allowed_urls)}个网页链接...")
        
        # 批量处理所有URL
        async for result in self._batch_process_urls(event, allowed_urls):
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
        
        # 过滤掉不允许访问的域名
        allowed_urls = [url for url in valid_urls if self._is_domain_allowed(url)]
        if not allowed_urls:
            return  # 没有允许访问的URL，不处理
        
        # 发送处理提示
        if len(allowed_urls) == 1:
            yield event.plain_result(f"检测到网页链接，正在分析: {allowed_urls[0]}")
        else:
            yield event.plain_result(f"检测到{len(allowed_urls)}个网页链接，正在分析...")
        
        # 批量处理所有URL
        async for result in self._batch_process_urls(event, allowed_urls):
            yield result
    
    async def _batch_process_urls(self, event: AstrMessageEvent, urls: List[str]):
        """批量处理多个URL，收集分析结果并发送"""
        # 收集所有分析结果
        analysis_results = []
        
        async with WebAnalyzer(self.max_content_length, self.timeout, self.user_agent) as analyzer:
            for url in urls:
                try:
                    # 检查缓存
                    cached_result = self._check_cache(url)
                    if cached_result:
                        logger.info(f"使用缓存结果: {url}")
                        analysis_results.append(cached_result)
                        continue
                    
                    # 抓取网页内容
                    html = await analyzer.fetch_webpage(url)
                    if not html:
                        analysis_results.append({
                            'url': url,
                            'result': f"❌ 无法抓取网页内容: {url}",
                            'screenshot': None
                        })
                        continue
                    
                    # 提取内容
                    content_data = analyzer.extract_content(html, url)
                    if not content_data:
                        analysis_results.append({
                            'url': url,
                            'result': f"❌ 无法解析网页内容: {url}",
                            'screenshot': None
                        })
                        continue
                    
                    # 翻译内容（如果启用）
                    if self.enable_translation:
                        translated_content = await self._translate_content(event, content_data['content'])
                        # 创建翻译后的内容数据副本
                        translated_content_data = content_data.copy()
                        translated_content_data['content'] = translated_content
                        # 调用LLM进行分析（使用翻译后的内容）
                        analysis_result = await self.analyze_with_llm(event, translated_content_data)
                    else:
                        # 直接调用LLM进行分析
                        analysis_result = await self.analyze_with_llm(event, content_data)
                    
                    # 提取特定类型内容（如果启用）
                    specific_content = self._extract_specific_content(html, url)
                    if specific_content:
                        # 在分析结果中添加特定内容
                        specific_content_str = "\n\n**特定内容提取**\n"
                        
                        if 'images' in specific_content and specific_content['images']:
                            specific_content_str += f"\n📷 图片链接 ({len(specific_content['images'])}):\n"
                            for img_url in specific_content['images']:
                                specific_content_str += f"- {img_url}\n"
                        
                        if 'links' in specific_content and specific_content['links']:
                            specific_content_str += f"\n🔗 相关链接 ({len(specific_content['links'])}):\n"
                            for link in specific_content['links'][:5]:  # 只显示前5个链接
                                specific_content_str += f"- [{link['text']}]({link['url']})\n"
                        
                        if 'code_blocks' in specific_content and specific_content['code_blocks']:
                            specific_content_str += f"\n💻 代码块 ({len(specific_content['code_blocks'])}):\n"
                            for i, code in enumerate(specific_content['code_blocks'][:2]):  # 只显示前2个代码块
                                specific_content_str += f"```\n{code}\n```\n"
                        
                        # 添加到分析结果中
                        analysis_result += specific_content_str
                    
                    # 捕获截图
                    screenshot = None
                    if self.enable_screenshot:
                        screenshot = await analyzer.capture_screenshot(
                            url,
                            quality=self.screenshot_quality,
                            width=self.screenshot_width,
                            full_page=self.screenshot_full_page,
                            wait_time=self.screenshot_wait_time
                        )
                    
                    # 准备结果数据
                    result_data = {
                        'url': url,
                        'result': analysis_result,
                        'screenshot': screenshot
                    }
                    
                    # 更新缓存
                    self._update_cache(url, result_data)
                    
                    analysis_results.append(result_data)
                except Exception as e:
                    logger.error(f"处理URL {url} 时出错: {e}")
                    analysis_results.append({
                        'url': url,
                        'result': f"❌ 处理URL时出错: {url}\n错误信息: {str(e)}",
                        'screenshot': None
                    })
        
        # 发送所有分析结果
        async for result in self._send_analysis_result(event, analysis_results):
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
                
                formatted_result = "**AI智能网页分析报告**\n\n"
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
            result += "**基本信息**\n"
        result += f"- **标题**: {title}\n"
        result += f"- **链接**: {url}\n"
        result += f"- **内容类型**: {content_type}\n"
        result += f"- **质量评估**: {quality_indicator}\n\n"
        
        # 根据配置决定是否显示统计信息
        if self.enable_statistics:
            if self.enable_emoji:
                result += f"**{stats_emoji} 内容统计**\n"
            else:
                result += "**内容统计**\n"
            result += f"- 字符数: {char_count:,}\n"
            result += f"- 段落数: {len(paragraphs)}\n"
            result += f"- 词数: {word_count:,}\n\n"
        
        if self.enable_emoji:
            result += f"**{search_emoji} 内容摘要**\n"
        else:
            result += "**内容摘要**\n"
        result += f"{chr(10).join(['• ' + sentence[:100] + ('...' if len(sentence) > 100 else '') for sentence in key_sentences])}\n\n"
        
        if self.enable_emoji:
            result += f"**{light_emoji} 分析说明**\n"
        else:
            result += "**分析说明**\n"
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
- 启用截图: {'✅ 已启用' if self.enable_screenshot else '❌ 已禁用'}
- 截图质量: {self.screenshot_quality}
- 截图宽度: {self.screenshot_width}px
- 截取整页: {'✅ 已启用' if self.screenshot_full_page else '❌ 已禁用'}
- 截图等待时间: {self.screenshot_wait_time}ms

**LLM配置**
- 指定提供商: {self.llm_provider if self.llm_provider else '使用会话默认'}
- 自定义提示词: {'✅ 已启用' if self.custom_prompt else '❌ 未设置'}

**翻译设置**
- 启用网页翻译: {'✅ 已启用' if self.enable_translation else '❌ 已禁用'}
- 目标语言: {self.target_language}
- 翻译提供商: {self.translation_provider}
- 自定义翻译提示词: {'✅ 已启用' if self.custom_translation_prompt else '❌ 未设置'}

**缓存设置**
- 启用结果缓存: {'✅ 已启用' if self.enable_cache else '❌ 已禁用'}
- 缓存过期时间: {self.cache_expire_time} 分钟
- 最大缓存数量: {self.max_cache_size} 个

**内容提取设置**
- 启用特定内容提取: {'✅ 已启用' if self.enable_specific_extraction else '❌ 已禁用'}
- 提取内容类型: {', '.join(self.extract_types)}

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
    
    @filter.command("web_cache", alias={'网页缓存', '清理缓存'})
    async def manage_cache(self, event: AstrMessageEvent):
        """管理缓存"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()
        
        # 如果没有参数，显示当前缓存状态
        if len(message_parts) <= 1:
            cache_count = len(self.cache)
            cache_info = f"**当前缓存状态**\n\n"
            cache_info += f"- 缓存数量: {cache_count} 个\n"
            cache_info += f"- 缓存过期时间: {self.cache_expire_time} 分钟\n"
            cache_info += f"- 最大缓存数量: {self.max_cache_size} 个\n"
            cache_info += f"- 缓存功能: {'✅ 已启用' if self.enable_cache else '❌ 已禁用'}\n"
            
            cache_info += "\n使用 `/web_cache clear` 清空所有缓存"
            
            yield event.plain_result(cache_info)
            return
        
        action = message_parts[1].lower() if len(message_parts) > 1 else ""
        
        if action == "clear":
            # 清空缓存
            if not self.cache:
                yield event.plain_result("缓存已为空")
                return
            
            self.cache.clear()
            yield event.plain_result(f"✅ 已清空所有缓存，共清理了 {len(self.cache)} 个缓存项")
            
        else:
            yield event.plain_result("无效的操作，请使用: clear")
    
    @filter.command("web_export", alias={'导出分析结果', '网页导出'})
    async def export_analysis_result(self, event: AstrMessageEvent):
        """导出分析结果，支持Markdown、JSON等格式"""
        # 解析命令参数
        message_parts = event.message_str.strip().split()
        
        # 检查参数
        if len(message_parts) < 2:
            yield event.plain_result("请提供要导出的URL链接和格式，例如：/web_export https://example.com md 或 /web_export all json")
            return
        
        url_or_all = message_parts[1]
        format_type = message_parts[2] if len(message_parts) > 2 else "md"
        
        # 验证格式类型
        supported_formats = ["md", "markdown", "json", "txt"]
        if format_type.lower() not in supported_formats:
            yield event.plain_result(f"不支持的格式类型，请使用：{', '.join(supported_formats)}")
            return
        
        # 准备导出数据
        export_results = []
        
        if url_or_all.lower() == "all":
            # 导出所有缓存的分析结果
            if not self.cache:
                yield event.plain_result("当前没有缓存的分析结果")
                return
            
            for url, cache_data in self.cache.items():
                export_results.append({
                    "url": url,
                    "result": cache_data["result"]
                })
        else:
            # 导出指定URL的分析结果
            url = url_or_all
            
            # 检查URL是否有效
            if not self.analyzer.is_valid_url(url):
                yield event.plain_result("无效的URL链接")
                return
            
            # 检查缓存中是否有该URL的分析结果
            cached_result = self._check_cache(url)
            if cached_result:
                export_results.append({
                    "url": url,
                    "result": cached_result
                })
            else:
                # 如果缓存中没有，先进行分析
                yield event.plain_result(f"缓存中没有该URL的分析结果，正在进行分析...")
                
                # 抓取并分析网页
                async with WebAnalyzer(self.max_content_length, self.timeout, self.user_agent) as analyzer:
                    html = await analyzer.fetch_webpage(url)
                    if not html:
                        yield event.plain_result(f"无法抓取网页内容: {url}")
                        return
                    
                    content_data = analyzer.extract_content(html, url)
                    if not content_data:
                        yield event.plain_result(f"无法解析网页内容: {url}")
                        return
                    
                    # 调用LLM进行分析
                    if self.enable_translation:
                        translated_content = await self._translate_content(event, content_data['content'])
                        translated_content_data = content_data.copy()
                        translated_content_data['content'] = translated_content
                        analysis_result = await self.analyze_with_llm(event, translated_content_data)
                    else:
                        analysis_result = await self.analyze_with_llm(event, content_data)
                    
                    # 提取特定内容
                    specific_content = self._extract_specific_content(html, url)
                    if specific_content:
                        # 在分析结果中添加特定内容
                        specific_content_str = "\n\n**特定内容提取**\n"
                        
                        if 'images' in specific_content and specific_content['images']:
                            specific_content_str += f"\n📷 图片链接 ({len(specific_content['images'])}):\n"
                            for img_url in specific_content['images']:
                                specific_content_str += f"- {img_url}\n"
                        
                        if 'links' in specific_content and specific_content['links']:
                            specific_content_str += f"\n🔗 相关链接 ({len(specific_content['links'])}):\n"
                            for link in specific_content['links'][:5]:  # 只显示前5个链接
                                specific_content_str += f"- [{link['text']}]({link['url']})\n"
                        
                        if 'code_blocks' in specific_content and specific_content['code_blocks']:
                            specific_content_str += f"\n💻 代码块 ({len(specific_content['code_blocks'])}):\n"
                            for i, code in enumerate(specific_content['code_blocks'][:2]):  # 只显示前2个代码块
                                specific_content_str += f"```\n{code}\n```\n"
                        
                        analysis_result += specific_content_str
                    
                    # 准备导出数据
                    export_results.append({
                        "url": url,
                        "result": {
                            "url": url,
                            "result": analysis_result,
                            "screenshot": None
                        }
                    })
        
        # 执行导出
        try:
            import os
            import json
            import tempfile
            import time
            
            # 创建data目录（如果不存在）
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            os.makedirs(data_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = int(time.time())
            if len(export_results) == 1:
                # 单个URL导出
                url = export_results[0]["url"]
                # 从URL中提取域名作为文件名的一部分
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc.replace(".", "_")
                filename = f"web_analysis_{domain}_{timestamp}"
            else:
                # 多个URL导出
                filename = f"web_analysis_all_{timestamp}"
            
            # 根据格式生成文件内容
            file_extension = format_type.lower()
            if file_extension == "markdown":
                file_extension = "md"
            
            file_path = os.path.join(data_dir, f"{filename}.{file_extension}")
            
            if format_type.lower() in ["md", "markdown"]:
                # 生成Markdown格式内容
                md_content = "# 网页分析结果导出\n\n"
                md_content += f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}\n\n"
                md_content += f"共 {len(export_results)} 个分析结果\n\n"
                md_content += "---\n\n"
                
                for i, export_item in enumerate(export_results, 1):
                    url = export_item["url"]
                    result_data = export_item["result"]
                    
                    md_content += f"## {i}. {url}\n\n"
                    md_content += result_data["result"]
                    md_content += "\n\n"
                    md_content += "---\n\n"
                
                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
            
            elif format_type.lower() == "json":
                # 生成JSON格式内容
                json_data = {
                    "export_time": timestamp,
                    "export_time_str": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp)),
                    "total_results": len(export_results),
                    "results": []
                }
                
                for export_item in export_results:
                    url = export_item["url"]
                    result_data = export_item["result"]
                    
                    json_data["results"].append({
                        "url": url,
                        "analysis_result": result_data["result"],
                        "has_screenshot": result_data["screenshot"] is not None
                    })
                
                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            elif format_type.lower() == "txt":
                # 生成纯文本格式内容
                txt_content = f"网页分析结果导出\n"
                txt_content += f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}\n"
                txt_content += f"共 {len(export_results)} 个分析结果\n"
                txt_content += "=" * 50 + "\n\n"
                
                for i, export_item in enumerate(export_results, 1):
                    url = export_item["url"]
                    result_data = export_item["result"]
                    
                    txt_content += f"{i}. {url}\n"
                    txt_content += "-" * 30 + "\n"
                    txt_content += result_data["result"]
                    txt_content += "\n\n"
                    txt_content += "=" * 50 + "\n\n"
                
                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(txt_content)
            
            # 发送导出成功消息，并附带导出文件
            from astrbot.api.message_components import Plain, File
            
            # 构建消息链
            message_chain = [
                Plain(f"✅ 分析结果导出成功！\n\n"),
                Plain(f"导出格式: {format_type}\n"),
                Plain(f"导出数量: {len(export_results)}\n\n"),
                Plain("📁 导出文件：\n"),
                File(file=file_path, name=os.path.basename(file_path))
            ]
            
            yield event.chain_result(message_chain)
            
            logger.info(f"成功导出 {len(export_results)} 个分析结果到 {file_path}，并发送给用户")
        
        except Exception as e:
            logger.error(f"导出分析结果失败: {e}")
            yield event.plain_result(f"❌ 导出分析结果失败: {str(e)}")
    
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
    
    def _check_cache(self, url: str) -> dict:
        """检查缓存是否存在且有效"""
        if not self.enable_cache:
            return None
        
        import time
        current_time = time.time()
        
        if url in self.cache:
            cache_data = self.cache[url]
            if current_time - cache_data['timestamp'] < self.cache_expire_time * 60:
                return cache_data['result']
            else:
                # 缓存过期，删除
                del self.cache[url]
        
        return None
    
    def _update_cache(self, url: str, result: dict):
        """更新缓存"""
        if not self.enable_cache:
            return
        
        import time
        current_time = time.time()
        
        # 清理过期缓存
        self._clean_cache()
        
        # 检查缓存大小
        if len(self.cache) >= self.max_cache_size:
            # 删除最旧的缓存
            oldest_url = min(self.cache, key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_url]
        
        # 添加新缓存
        self.cache[url] = {
            'timestamp': current_time,
            'result': result
        }
    
    def _clean_cache(self):
        """清理过期缓存"""
        import time
        current_time = time.time()
        
        expired_urls = []
        for url, cache_data in self.cache.items():
            if current_time - cache_data['timestamp'] >= self.cache_expire_time * 60:
                expired_urls.append(url)
        
        for url in expired_urls:
            del self.cache[url]
    
    async def _translate_content(self, event: AstrMessageEvent, content: str) -> str:
        """翻译网页内容"""
        if not self.enable_translation:
            return content
        
        try:
            # 检查LLM是否可用
            if not hasattr(self.context, 'llm_generate'):
                logger.error("LLM不可用，无法进行翻译")
                return content
            
            # 优先使用配置的LLM提供商，如果没有配置则使用当前会话的模型
            provider_id = self.llm_provider
            if not provider_id:
                umo = event.unified_msg_origin
                provider_id = await self.context.get_current_chat_provider_id(umo=umo)
            
            if not provider_id:
                logger.error("无法获取LLM提供商ID，无法进行翻译")
                return content
            
            # 使用自定义翻译提示词或默认提示词
            if self.custom_translation_prompt:
                # 替换自定义提示词中的变量
                prompt = self.custom_translation_prompt.format(
                    content=content,
                    target_language=self.target_language
                )
            else:
                # 默认翻译提示词
                prompt = f"请将以下内容翻译成{self.target_language}语言，保持原文意思不变，语言流畅自然：\n\n{content}"
            
            # 调用LLM进行翻译
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt
            )
            
            if llm_resp and llm_resp.completion_text:
                return llm_resp.completion_text.strip()
            else:
                logger.error("LLM翻译返回为空")
                return content
        except Exception as e:
            logger.error(f"翻译内容失败: {e}")
            return content
    
    def _extract_specific_content(self, html: str, url: str) -> dict:
        """提取特定类型的内容"""
        if not self.enable_specific_extraction:
            return {}
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            extracted_content = {}
            
            # 提取标题
            if 'title' in self.extract_types:
                title = soup.find('title')
                extracted_content['title'] = title.get_text().strip() if title else "无标题"
            
            # 提取正文内容
            if 'content' in self.extract_types:
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
                        for script in element(['script', 'style']):
                            script.decompose()
                        text = element.get_text(separator='\n', strip=True)
                        if len(text) > len(content_text):
                            content_text = text
                
                if len(content_text) > self.max_content_length:
                    content_text = content_text[:self.max_content_length] + "..."
                
                extracted_content['content'] = content_text
            
            # 提取图片链接
            if 'images' in self.extract_types:
                images = []
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if src:
                        # 处理相对路径
                        from urllib.parse import urljoin
                        full_url = urljoin(url, src)
                        images.append(full_url)
                extracted_content['images'] = images[:10]  # 最多提取10张图片
            
            # 提取链接
            if 'links' in self.extract_types:
                links = []
                for a in soup.find_all('a', href=True):
                    href = a.get('href')
                    if href and not href.startswith('#'):
                        from urllib.parse import urljoin
                        full_url = urljoin(url, href)
                        links.append({
                            'text': a.get_text().strip() or full_url,
                            'url': full_url
                        })
                extracted_content['links'] = links[:20]  # 最多提取20个链接
            
            # 提取表格
            if 'tables' in self.extract_types:
                tables = []
                for table in soup.find_all('table'):
                    table_data = []
                    # 提取表头
                    headers = []
                    thead = table.find('thead')
                    if thead:
                        for th in thead.find_all('th'):
                            headers.append(th.get_text().strip())
                    
                    # 提取表体
                    tbody = table.find('tbody') or table
                    for row in tbody.find_all('tr'):
                        row_data = []
                        for cell in row.find_all(['td', 'th']):
                            row_data.append(cell.get_text().strip())
                        if row_data:
                            table_data.append(row_data)
                    
                    if table_data:
                        tables.append({
                            'headers': headers,
                            'rows': table_data
                        })
                extracted_content['tables'] = tables[:5]  # 最多提取5个表格
            
            # 提取列表
            if 'lists' in self.extract_types:
                lists = []
                # 提取无序列表
                for ul in soup.find_all('ul'):
                    list_items = []
                    for li in ul.find_all('li'):
                        list_items.append(li.get_text().strip())
                    if list_items:
                        lists.append({
                            'type': 'ul',
                            'items': list_items[:20]  # 每个列表最多提取20项
                        })
                
                # 提取有序列表
                for ol in soup.find_all('ol'):
                    list_items = []
                    for li in ol.find_all('li'):
                        list_items.append(li.get_text().strip())
                    if list_items:
                        lists.append({
                            'type': 'ol',
                            'items': list_items[:20]  # 每个列表最多提取20项
                        })
                extracted_content['lists'] = lists[:10]  # 最多提取10个列表
            
            # 提取代码块
            if 'code' in self.extract_types:
                code_blocks = []
                for code in soup.find_all(['pre', 'code']):
                    code_text = code.get_text().strip()
                    if code_text and len(code_text) > 10:
                        code_blocks.append(code_text[:1000] + "..." if len(code_text) > 1000 else code_text)
                extracted_content['code_blocks'] = code_blocks[:5]  # 最多提取5个代码块
            
            return extracted_content
        except Exception as e:
            logger.error(f"提取特定内容失败: {e}")
            return {}
    
    async def _send_analysis_result(self, event, analysis_results):
        '''发送分析结果，根据开关决定是否使用合并转发'''
        from astrbot.api.message_components import Node, Plain, Nodes, Image
        import tempfile
        import os
        
        # 检查是否为群聊消息且合并转发功能已启用
        group_id = None
        if hasattr(event, 'group_id') and event.group_id:
            group_id = event.group_id
        elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'group_id') and event.message_obj.group_id:
            group_id = event.message_obj.group_id
        
        # 如果是群聊消息且合并转发功能已启用，使用合并转发
        if group_id and self.merge_forward_enabled:
            # 使用合并转发 - 将所有分析结果合并成一个合并转发消息
            nodes = []
            
            # 添加总标题节点
            total_title_node = Node(
                uin=event.get_sender_id(),
                name="网页分析结果汇总",
                content=[
                    Plain(f"共{len(analysis_results)}个网页分析结果")
                ]
            )
            nodes.append(total_title_node)
            
            # 为每个URL添加分析结果节点
            for i, result_data in enumerate(analysis_results, 1):
                url = result_data['url']
                analysis_result = result_data['result']
                screenshot = result_data['screenshot']
                
                # 添加当前URL的标题节点
                url_title_node = Node(
                    uin=event.get_sender_id(),
                    name=f"分析结果 {i}",
                    content=[
                        Plain(f"第{i}个网页分析结果 - {url}")
                    ]
                )
                nodes.append(url_title_node)
                
                # 添加当前URL的内容节点
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
            
            # 如果有截图，逐个发送截图
            for result_data in analysis_results:
                screenshot = result_data['screenshot']
                if screenshot:
                    try:
                        # 创建临时文件保存截图
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                            temp_file.write(screenshot)
                            temp_file_path = temp_file.name
                        
                        # 使用Image.fromFileSystem()方法发送图片
                        image_component = Image.fromFileSystem(temp_file_path)
                        yield event.chain_result([image_component])
                        logger.info(f"群聊 {group_id} 使用合并转发发送分析结果，并发送截图")
                        
                        # 删除临时文件
                        os.unlink(temp_file_path)
                    except Exception as e:
                        logger.error(f"发送截图失败: {e}")
                        # 确保临时文件被删除
                        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
            logger.info(f"群聊 {group_id} 使用合并转发发送{len(analysis_results)}个分析结果")
        else:
            # 普通发送 - 逐个发送分析结果
            for i, result_data in enumerate(analysis_results, 1):
                url = result_data['url']
                analysis_result = result_data['result']
                screenshot = result_data['screenshot']
                
                # 发送分析结果文本
                if len(analysis_results) == 1:
                    result_text = f"网页分析结果：\n{analysis_result}"
                else:
                    result_text = f"第{i}/{len(analysis_results)}个网页分析结果：\n{analysis_result}"
                yield event.plain_result(result_text)
                
                # 如果有截图，发送截图
                if screenshot:
                    try:
                        # 创建临时文件保存截图
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                            temp_file.write(screenshot)
                            temp_file_path = temp_file.name
                        
                        # 使用Image.fromFileSystem()方法发送图片
                        image_component = Image.fromFileSystem(temp_file_path)
                        yield event.chain_result([image_component])
                        logger.info("普通发送分析结果，并发送截图")
                        
                        # 删除临时文件
                        os.unlink(temp_file_path)
                    except Exception as e:
                        logger.error(f"发送截图失败: {e}")
                        # 确保临时文件被删除
                        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
            message_type = "群聊" if group_id else "私聊"
            logger.info(f"{message_type}消息普通发送{len(analysis_results)}个分析结果")
    
    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("网页分析插件已卸载")