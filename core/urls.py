"""
URL 与域名规则模块

提供链接提取、格式校验、规范化和域名访问控制。
截图与正文抓取共用同一套校验规则。
"""

import ipaddress
import re
from urllib.parse import urlparse

# 带协议头的 URL：排除中文等非 ASCII 字符
_PROTOCOL_URL_PATTERN = r"https?://[^\s一-鿿]+"
# 无协议头的 URL：域名 + 可选路径
_NO_PROTOCOL_URL_PATTERN = (
    r"(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]"
    r"(?:\.[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9])+(?:/[^\s一-鿿]*)?"
)
_NO_PROTOCOL_SUFFIXES = ".,;:!?)'\""


def extract_urls(
    text: str, enable_no_protocol: bool = False, default_protocol: str = "https"
) -> list[str]:
    """从文本中提取所有 URL 链接。

    Args:
        text: 消息文本。
        enable_no_protocol: 是否识别没有协议头的链接（如 www.example.com）。
        default_protocol: 无协议头链接补全的协议。

    Returns:
        提取到的 URL 列表。
    """
    urls = re.findall(_PROTOCOL_URL_PATTERN, text)
    if enable_no_protocol:
        remainder = text
        for url in urls:
            remainder = remainder.replace(url, "")
        for match in re.findall(_NO_PROTOCOL_URL_PATTERN, remainder):
            cleaned = match.rstrip(_NO_PROTOCOL_SUFFIXES)
            urls.append(f"{default_protocol}://{cleaned}")
    return urls


def is_valid_url(url: str, allow_local: bool = False) -> bool:
    """校验 URL 格式，并拒绝指向内网/回环地址的目标（SSRF 防护）。

    仅检查 URL 中直接书写的 IP 与 localhost 域名，不解析 DNS：
    本地代理工具会劫持 DNS。allow_local 开启时放行本地/内网目标，
    供用户在可信网络环境截图或读取本地服务。

    Args:
        url: 待校验的 URL。
        allow_local: 是否允许本地/内网地址。

    Returns:
        URL 是否有效。
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        if not parsed.netloc or not parsed.hostname:
            return False
        if allow_local:
            return True
        hostname = parsed.hostname
        if hostname == "localhost" or hostname.endswith(".localhost"):
            return False
        try:
            addr = ipaddress.ip_address(hostname)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
            ):
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


def normalize_url(url: str, unify_www: bool = False) -> str:
    """规范化 URL：小写协议与域名，去掉路径尾部斜杠。

    Args:
        url: 待规范化的 URL。
        unify_www: 开启时给非 IP 主机补 www. 前缀，
            使 example.com 与 www.example.com 归一（用于缓存与去重）。
    """
    try:
        parsed = urlparse(url)
        netloc = _normalize_netloc(parsed.netloc.lower(), unify_www)
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=netloc,
            path=parsed.path.rstrip("/"),
        )
        return normalized.geturl()
    except Exception:
        return url


def _normalize_netloc(netloc: str, unify_www: bool) -> str:
    """按需把裸域名归一到 www. 形式；IP 与已带 www 的主机保持原样。"""
    if not unify_www or not netloc or "." not in netloc:
        return netloc
    if netloc.startswith("www.") or ".www." in netloc:
        return netloc
    try:
        ipaddress.ip_address(netloc)
        return netloc
    except ValueError:
        return f"www.{netloc}"


def parse_domain_list(domain_text: str) -> list[str]:
    """把多行域名文本解析为列表，过滤空行和空白。"""
    if not domain_text:
        return []
    return [domain.strip() for domain in str(domain_text).split("\n") if domain.strip()]


def parse_group_list(group_text: str) -> list[str]:
    """把多行群号文本解析为列表。"""
    if not group_text:
        return []
    return [group.strip() for group in str(group_text).split("\n") if group.strip()]


def is_domain_allowed(
    url: str, allowed_domains: list[str], blocked_domains: list[str]
) -> bool:
    """按访问规则判断 URL 是否允许访问。

    优先级：
    1. 命中禁止列表 → 拒绝；
    2. 允许列表非空且未命中 → 拒绝；
    3. 其余放行。

    Args:
        url: 完整 URL。
        allowed_domains: 允许的域名列表。
        blocked_domains: 禁止的域名列表。

    Returns:
        是否允许访问。
    """
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        return False
    if _matches_domain(domain, blocked_domains):
        return False
    if allowed_domains and not _matches_domain(domain, allowed_domains):
        return False
    return True


def _matches_domain(domain: str, patterns: list[str]) -> bool:
    """后缀匹配域名列表，支持子域名；不匹配空串或非域名的意外输入。"""
    domain = domain.rstrip(".")
    for pattern in patterns:
        candidate = str(pattern).lower().rstrip(".")
        if not candidate:
            continue
        if domain == candidate or domain.endswith("." + candidate):
            return True
    return False


def is_container_environment() -> bool:
    """检测当前是否运行在需要禁用浏览器沙箱的容器环境。

    检测顺序：Windows 直接返回 False → Docker → cgroup → Kubernetes →
    root 用户 → 用户命名空间 → systemd-nspawn。首次匹配即返回。

    Returns:
        True 表示检测到容器或受限环境。
    """
    import os
    import sys

    if sys.platform == "win32":
        return False

    if os.path.exists("/.dockerenv"):
        return True

    try:
        with open("/proc/1/cgroup") as f:
            cgroup_content = f.read().lower()
        container_keywords = ("docker", "containerd", "lxc", "kubepods")
        if any(kw in cgroup_content for kw in container_keywords):
            return True
    except OSError:
        pass

    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        return True

    try:
        if os.getuid() == 0:
            return True
    except AttributeError:
        pass

    try:
        with open("/proc/self/uid_map") as f:
            uid_map = f.read().strip()
        parts = uid_map.split()
        if len(parts) >= 2 and (parts[0] != "0" or parts[1] != "0"):
            return True
    except OSError:
        pass

    try:
        container_env = os.environ.get("container", "")
        known_container_types = (
            "docker",
            "lxc",
            "lxc-libvirt",
            "systemd-nspawn",
            "podman",
        )
        if container_env and container_env in known_container_types:
            return True
        if os.path.exists("/run/systemd/container"):
            with open("/run/systemd/container") as f:
                content = f.read().strip()
            if content and content in known_container_types:
                return True
    except OSError:
        pass

    return False
