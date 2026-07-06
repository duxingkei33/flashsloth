"""
Compiler Engine — FlashSloth 中央编译器

输入: 源 Article + 目标平台列表
处理: 1. 解析源文 → 中间表示(IR)
      2. 按各平台规则 → 编译产物
输出: {platform: CompiledContent}

整个流程：
  Article
    → parse_source()     解析 Markdown 为结构化 IR
    → apply_rules()      对各平台应用编译规则
      → image_pipeline() 图片提取/压缩/上传准备
      → format_body()    格式转换 (Markdown→BBcode/HTML/etc)
      → validate()       检查是否满足平台限制
    → 输出 CompiledContent 列表（可预览）
"""
import re
import os
from dataclasses import dataclass, field
from typing import Optional
try:
    from flashsloth.core.article import Article as SourceArticle
except ImportError:
    from core.article import Article as SourceArticle


# ═══════════════════════════════════════════════
# 中间表示 (Intermediate Representation)
# ═══════════════════════════════════════════════

@dataclass
class IRBlock:
    """IR 中的一个块"""
    type: str  # heading | paragraph | code_block | image | list | table | quote | hr
    content: str = ""
    level: int = 0           # heading level, list nesting
    language: str = ""       # code block language
    items: list = field(default_factory=list)  # for list items
    rows: list = field(default_factory=list)   # for table rows
    alt: str = ""            # image alt text
    src: str = ""            # image source URL
    width: int = 0
    height: int = 0


@dataclass
class IRDocument:
    """完整的中间表示文档"""
    title: str = ""
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    blocks: list[IRBlock] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)  # [{"src": "...", "alt": "..."}]
    original_body: str = ""


# ═══════════════════════════════════════════════
# 编译产物
# ═══════════════════════════════════════════════

@dataclass
class CompiledContent:
    """一个平台编译完成的结果"""
    platform: str
    display_name: str
    title: str
    body: str                       # 目标平台格式的正文
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)  # 上传后的图片信息
    image_warnings: list[str] = field(default_factory=list)
    fields: dict = field(default_factory=dict)  # 额外字段 (fid, article_type...)
    warnings: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""


# ═══════════════════════════════════════════════
# Markdown → IR 解析器
# ═══════════════════════════════════════════════

class MarkdownParser:
    """将 Markdown 正文解析为 IRDocument"""

    @staticmethod
    def parse(body: str) -> IRDocument:
        doc = IRDocument(original_body=body)
        lines = body.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 跳过空行
            if not stripped:
                i += 1
                continue

            # 标题
            heading = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading:
                doc.blocks.append(IRBlock(
                    type="heading",
                    content=heading.group(2).strip(),
                    level=len(heading.group(1))
                ))
                i += 1
                continue

            # 代码块
            code_match = re.match(r'^```(\w*)', stripped)
            if code_match:
                lang = code_match.group(1)
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # skip closing ```
                doc.blocks.append(IRBlock(
                    type="code_block",
                    content="\n".join(code_lines),
                    language=lang
                ))
                continue

            # 分割线
            if re.match(r'^---+\s*$', stripped) or re.match(r'^\*\*\*+\s*$', stripped):
                doc.blocks.append(IRBlock(type="hr"))
                i += 1
                continue

            # 引用
            if stripped.startswith("> "):
                quote_lines = []
                while i < len(lines) and lines[i].strip().startswith("> "):
                    quote_lines.append(lines[i].strip()[2:])
                    i += 1
                doc.blocks.append(IRBlock(type="quote", content="\n".join(quote_lines)))
                continue

            # 无序列表
            if re.match(r'^[-*+]\s+', stripped):
                items = []
                while i < len(lines):
                    m = re.match(r'^[-*+]\s+(.*)', lines[i].strip())
                    if not m:
                        break
                    items.append(m.group(1))
                    i += 1
                doc.blocks.append(IRBlock(type="list", items=items, level=0))
                continue

            # 有序列表
            if re.match(r'^\d+\.\s+', stripped):
                items = []
                while i < len(lines):
                    m = re.match(r'^\d+\.\s+(.*)', lines[i].strip())
                    if not m:
                        break
                    items.append(m.group(1))
                    i += 1
                doc.blocks.append(IRBlock(type="list", items=items, level=0))
                continue

            # 表格
            if "|" in stripped and i + 1 < len(lines) and re.match(r'^[\s\|:\-]+$', lines[i+1].strip()):
                rows = []
                while i < len(lines) and "|" in lines[i]:
                    cells = [c.strip() for c in lines[i].split("|") if c.strip()]
                    if cells:
                        rows.append(cells)
                    i += 1
                doc.blocks.append(IRBlock(type="table", rows=rows))
                continue

            # 图片
            images_in_line = list(re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', stripped))
            if images_in_line:
                # 如果整行就是一张图片
                if len(images_in_line) == 1 and not re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', '', stripped).strip():
                    m = images_in_line[0]
                    alt = m.group(1)
                    src = m.group(2)
                    doc.images.append({"src": src, "alt": alt})
                    doc.blocks.append(IRBlock(type="image", alt=alt, src=src))
                    i += 1
                    continue

            # 普通段落（含行内图片、链接、粗体等）
            para_lines = []
            while i < len(lines):
                s = lines[i].strip()
                if not s:
                    break
                # 遇到标题/代码/列表等结构块则停止
                if re.match(r'^(#{1,6}\s|```|---|\*{3,}|[-*+]\s|\d+\.\s|>\s|\|)', s):
                    break
                # 提取行内图片
                for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', s):
                    doc.images.append({"src": m.group(2), "alt": m.group(1)})
                para_lines.append(s)
                i += 1

            if para_lines:
                doc.blocks.append(IRBlock(type="paragraph", content="\n".join(para_lines)))
                continue

            i += 1

        return doc


# ═══════════════════════════════════════════════
# 格式转换器
# ═══════════════════════════════════════════════

class FormatConverter:
    """IR → 目标平台格式"""

    @staticmethod
    def to_bbcode(ir: IRDocument) -> str:
        """IR → Discuz! BBCode"""
        parts = []
        for block in ir.blocks:
            if block.type == "heading":
                # Discuz 用 [size] 模拟标题
                sizes = {1: 7, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2}
                sz = sizes.get(block.level, 4)
                parts.append(f"[size={sz}][b]{block.content}[/b][/size]\n")
            elif block.type == "paragraph":
                text = block.content
                # 转行内样式
                text = re.sub(r'\*\*(.+?)\*\*', r'[b]\1[/b]', text)
                text = re.sub(r'\*(.+?)\*', r'[i]\1[/i]', text)
                text = re.sub(r'`([^`]+)`', r'[font=monospace]\1[/font]', text)
                # 链接
                text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'[url=\2]\1[/url]', text)
                # 图片（保留原始引用，后续由图片上传管线处理）
                text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'[img]\2[/img]', text)
                parts.append(text + "\n\n")
            elif block.type == "code_block":
                parts.append(f"[code]\n{block.content}\n[/code]\n\n")
            elif block.type == "image":
                parts.append(f"[img]{block.src}[/img]\n\n")
            elif block.type == "list":
                for item in block.items:
                    parts.append(f"[*]{item}\n")
                parts.append("\n")
            elif block.type == "quote":
                lines = block.content.split("\n")
                for line in lines:
                    parts.append(f"[quote]{line}[/quote]\n")
                parts.append("\n")
            elif block.type == "table":
                for row in block.rows:
                    parts.append("| " + " | ".join(row) + " |\n")
                parts.append("\n")
            elif block.type == "hr":
                parts.append("---\n\n")
        return "".join(parts)

    @staticmethod
    def to_plain_text(ir: IRDocument) -> str:
        """IR → 纯文本（Twitter/YouTube 用）"""
        parts = []
        for block in ir.blocks:
            if block.type == "heading":
                parts.append(f"{block.content}\n\n")
            elif block.type == "paragraph":
                text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'\1', block.content)
                text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
                text = re.sub(r'\*(.+?)\*', r'\1', text)
                text = re.sub(r'`([^`]+)`', r'\1', text)
                parts.append(f"{text}\n\n")
            elif block.type == "image":
                parts.append(f"[图片: {block.alt or block.src}]\n\n")
            elif block.type == "code_block" and block.language:
                parts.append(f"[代码: {block.language}]\n{block.content}\n\n")
            else:
                parts.append(f"{block.content}\n\n")
        return "".join(parts).strip()

    @staticmethod
    def to_html(ir: IRDocument) -> str:
        """IR → HTML"""
        parts = []
        for block in ir.blocks:
            if block.type == "heading":
                tag = f"h{min(block.level, 6)}"
                parts.append(f"<{tag}>{block.content}</{tag}>\n")
            elif block.type == "paragraph":
                text = block.content
                text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
                text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
                text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
                text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
                text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',
                              r'<img src="\2" alt="\1" style="max-width:100%">', text)
                parts.append(f"<p>{text}</p>\n")
            elif block.type == "code_block":
                lang = f' class="language-{block.language}"' if block.language else ""
                parts.append(f"<pre><code{lang}>{block.content}</code></pre>\n")
            elif block.type == "image":
                parts.append(f'<img src="{block.src}" alt="{block.alt}">\n')
            elif block.type == "list":
                tag = "ul"
                parts.append(f"<{tag}>\n")
                for item in block.items:
                    parts.append(f"  <li>{item}</li>\n")
                parts.append(f"</{tag}>\n")
            elif block.type == "quote":
                parts.append(f"<blockquote>{block.content}</blockquote>\n")
            elif block.type == "table":
                parts.append("<table>\n")
                for i, row in enumerate(block.rows):
                    tag = "th" if i == 0 else "td"
                    parts.append(f"  <tr><{'><'.join([tag]*len(row))}>{'><'.join(row)}</{'></'.join([tag]*len(row))}></tr>\n")
                parts.append("</table>\n")
            elif block.type == "hr":
                parts.append("<hr>\n")
        return "".join(parts)

    @staticmethod
    def keep_markdown(ir: IRDocument) -> str:
        """保持 Markdown 原格式（CSDN/掘金/GitHub Pages）"""
        return ir.original_body


# ═══════════════════════════════════════════════
# 图片预处理管线
# ═══════════════════════════════════════════════

class ImagePipeline:
    """从源文中提取图片，做预处理"""

    @staticmethod
    def extract_images_from_markdown(body: str) -> list[dict]:
        """从 Markdown body 中提取所有图片引用"""
        images = []
        # Markdown 图片: ![alt](url)
        for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', body):
            images.append({"src": m.group(2), "alt": m.group(1), "type": "markdown"})
        # HTML img: <img src="..." alt="...">
        for m in re.finditer(r'<img[^>]*src="([^"]+)"[^>]*(?:alt="([^"]*)")?[^>]*>', body, re.IGNORECASE):
            images.append({"src": m.group(1), "alt": m.group(2) or "", "type": "html"})
        return images

    @staticmethod
    def resolve_local_path(src: str, base_dir: str = "") -> Optional[str]:
        """将图片引用解析为本地文件路径"""
        if src.startswith("http"):
            return None  # 远程图片，需下载
        if src.startswith("/static/uploads/"):
            rel = src[len("/static/uploads/"):]
            local = os.path.join(base_dir, "static", "uploads", rel)
            if os.path.isfile(local):
                return local
        if not src.startswith("/") and not src.startswith("http"):
            local = os.path.join(base_dir, "static", "uploads", os.path.basename(src))
            if os.path.isfile(local):
                return local
        return None

    @staticmethod
    def check_image_size(filepath: str, rule) -> list[str]:
        """检查图片是否符合平台限制，返回警告列表"""
        warnings = []
        try:
            from PIL import Image
            img = Image.open(filepath)
            w, h = img.size
            if rule.max_width and w > rule.max_width:
                warnings.append(f"图片宽度 {w}px 超过限制 {rule.max_width}px，将被压缩")
            if rule.max_height and h > rule.max_height:
                warnings.append(f"图片高度 {h}px 超过限制 {rule.max_height}px，将被压缩")
            if rule.max_size_mb:
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                if size_mb > rule.max_size_mb:
                    warnings.append(f"图片大小 {size_mb:.1f}MB 超过限制 {rule.max_size_mb}MB，将被压缩")
        except ImportError:
            pass  # PIL not available
        except Exception:
            pass
        return warnings


# ═══════════════════════════════════════════════
# Compiler Engine 主类
# ═══════════════════════════════════════════════

class Compiler:
    """
    中央编译器。使用方式:

    compiler = Compiler()
    article = Article(title="...", body="...")
    results = compiler.compile(article, targets=["discuz", "csdn"])

    # 预览任意平台的编译效果
    discuz_content = results["discuz"].body
    """

    def __init__(self):
        try:
            from flashsloth.core.compile_rule import get_rule, list_rules
        except ImportError:
            from core.compile_rule import get_rule, list_rules
        self._rules = {r.platform: r for r in list_rules()}

    def compile(self, source: SourceArticle,
                targets: Optional[list[str]] = None,
                base_dir: str = "") -> dict[str, CompiledContent]:
        """
        编译源文章到指定目标平台。

        参数:
            source: 源 Article 对象
            targets: 目标平台列表 (None = 所有已注册平台)
            base_dir: 项目根目录（用于解析本地图片路径）

        返回: {platform_name: CompiledContent}
        """
        if not targets:
            targets = list(self._rules.keys())

        # 1. 解析为 IR
        ir = MarkdownParser.parse(source.body)
        ir.title = source.title
        ir.tags = source.tags or []
        ir.summary = source.summary or ""

        # 2. 提取所有图片
        all_images = ImagePipeline.extract_images_from_markdown(source.body)

        results = {}
        for platform in targets:
            rule = self._rules.get(platform)
            if not rule:
                results[platform] = CompiledContent(
                    platform=platform, display_name=platform,
                    title=source.title, body=source.body,
                    success=False, error=f"未找到平台 {platform} 的编译规则"
                )
                continue

            warnings = []
            image_warnings = []

            # 3. 图片检查（对每个平台）
            for img in all_images:
                local_path = ImagePipeline.resolve_local_path(img["src"], base_dir)
                if local_path:
                    iw = ImagePipeline.check_image_size(local_path, rule.image)
                    image_warnings.extend(iw)

            # 4. 格式转换
            body_format = rule.body.format_type
            if body_format == "bbcode":
                converted_body = FormatConverter.to_bbcode(ir)
            elif body_format == "html":
                converted_body = FormatConverter.to_html(ir)
            elif body_format == "markdown":
                converted_body = FormatConverter.keep_markdown(ir)
            elif body_format == "richtext":
                converted_body = FormatConverter.to_html(ir)
            elif body_format == "text":
                converted_body = FormatConverter.to_plain_text(ir)
            else:
                converted_body = ir.original_body

            # 5. 标题截断
            title = source.title or ""
            if rule.max_title_length and len(title) > rule.max_title_length:
                title = title[:rule.max_title_length - 3] + "..."
                warnings.append(f"标题已截断到 {rule.max_title_length} 字符")

            # 6. 正文截断
            if body_format == "text":
                max_body = 4000  # Twitter 限制
                if len(converted_body) > max_body:
                    converted_body = converted_body[:max_body - 3] + "..."
                    warnings.append(f"正文已截断到 {max_body} 字符")

            # 7. 构建 fields
            fields = {}
            for f in rule.fields:
                if f.field_type == "select":
                    pass  # 由发布时用户选择
                elif f.field_name == "title":
                    fields[f.field_name] = title
                elif f.field_name in ("content", "message", "body"):
                    fields[f.field_name] = converted_body

            # 🔥 智能版块/分类匹配：支持所有平台
            if "fid" not in fields and "type_id" not in fields:
                try:
                    from flashsloth.core.forum_registry import (
                        match_forum, get_forum_name, match_platform_type
                    )
                    
                    # 平台 → 域名映射
                    domain_map = {
                        "discuz_amobbs": "amobbs.com",
                        "discuz_mydigit": "mydigit.cn",
                        "discuz": None,  # 未知 Discuz → 由上层指定
                        "oshwhub": "oshwhub.com",
                        "csdn": "csdn.net",
                    }
                    
                    domain = domain_map.get(platform)
                    
                    # 如果是 Discuz 论坛 → 匹配 FID
                    if domain in ("amobbs.com", "mydigit.cn"):
                        fid = match_forum(domain, ir.tags, title, converted_body)
                        if fid:
                            fields["fid"] = fid
                            fields["_forum_domain"] = domain
                            name = get_forum_name(domain, fid)
                            warnings.append(f"智能匹配版块: {domain} → {name}(fid={fid})")
                    
                    # 如果是 OSHWHub → 匹配项目类型
                    elif domain == "oshwhub.com":
                        type_info = match_platform_type("oshwhub.com", ir.tags, title, converted_body)
                        if type_info:
                            fields["project_type"] = type_info.get("type_id")
                            fields["project_endpoint"] = type_info.get("endpoint")
                            fields["type_id"] = type_info.get("type_id")
                            warnings.append(f"智能匹配项目类型: OSHWHub → {type_info.get('type_name')}")
                    
                    # 如果是 CSDN → 匹配文章类型
                    elif domain == "csdn.net":
                        type_info = match_platform_type("csdn.net", ir.tags, title, converted_body)
                        if type_info:
                            fields["article_type"] = type_info.get("type_id")
                            fields["type_id"] = type_info.get("type_id")
                            warnings.append(f"智能匹配文章类型: CSDN → {type_info.get('type_name')}")
                            
                except ImportError:
                    pass  # forum_registry 不可用时跳过

            results[platform] = CompiledContent(
                platform=platform,
                display_name=rule.display_name,
                title=title,
                body=converted_body,
                summary=ir.summary,
                tags=ir.tags,
                images=all_images,
                image_warnings=image_warnings,
                fields=fields,
                warnings=warnings,
                success=True,
            )

        return results
