"""
网页分析插件工具类

包含各种通用工具函数和辅助方法，用于支持插件的核心功能。
"""

import re
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional


class WebAnalyzerUtils:
    """网页分析插件工具类
    
    包含各种通用工具函数和辅助方法，用于支持插件的核心功能。
    """
    
    @staticmethod
    def get_current_time() -> str:
        """获取当前时间的格式化字符串
        
        Returns:
            格式化的时间字符串
        """
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def parse_domain_list(domain_text: str) -> List[str]:
        """将多行域名文本转换为Python列表
        
        处理配置中定义的域名列表，支持：
        - 每行一个域名的格式
        - 自动去除空行和前后空白字符
        - 支持域名通配符（如*.example.com）
        
        Args:
            domain_text: 包含域名的多行文本字符串
        
        Returns:
            解析后的域名列表，已清理无效内容
        """
        if not domain_text:
            return []
        domains = [
            domain.strip() for domain in domain_text.split("\n") if domain.strip()
        ]
        return domains
    
    @staticmethod
    def parse_group_list(group_text: str) -> List[str]:
        """将多行群聊ID文本转换为Python列表
        
        处理配置中定义的群聊黑名单，支持：
        - 每行一个群聊ID的格式
        - 自动去除空行和前后空白字符
        - 支持数字和字符串类型的群聊ID
        
        Args:
            group_text: 包含群聊ID的多行文本字符串
        
        Returns:
            解析后的群聊ID列表，已清理无效内容
        """
        if not group_text:
            return []
        groups = [group.strip() for group in group_text.split("\n") if group.strip()]
        return groups
    
    @staticmethod
    def parse_extract_types(extract_types_text: str) -> List[str]:
        """解析提取类型配置
        
        Args:
            extract_types_text: 包含提取类型的多行文本字符串
        
        Returns:
            解析后的提取类型列表
        """
        if not extract_types_text:
            return []
        return [
            extract_type.strip() for extract_type in extract_types_text.split("\n") if extract_type.strip()
        ]
    
    @staticmethod
    def validate_extract_types(extract_types: List[str]) -> List[str]:
        """验证提取类型是否有效
        
        Args:
            extract_types: 提取类型列表
        
        Returns:
            验证后的提取类型列表
        """
        valid_types = ["title", "content", "images", "links", "meta", "code_blocks", "tables"]
        return [extract_type for extract_type in extract_types if extract_type in valid_types]
    
    @staticmethod
    def ensure_minimal_extract_types(extract_types: List[str]) -> List[str]:
        """确保至少包含必要的提取类型
        
        Args:
            extract_types: 提取类型列表
        
        Returns:
            确保包含必要提取类型的列表
        """
        minimal_types = ["title", "content"]
        for minimal_type in minimal_types:
            if minimal_type not in extract_types:
                extract_types.append(minimal_type)
        return extract_types
    
    @staticmethod
    def add_required_extract_types(extract_types: List[str]) -> List[str]:
        """添加必需的提取类型
        
        Args:
            extract_types: 提取类型列表
        
        Returns:
            添加了必需提取类型的列表
        """
        return extract_types
    
    @staticmethod
    def is_domain_allowed(url: str, allowed_domains: List[str], blocked_domains: List[str]) -> bool:
        """检查指定URL的域名是否允许访问
        
        根据配置的允许和禁止域名列表，判断URL是否可以访问，
        支持灵活的访问控制策略：
        
        访问规则（优先级从高到低）：
        1. 如果域名在禁止列表中，直接拒绝访问
        2. 如果允许列表不为空，只有在列表中的域名才允许访问
        3. 如果允许列表为空，则允许所有未被禁止的域名
        
        Args:
            url: 要检查的完整URL
            allowed_domains: 允许访问的域名列表
            blocked_domains: 禁止访问的域名列表
        
        Returns:
            True表示允许访问，False表示禁止访问
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # 首先检查是否在禁止列表中
            if blocked_domains:
                for blocked_domain in blocked_domains:
                    if blocked_domain.lower() in domain:
                        return False
            
            # 然后检查是否在允许列表中（如果允许列表不为空）
            if allowed_domains:
                for allowed_domain in allowed_domains:
                    if allowed_domain.lower() in domain:
                        return True
                return False
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_url_priority(url: str) -> int:
        """评估URL的处理优先级
        
        根据URL的特性评估其处理优先级，优先级从1到10，数字越大优先级越高
        
        Args:
            url: 要评估优先级的URL
            
        Returns:
            优先级数值（1-10）
        """
        # 默认优先级
        priority = 5
        
        try:
            # 提取URL的域名和路径信息
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            path = parsed_url.path.lower()
            
            # 短链接优先（路径较短）
            if len(path) < 20:
                priority += 2
            # 已知的新闻网站优先级较高
            news_domains = ["news.", "cnn.", "bbc.", "nytimes.", "reuters.", "ap.", "afp.", "xinhua.", "people.", "sina.", "sohu.", "netease."]
            for news_domain in news_domains:
                if news_domain in domain:
                    priority += 3
                    break
            # 已知的技术网站优先级较高
            tech_domains = ["github.", "stackoverflow.", "medium.", "dev.to", "towardsdatascience.", "geeksforgeeks."]
            for tech_domain in tech_domains:
                if tech_domain in domain:
                    priority += 2
                    break
            # 已知的视频网站优先级较低（通常需要较长时间处理）
            video_domains = ["youtube.", "bilibili.", "tiktok.", "douyin.", "youku.", "iqiyi."]
            for video_domain in video_domains:
                if video_domain in domain:
                    priority -= 2
                    break
        except Exception:
            pass
        
        # 确保优先级在1-10范围内
        return max(1, min(10, priority))
    
    @staticmethod
    def detect_content_type(content: str) -> str:
        """检测网页内容类型
        
        根据网页内容的特征，自动检测其类型，支持多种内容类型：
        - 新闻资讯
        - 教程指南
        - 个人博客
        - 产品介绍
        - 技术文档
        - 学术论文
        
        Args:
            content: 网页内容
            
        Returns:
            检测到的内容类型
        """
        content_lower = content.lower()
        
        # 新闻资讯特征
        news_keywords = ["新闻", "资讯", "报道", "快讯", "时事", "热点", "头条"]
        if any(keyword in content_lower for keyword in news_keywords):
            return "新闻资讯"
        
        # 教程指南特征
        tutorial_keywords = ["教程", "指南", "教程", "学习", "如何", "步骤", "方法", "技巧", "实战"]
        if any(keyword in content_lower for keyword in tutorial_keywords):
            return "教程指南"
        
        # 个人博客特征
        blog_keywords = ["博客", "日志", "随笔", "感悟", "分享", "思考", "心得"]
        if any(keyword in content_lower for keyword in blog_keywords):
            return "个人博客"
        
        # 产品介绍特征
        product_keywords = ["产品", "服务", "功能", "特性", "优势", "价格", "购买", "下载"]
        if any(keyword in content_lower for keyword in product_keywords):
            return "产品介绍"
        
        # 技术文档特征
        tech_keywords = ["文档", "API", "SDK", "开发", "技术", "编程", "代码", "框架", "库"]
        if any(keyword in content_lower for keyword in tech_keywords):
            return "技术文档"
        
        # 学术论文特征
        academic_keywords = ["论文", "研究", "实验", "结果", "结论", "摘要", "引言", "方法", "分析"]
        if any(keyword in content_lower for keyword in academic_keywords):
            return "学术论文"
        
        # 默认类型
        return "新闻资讯"
