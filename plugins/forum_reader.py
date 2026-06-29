"""
AI逛论坛 — FlashSloth 插件
自动登录配置的论坛账号，抓取新帖子，AI 筛选推荐
"""
import re, requests, json, time, hashlib
from datetime import datetime, timedelta
from html import unescape
from typing import Optional

# ─── Discuz! 论坛抓取器 ─────────────────────────

class DiscuzForumReader:
    """读取 Discuz! 论坛帖子列表和详情"""

    def __init__(self, site_url: str, cookies: str = "", username: str = "", password: str = ""):
        self.site_url = site_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
        })
        self._parse_cookies(cookies)
        self.username = username
        self.password = password

    def _parse_cookies(self, cookie_str: str):
        if not cookie_str:
            return
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                domain = self.site_url.replace("https://", "").replace("http://", "").split("/")[0]
                self.session.cookies.set(k.strip(), v.strip(), domain=domain)

    def _get_domain(self) -> str:
        return self.site_url.replace("https://", "").replace("http://", "").split("/")[0]

    def is_logged_in(self) -> bool:
        """检查登录状态"""
        try:
            r = self.session.get(f"{self.site_url}/home.php?mod=space&do=profile", timeout=10)
            if self.username and self.username in r.text:
                return True
            for c in self.session.cookies:
                if "auth" in c.name.lower():
                    return True
            return "login" not in r.url.lower()
        except:
            return False

    def get_forum_list(self) -> list[dict]:
        """获取板块列表"""
        try:
            r = self.session.get(f"{self.site_url}/forum.php", timeout=15)
            forums = []
            # 标准 Discuz! 格式: forum.php?mod=forumdisplay&fid=X
            pat1 = re.compile(r'<a[^>]*href="forum\.php\?mod=forumdisplay&fid=(\d+)"[^>]*>([^<]+)</a>')
            for m in pat1.finditer(r.text):
                fid, name = m.group(1), unescape(m.group(2)).strip()
                if fid not in [f["fid"] for f in forums]:
                    forums.append({"fid": fid, "name": name})
            # 兼容格式: forum-X-1.html (mydigit.cn 等)
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
        cutoff = datetime.now() - timedelta(hours=hours)

        for page in range(1, max_pages + 1):
            try:
                url = f"{self.site_url}/forum.php?mod=forumdisplay&fid={fid}&page={page}&orderby=dateline"
                r = self.session.get(url, timeout=15)

                # 解析帖子列表 — 多种格式兼容
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
                        "tid": tid,
                        "title": title,
                        "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                        "fid": fid,
                    })

                # 格式2: thread-123-1-1.html (mydigit.cn 等)
                for m2 in re.finditer(
                    r'<span[^>]*class="s xst"[^>]*>(.*?)</span>',
                    r.text, re.DOTALL
                ):
                    title = unescape(m2.group(1)).strip()
                    if not title or len(title) < 3:
                        continue
                    # Look for thread-X URL before this span
                    start = max(0, m2.start() - 400)
                    snippet = r.text[start:m2.start()]
                    tid_m = re.search(r'thread-(\d+)-\d+-\d+\.html', snippet)
                    if not tid_m:
                        tid_m = re.search(r'tid=(\d+)', snippet)
                    if not tid_m:
                        continue
                    tid = tid_m.group(1)
                    if any(t["tid"] == tid for t in threads):
                        continue
                    threads.append({
                        "tid": tid,
                        "title": title,
                        "url": f"{self.site_url}/thread-{tid}-1-1.html",
                        "fid": fid,
                    })

                # 检查是否有下一页
                if "next" not in r.text and "下一页" not in r.text:
                    break
            except:
                break

        return threads

    def get_thread_detail(self, tid: str) -> Optional[dict]:
        """获取帖子详情（首帖内容）"""
        try:
            r = self.session.get(
                f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                timeout=15
            )
            # 提取正文
            content = ""
            for pattern in [
                r'<td[^>]*class="t_f"[^>]*>([\\s\\S]*?)</td>',
                r'<div[^>]*class="t_fsz"[^>]*>([\\s\\S]*?)</div>',
                r'<div[^>]*class="postmessage"[^>]*>([\\s\\S]*?)</div>',
            ]:
                m = re.search(pattern, r.text, re.DOTALL)
                if m:
                    content = unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip()
                    content = re.sub(r"\s+", " ", content)[:2000]
                    break

            # 提取作者
            author = ""
            for pattern in [
                r'<a[^>]*class="xw1"[^>]*>([^<]+)</a>',
                r'<div[^>]*class="authi"[^>]*>([\\s\\S]*?)<',
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
        except Exception as e:
            return None

    def get_replies_to_my_threads(self, my_thread_tids: list[str], max_pages: int = 2) -> list[dict]:
        """检查我发的帖子的最新回复"""
        replies = []
        for tid in my_thread_tids:
            try:
                r = self.session.get(
                    f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                    timeout=15
                )
                # 提取回复列表
                post_divs = re.findall(
                    r'<div[^>]*class="plc"[^>]*>([\\s\\S]*?)</div>\s*</div>',
                    r.text, re.DOTALL
                )
                for i, div in enumerate(post_divs):
                    if i == 0:  # 跳过首帖
                        continue
                    reply_author = ""
                    m = re.search(r'<a[^>]*class="xw1"[^>]*>([^<]+)</a>', div)
                    if m:
                        reply_author = unescape(m.group(1)).strip()
                    reply_content = re.sub(r"<[^>]+>", " ", div)[:500].strip()
                    if reply_author != self.username:  # 不是自己的回复
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
    """基于关键词和 LLM 的帖子筛选引擎"""

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
        """关键词打分，返回 (分数, 匹配关键词)"""
        text = (title + " " + content).lower()
        hits = []
        for tag in self.interesting_tags:
            if tag.lower() in text:
                hits.append(tag)
        # 标题命中权重高
        title_hits = [t for t in hits if t.lower() in title.lower()]
        score = len(hits) * 5 + len(title_hits) * 10
        return score, hits

    def filter_threads(self, threads: list[dict]) -> list[dict]:
        """筛选帖子，附加 AI 评分"""
        results = []
        for t in threads:
            score, tags = self.score_by_keywords(t.get("title", ""), t.get("content", ""))
            if score >= 10:  # 至少命中一个重要关键词或在标题中命中
                results.append({
                    **t,
                    "ai_score": score,
                    "ai_tags": tags,
                    "ai_summary": f"[{', '.join(tags[:3])}] {t.get('title', '')}",
                })
        # 按分数排序
        results.sort(key=lambda x: x["ai_score"], reverse=True)
        return results
