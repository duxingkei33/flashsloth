"""
AI逛论坛 — FlashSloth 插件
自动登录配置的论坛账号，抓取新帖子，AI 筛选推荐
使用人机浏览器模拟，避免反爬
"""
import re, json, time
from datetime import datetime, timedelta
from html import unescape
from typing import Optional

from flashsloth.plugins.browser_session import HumanSession

# ─── Discuz! 论坛抓取器 ─────────────────────────

class DiscuzForumReader:
    """读取 Discuz! 论坛帖子列表和详情"""

    def __init__(self, site_url: str, cookies: str = "", username: str = "", password: str = ""):
        self.site_url = site_url.rstrip("/")
        self.browser = HumanSession(base_url=site_url, min_delay=0.5, max_delay=2.0)
        if cookies:
            self.browser.set_cookies(cookies)
        self.username = username
        self.password = password

    def _get_domain(self) -> str:
        return self.site_url.replace("https://", "").replace("http://", "").split("/")[0]

    def is_logged_in(self) -> bool:
        """检查登录状态"""
        try:
            r = self.browser.get("/home.php?mod=space&do=profile")
            if self.username and self.username in r.text:
                return True
            for c in self.browser.session.cookies:
                if "auth" in c.name.lower():
                    return True
            return "login" not in r.url.lower()
        except:
            return False

    def get_forum_list(self) -> list[dict]:
        """获取板块列表"""
        try:
            r = self.browser.get("/forum.php")
            forums = []
            # 标准 Discuz! 格式
            pat1 = re.compile(r'<a[^>]*href="forum\.php\?mod=forumdisplay&fid=(\d+)"[^>]*>([^<]+)</a>')
            for m in pat1.finditer(r.text):
                fid, name = m.group(1), unescape(m.group(2)).strip()
                if fid not in [f["fid"] for f in forums]:
                    forums.append({"fid": fid, "name": name})
            # 兼容 mydigit.cn 格式
            pat2 = re.compile(r'forum-(\d+)-1\.html[^>]*>([^<]+)</a>')
            for m in pat2.finditer(r.text):
                fid, name = m.group(1), unescape(m.group(2)).strip()
                if fid not in [f["fid"] for f in forums]:
                    forums.append({"fid": fid, "name": name})
            return forums
        except Exception as e:
            return []

    def get_new_threads(self, fid: str, hours: int = 24, max_pages: int = 3) -> list[dict]:
        """获取指定板块的新帖子"""
        threads = []
        for page in range(1, max_pages + 1):
            try:
                url = f"/forum.php?mod=forumdisplay&fid={fid}&page={page}&orderby=dateline"
                r = self.browser.get(url)

                # 格式1: viewthread&tid=123 (标准 Discuz!)
                for m in re.finditer(
                    r'href="[^"]*viewthread[^"]*tid=(\d+)"[^>]*>(.*?)</a>',
                    r.text, re.DOTALL
                ):
                    tid = m.group(1)
                    title = unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
                    if not title or title in ["", "&nbsp;"]:
                        continue
                    if any(t["tid"] == tid for t in threads):
                        continue
                    title = re.sub(r'<span[^>]*>.*?</span>', '', title).strip()
                    if not title:
                        continue
                    threads.append({
                        "tid": tid, "title": title,
                        "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                        "fid": fid,
                    })

                # 格式2: thread-123-1-1.html (mydigit.cn — 标题在 <a> 内)
                for m2 in re.finditer(
                    r'href="thread-(\d+)-1-1\.html"[^>]*>(.*?)</a>',
                    r.text, re.DOTALL
                ):
                    tid = m2.group(1)
                    title = unescape(re.sub(r"<[^>]+>", "", m2.group(2))).strip()
                    if not title or len(title) < 3 or title in ["", "&nbsp;"]:
                        continue
                    if any(skip in title.lower() for skip in ["关于我们", "联系我们", "法律条款"]):
                        continue
                    title = re.sub(r'<span[^>]*>.*?</span>', '', title).strip()
                    if not title or any(t["tid"] == tid for t in threads):
                        continue
                    threads.append({
                        "tid": tid, "title": title,
                        "url": f"{self.site_url}/thread-{tid}-1-1.html",
                        "fid": fid,
                    })

                # 格式3: 兼容旧版 class=s xst
                for m3 in re.finditer(
                    r'<span[^>]*class="s xst"[^>]*>(.*?)</span>',
                    r.text, re.DOTALL
                ):
                    title = unescape(m3.group(1)).strip()
                    if not title or len(title) < 3:
                        continue
                    start = max(0, m3.start() - 400)
                    snippet = r.text[start:m3.start()]
                    tid_m = re.search(r'thread-(\d+)-\d+-\d+\.html', snippet)
                    if not tid_m:
                        tid_m = re.search(r'tid=(\d+)', snippet)
                    if not tid_m or any(t["tid"] == tid_m.group(1) for t in threads):
                        continue
                    tid = tid_m.group(1)
                    threads.append({
                        "tid": tid, "title": title,
                        "url": f"{self.site_url}/thread-{tid}-1-1.html",
                        "fid": fid,
                    })

                if "next" not in r.text and "下一页" not in r.text:
                    break
            except:
                break

        return threads

    def get_thread_detail(self, tid: str) -> Optional[dict]:
        """获取帖子详情（首帖内容）"""
        try:
            r = self.browser.get(f"/forum.php?mod=viewthread&tid={tid}")
            content = ""
            for pattern in [
                r'<td[^>]*class="t_f"[^>]*>(.*?)</td>',
                r'<div[^>]*class="t_fsz"[^>]*>(.*?)</div>',
                r'<div[^>]*class="postmessage"[^>]*>(.*?)</div>',
            ]:
                m = re.search(pattern, r.text, re.DOTALL)
                if m:
                    content = unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip()
                    content = re.sub(r"\s+", " ", content)[:2000]
                    break

            author = ""
            for pattern in [
                r'<a[^>]*class="xw1"[^>]*>([^<]+)</a>',
            ]:
                m = re.search(pattern, r.text)
                if m:
                    author = unescape(m.group(1)).strip()
                    break

            return {
                "tid": tid,
                "content": content or "(无法提取内容)",
                "author": author or "未知",
            }
        except:
            return None

    def get_replies_to_my_threads(self, my_thread_tids: list[str], max_pages: int = 2) -> list[dict]:
        """检查我发的帖子的最新回复"""
        replies = []
        for tid in my_thread_tids:
            try:
                r = self.browser.get(f"/forum.php?mod=viewthread&tid={tid}")
                post_divs = re.findall(
                    r'<div[^>]*class="plc"[^>]*>(.*?)</div>\s*</div>',
                    r.text, re.DOTALL
                )
                for i, div in enumerate(post_divs):
                    if i == 0:
                        continue
                    reply_author = ""
                    m = re.search(r'<a[^>]*class="xw1"[^>]*>([^<]+)</a>', div)
                    if m:
                        reply_author = unescape(m.group(1)).strip()
                    reply_content = re.sub(r"<[^>]+>", " ", div)[:500].strip()
                    if reply_author != self.username:
                        replies.append({
                            "thread_tid": tid,
                            "author": reply_author,
                            "content": reply_content[:300],
                            "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                        })
            except:
                continue
        return replies


# ─── AI 筛选引擎 ────────────────────────────────

class InterestFilter:
    """基于关键词的帖子筛选引擎"""

    def __init__(self, interesting_tags: list[str] = None):
        self.interesting_tags = interesting_tags or [
            "AI", "大模型", "嵌入式", "ESP32", "单片机", "MCU",
            "开源", "硬件", "电子", "DIY", "Python", "C++",
            "Linux", "树莓派", "传感器", "物联网", "IoT",
            "Arduino", "机器人", "无人机", "飞控",
            "电源", "充电", "电池", "BMS", "锂电池",
            "PCB", "layout", "原理图", "电路", "芯片",
            "STM32", "RISC-V", "ARM", "FPGA",
        ]

    def score_by_keywords(self, title: str, content: str = "") -> tuple[int, list[str]]:
        text = (title + " " + content).lower()
        hits = []
        for tag in self.interesting_tags:
            if tag.lower() in text:
                hits.append(tag)
        title_hits = [t for t in hits if t.lower() in title.lower()]
        score = len(hits) * 5 + len(title_hits) * 10
        return score, hits

    def filter_threads(self, threads: list[dict]) -> list[dict]:
        results = []
        for t in threads:
            score, tags = self.score_by_keywords(t.get("title", ""), t.get("content", ""))
            if score >= 10:
                results.append({
                    **t,
                    "ai_score": score,
                    "ai_tags": tags,
                    "ai_summary": f"[{', '.join(tags[:3])}] {t.get('title', '')}",
                })
        results.sort(key=lambda x: x["ai_score"], reverse=True)
        return results
