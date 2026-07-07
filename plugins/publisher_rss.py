"""
RSS Publisher — 生成标准 RSS 2.0 / Atom 订阅源
零依赖，纯 Python 标准库
"""
import os, xml.etree.ElementTree as ET
from datetime import datetime
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register


@register
class RSSPublisher(Publisher):
    name = "rss"
    display_name = "RSS 订阅"
    architecture = ""
    login_methods = []  # 无需登录，纯本地生成
    config_fields = [
        {"key": "output_path", "label": "输出路径", "type": "text", "default": "blog/docs/feed.xml"},
        {"key": "title", "label": "站点标题", "type": "text", "required": True},
        {"key": "description", "label": "站点描述", "type": "text"},
        {"key": "link", "label": "站点链接", "type": "text", "required": True},
        {"key": "max_items", "label": "最大条数", "type": "number", "default": 20},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.output_path = config.get("output_path", "blog/docs/feed.xml")
        self.site_title = config.get("title", "FlashSloth Blog")
        self.site_desc = config.get("description", "")
        self.site_link = config.get("link", "https://example.com")
        self.max_items = int(config.get("max_items", 20))

    def publish(self, article: Article, **kwargs) -> dict:
        """追加单篇文章到 RSS（或重新生成全部）"""
        # RSS 是批量生成，单篇发布需要缓存
        return self._generate_feed([article])

    def generate_feed(self, articles: list[Article]) -> str:
        """生成完整 RSS XML"""
        rss = ET.Element("rss", version="2.0",
                         attrib={"xmlns:atom": "http://www.w3.org/2005/Atom"})
        channel = ET.SubElement(rss, "channel")

        ET.SubElement(channel, "title").text = self.site_title
        ET.SubElement(channel, "link").text = self.site_link
        ET.SubElement(channel, "description").text = self.site_desc
        ET.SubElement(channel, "language").text = "zh-CN"
        ET.SubElement(channel, "generator").text = "FlashSloth"

        atom_link = ET.SubElement(channel, "atom:link")
        atom_link.set("href", f"{self.site_link}/feed.xml")
        atom_link.set("rel", "self")
        atom_link.set("type", "application/rss+xml")

        for a in articles[:self.max_items]:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = a.title
            ET.SubElement(item, "link").text = f"{self.site_link}/posts/{a.slug or ''}"
            ET.SubElement(item, "description").text = a.summary or a.body[:200]
            ET.SubElement(item, "pubDate").text = self._rss_date(a.date)
            ET.SubElement(item, "guid", isPermaLink="false").text = a.slug or a.title
            for tag in a.tags:
                ET.SubElement(item, "category").text = tag

        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")

    def _generate_feed(self, articles: list[Article]) -> dict:
        try:
            xml = self.generate_feed(articles)
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(xml)
            return {"success": True, "url": f"{self.site_link}/feed.xml",
                    "id": "rss", "error": ""}
        except Exception as e:
            return {"success": False, "error": f"RSS 生成失败: {e}", "url": "", "id": ""}

    @staticmethod
    def _rss_date(date_str: str | None) -> str:
        """转 RSS 日期格式"""
        if not date_str:
            return datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0800")
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%a, %d %b %Y %H:%M:%S +0800")
        except Exception:
            return datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0800")
