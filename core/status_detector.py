"""
FlashSloth 登录状态检测器 — 三层架构

第一层：API轻量检测（最快，优先）
  - 用Cookie调平台API/页面 → 提取用户名/积分/等级
  - 零浏览器开销，毫秒级返回

第二层：Playwright快速检测（中等）
  - 打开个人主页/用户中心，解析页面上的用户信息
  - 单页面加载，不等待完整渲染

第三层：全量Playwright浏览器（较重，兜底）
  - 完整打开网站，注入Cookie，模拟登录验证

检测结果数据结构:
{
    "logged_in": true|false,
    "username": "duxingkei",
    "display_name": "杜行客",
    "points": 12580,
    "level": "高级会员",
    "points_label": "积分",
    "avatar_url": "https://...",
    "verified_at": "2026-07-07T07:00:00",
    "method": "api_lightweight" | "playwright_fast" | "playwright_full",
    "status": "✅ duxingkei (积分:12580)",
    "success": true
}
"""

import re
import json
import time
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 第一层：API轻量检测
# ═══════════════════════════════════════════════════════════

def _make_session():
    """创建带基本UA的requests Session"""
    import requests
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return sess


def _parse_cookie_header(cookie_str: str) -> dict:
    """将 Cookie 字符串解析为 dict"""
    result = {}
    if not cookie_str:
        return result
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        result[n.strip()] = v.strip()
    return result


def detect_discuz(site_url: str, cookie_str: str, platform: str = "discuz") -> dict:
    """
    Discuz 论坛 API轻量检测
    用Cookie访问 /home.php?mod=space&do=profile
    解析HTML中的用户名、积分、等级
    """
    result = {
        "logged_in": False,
        "method": "api_lightweight",
        "platform": platform,
        "site_url": site_url,
    }
    
    if not cookie_str or not site_url:
        return result
    
    site_url = site_url.rstrip("/")
    
    try:
        sess = _make_session()
        # 注入Cookie
        for name, value in _parse_cookie_header(cookie_str).items():
            sess.cookies.set(name, value)
        
        # 访问个人资料页面
        profile_url = f"{site_url}/home.php?mod=space&do=profile"
        resp = sess.get(profile_url, timeout=15, allow_redirects=True)
        
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result
        
        html = resp.text
        
        # 检查是否被重定向到登录页
        if "login" in resp.url.lower() or "logging" in resp.url.lower():
            result["error"] = "重定向到登录页（Cookie可能已过期）"
            return result
        
        # 检查是否包含"退出"或"logout" — 这是已登录的标志
        has_logout = bool(re.search(r'退出|注销|logout', html, re.IGNORECASE))
        
        # 提取用户名（通常在欢迎信息或用户资料中）
        username = ""
        # 尝试多种Discuz用户名模式
        name_patterns = [
            r'<title>[^<]*?([\u4e00-\u9fff\w]+)[^<]*?的个人资料',
            r'<a[^>]*?>([\u4e00-\u9fff\w]+)</a>\s*的</em>\s*个人资料',
            r'<em>([\u4e00-\u9fff\w]+)</em>',
            r'欢迎您回来[：:]\s*([\u4e00-\u9fff\w]+)',
            r'欢迎\s*([\u4e00-\u9fff\w]+)',
            r'username[":\s>]+([\u4e00-\u9fff\w]+)',
        ]
        for pat in name_patterns:
            m = re.search(pat, html)
            if m:
                username = m.group(1).strip()
                if len(username) >= 2:
                    break
        
        # 提取积分
        points = 0
        points_label = "积分"
        # Discuz积分模式
        point_patterns = [
            r'积分[：:>\s]*(\d[\d,.]*)',
            r'积分.*?(\d[\d,.]*)',
            r'points[">\s]*(\d+)',
            r'class="[^"]*credit[^"]*"[^>]*>(\d[\d,.]*)',
            r'credit[=_\s]*(\d+)',
            r'<li><em>积分</em>\s*(\d[\d,.]*)\s*</li>',
        ]
        for pat in point_patterns:
            m = re.search(pat, html)
            if m:
                try:
                    points = int(m.group(1).replace(",", "").replace(".", ""))
                except ValueError:
                    pass
                break
        
        # 提取等级
        level = ""
        level_patterns = [
            r'用户组[：:>\s]+([^<]{2,20})',
            r'等级[：:>\s]+([^<]{2,20})',
            r'class="[^"]*group[^"]*"[^>]*>([^<]{2,20})',
        ]
        for pat in level_patterns:
            m = re.search(pat, html)
            if m:
                level = m.group(1).strip()
                if level and len(level) >= 2:
                    break
        
        # 提取头像URL
        avatar_url = ""
        avatar_patterns = [
            r'<img[^>]*id="avatar"[^>]*src="([^"]+)"',
            r'<img[^>]*class="[^"]*avatar[^"]*"[^>]*src="([^"]+)"',
            r'avatar[=/_]?([^"\s&]+)',
        ]
        for pat in avatar_patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                avatar_url = m.group(1)
                if avatar_url.startswith("//"):
                    avatar_url = "https:" + avatar_url
                break
        
        # 判断登录状态 — 铁律：必须有真实用户信息（退出按钮/用户名）才认定为已登录
        # resp.url == profile_url 太弱（未登录也能看到个人资料页，只是内容不同）
        logged_in = has_logout or bool(username)
        
        result["logged_in"] = logged_in
        result["username"] = username if username else ""
        result["points"] = points
        result["points_label"] = points_label
        result["level"] = level if level else ""
        result["avatar_url"] = avatar_url
        result["verified_at"] = datetime.now().isoformat()
        
        if logged_in:
            parts = []
            if username:
                parts.append(username)
            if points:
                parts.append(f"{points_label}:{points}")
            if level:
                parts.append(level)
            result["status"] = f"✅ {' | '.join(parts)}" if parts else "✅ 已登录（API检测）"
            result["display_name"] = username
        else:
            result["status"] = "❌ Cookie已失效（API检测）"
        
    except Exception as e:
        result["error"] = str(e)[:200]
        result["logged_in"] = False
        result["status"] = f"⚠️ API检测异常: {str(e)[:80]}"
    
    return result


def detect_csdn(cookie_str: str) -> dict:
    """
    CSDN API轻量检测
    用Cookie访问CSDN个人中心页面
    """
    result = {
        "logged_in": False,
        "method": "api_lightweight",
        "platform": "csdn",
        "site_url": "https://www.csdn.net",
    }
    
    if not cookie_str:
        return result
    
    try:
        sess = _make_session()
        for name, value in _parse_cookie_header(cookie_str).items():
            sess.cookies.set(name, value)
        
        # CSDN个人主页（从Cookie或页面提取用户名）
        # 先检查是否登录 — 访问msg.csdn.net
        msg_resp = sess.get("https://msg.csdn.net/", timeout=15, allow_redirects=True)
        if "login" in msg_resp.url.lower():
            result["error"] = "重定向到登录页"
            return result
        
        # 访问CSDN个人主页获取用户信息
        resp = sess.get("https://www.csdn.net/", timeout=15, allow_redirects=True)
        html = resp.text
        
        # 提取用户名（在登录后的右上角）
        username = ""
        name_patterns = [
            r'"nickname"\s*[:=]\s*"([^"]+)"',
            r'"username"\s*[:=]\s*"([^"]+)"',
            r'<a[^>]*href="https://blog\.csdn\.net/([^"/]+)"[^>]*>([^<]+)',
            r'<span[^>]*class="[^"]*name[^"]*"[^>]*>([^<]+)',
            r'<a[^>]*class="[^"]*user[^"]*"[^>]*href="/([^"/]+)"',
        ]
        for pat in name_patterns:
            m = re.search(pat, html)
            if m:
                # If we got a href-based username (CSDN blog URL), use it
                if m.lastindex and m.lastindex >= 2 and m.group(2):
                    candidate = m.group(1).strip()
                    # href="/username" style is more reliable
                    if candidate and '/' not in candidate:
                        username = candidate
                else:
                    username = m.group(1).strip()
                if username and len(username) >= 2:
                    break
        
        # 如果从主页没拿到，从Cookie拿
        if not username:
            cookie_dict = _parse_cookie_header(cookie_str)
            for ck_name in ["UserName", "username", "login_name", "uname"]:
                if ck_name in cookie_dict:
                    from urllib.parse import unquote
                    username = unquote(cookie_dict[ck_name])
                    if username:
                        break
        
        # 提取积分/等级
        points = 0
        level = ""
        point_patterns = [
            r'(经验|积分|等级|粉丝)[：:>\s]*(\d[\d,.]*)',
            r'"score"\s*[:=]\s*(\d+)',
            r'"level"\s*[:=]\s*(\d+)',
            r'"rank"\s*[:=]\s*"?(\d+)"?',
        ]
        for pat in point_patterns:
            m = re.search(pat, html)
            if m:
                try:
                    points = int(m.group(2).replace(",", "")) if m.lastindex >= 2 else int(m.group(1))
                except ValueError:
                    pass
                break
        
        # 用博客主页获取更多信息
        if username:
            blog_resp = sess.get(f"https://blog.csdn.net/{username}", timeout=15)
            blog_html = blog_resp.text
            # 提取粉丝数
            fan_match = re.search(r'粉丝[：:>\s]*(\d[\d,.]*)', blog_html)
            if fan_match:
                try:
                    points = int(fan_match.group(1).replace(",", ""))
                    result["points_label"] = "粉丝"
                except ValueError:
                    pass
            
            # 提取等级
            lv_match = re.search(r'(等级|Lv\.?|级)[：:>\s]*(\d+)', blog_html, re.IGNORECASE)
            if lv_match:
                level = f"Lv.{lv_match.group(2)}"
        
        logged_in = bool(username)
        result["logged_in"] = logged_in
        result["username"] = username if username else ""
        result["display_name"] = username if username else ""
        result["points"] = points
        result["level"] = level if level else ""
        result["verified_at"] = datetime.now().isoformat()
        
        if logged_in:
            parts = [username]
            if points:
                parts.append(f"{result.get('points_label', '积分')}:{points}")
            if level:
                parts.append(level)
            result["status"] = f"✅ {' | '.join(parts)}" if parts else "✅ 已登录（API检测）"
        else:
            result["status"] = "❌ Cookie已失效（API检测）"
        
    except Exception as e:
        result["error"] = str(e)[:200]
        result["status"] = f"⚠️ API检测异常: {str(e)[:80]}"
    
    return result


def detect_oshwhub(cookie_str: str, username_hint: str = "") -> dict:
    """
    OSHWHub API轻量检测
    用Cookie访问立创开源硬件平台用户信息
    """
    result = {
        "logged_in": False,
        "method": "api_lightweight",
        "platform": "oshwhub",
        "site_url": "https://oshwhub.com",
    }
    
    if not cookie_str:
        return result
    
    try:
        sess = _make_session()
        for name, value in _parse_cookie_header(cookie_str).items():
            sess.cookies.set(name, value)
        
        # OSHWHub 主页 — 检查登录状态
        resp = sess.get("https://oshwhub.com/", timeout=15, allow_redirects=True)
        html = resp.text
        
        # 检查是否已登录: 查找右上角用户信息
        username = ""
        name_patterns = [
            r'"nickname"\s*:\s*"([^"]+)"',
            r'"username"\s*:\s*"([^"]+)"',
            r'<span[^>]*class="[^"]*user[^"]*"[^>]*>\s*([\u4e00-\u9fff\w]+)',
            r'<a[^>]*href="/[^"]*"[^>]*>([\u4e00-\u9fff\w]+)</a>',
        ]
        for pat in name_patterns:
            m = re.search(pat, html)
            if m:
                username = m.group(1).strip()
                if username and len(username) >= 2:
                    break
        
        # 从Cookie提取
        if not username:
            cookie_dict = _parse_cookie_header(cookie_str)
            for ck_name in ["user_name", "username", "nickname", "uname"]:
                if ck_name in cookie_dict:
                    from urllib.parse import unquote
                    username = unquote(cookie_dict[ck_name])
                    if username:
                        break
        
        if not username:
            username = username_hint
        
        # 检查是否有退出/登录菜单
        has_logout = bool(re.search(r'退出|注销|logout|sign.*out', html, re.IGNORECASE))
        
        # 尝试访问用户设置页面
        points = 0
        level = ""
        if username:
            try:
                profile_resp = sess.get(f"https://oshwhub.com/{username}", timeout=15)
                profile_html = profile_resp.text
                
                point_patterns = [
                    r'(积分|经验|贡献)[：:>\s]*(\d[\d,.]*)',
                    r'"score"\s*[:=]\s*(\d+)',
                    r'"points"\s*[:=]\s*(\d+)',
                ]
                for pat in point_patterns:
                    m = re.search(pat, profile_html)
                    if m:
                        try:
                            val = m.group(2).replace(",", "") if m.lastindex >= 2 else m.group(1)
                            points = int(val)
                        except ValueError:
                            pass
                        break
            except Exception:
                pass
        
        logged_in = has_logout or bool(username)
        result["logged_in"] = logged_in
        result["username"] = username
        result["display_name"] = username
        result["points"] = points
        result["points_label"] = "积分"
        result["level"] = level
        result["verified_at"] = datetime.now().isoformat()
        
        if logged_in:
            parts = [username] if username else []
            if points:
                parts.append(f"积分:{points}")
            if level:
                parts.append(level)
            result["status"] = f"✅ {' | '.join(parts)}" if parts else "✅ 已登录（API检测）"
        else:
            result["status"] = "❌ Cookie已失效（API检测）"
        
    except Exception as e:
        result["error"] = str(e)[:200]
        result["status"] = f"⚠️ API检测异常: {str(e)[:80]}"
    
    return result


def detect_xianyu(cookie_str: str) -> dict:
    """
    闲鱼 API轻量检测
    用Cookie访问闲鱼主页/用户信息
    """
    result = {
        "logged_in": False,
        "method": "api_lightweight",
        "platform": "xianyu",
        "site_url": "https://goofish.com",
    }
    
    if not cookie_str:
        return result
    
    try:
        sess = _make_session()
        for name, value in _parse_cookie_header(cookie_str).items():
            sess.cookies.set(name, value)
        
        # 访问goofish.com检查登录状态
        resp = sess.get("https://goofish.com/", timeout=15, allow_redirects=True)
        html = resp.text
        
        username = ""
        name_patterns = [
            r'"nick"\s*:\s*"([^"]+)"',
            r'"nickName"\s*:\s*"([^"]+)"',
            r'"userName"\s*:\s*"([^"]+)"',
            r'<span[^>]*class="[^"]*nick[^"]*"[^>]*>([^<]+)',
        ]
        for pat in name_patterns:
            m = re.search(pat, html)
            if m:
                username = m.group(1).strip()
                if username and len(username) >= 2:
                    break
        
        has_logout = bool(re.search(r'退出|注销|logout', html, re.IGNORECASE))
        
        logged_in = has_logout or bool(username)
        result["logged_in"] = logged_in
        result["username"] = username if username else ""
        result["display_name"] = username if username else ""
        result["verified_at"] = datetime.now().isoformat()
        
        if logged_in:
            result["status"] = f"✅ {username}（API检测）" if username else "✅ 已登录（API检测）"
        else:
            result["status"] = "❌ Cookie已失效（API检测）"
        
    except Exception as e:
        result["error"] = str(e)[:200]
        result["status"] = f"⚠️ API检测异常: {str(e)[:80]}"
    
    return result


# 检测器注册表
PLATFORM_DETECTORS = {
    "discuz": detect_discuz,
    "csdn": detect_csdn,
    "oshwhub": detect_oshwhub,
    "xianyu": detect_xianyu,
    # 遗留/别名
    "discuz_amobbs": detect_discuz,
    "discuz_mydigit": detect_discuz,
}


def detect_platform(platform: str, site_url: str, cookie_str: str, username_hint: str = "") -> dict:
    """
    通用平台检测入口 — 根据平台类型选择合适的检测器
    返回统一格式的检测结果
    """
    detector = PLATFORM_DETECTORS.get(platform)
    if detector:
        if platform == "discuz":
            return detect_discuz(site_url, cookie_str, platform)
        elif platform == "csdn":
            return detect_csdn(cookie_str)
        elif platform == "oshwhub":
            return detect_oshwhub(cookie_str, username_hint)
        elif platform == "xianyu":
            return detect_xianyu(cookie_str)
        else:
            return detector(site_url, cookie_str)
    
    # 未知平台，返回空结果
    return {
        "logged_in": False,
        "method": "api_lightweight",
        "platform": platform,
        "status": "⚠️ 该平台暂无轻量检测支持",
    }
