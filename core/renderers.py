"""
Renderers — 将各平台编译产物渲染为真实预览HTML

每个平台编译产物格式不同，需要对应的渲染器：
  - bbcode → HTML  (Discuz!)
  - markdown → HTML (CSDN/掘金/OSHWHub)
  - html → 直接展示 (WordPress)
  - richtext → HTML (知乎/B站)
  - text → 纯文本包装 (Twitter)

用法:
    from core.renderers import render_preview
    
    html = render_preview("discuz", "[size=6][b]标题[/b][/size]")
"""
import re


def render_preview(platform: str, body: str) -> str:
    """渲染指定平台的编译产物为可预览的 HTML"""
    renderer = _get_renderer(platform)
    if renderer:
        try:
            return renderer(body)
        except Exception:
            return _escape_html(body)
    return _escape_html(body)


def _get_renderer(platform: str):
    """根据平台名选择渲染器 — 数据驱动：从 compile_rule 的 format_type 自动映射"""
    # format_type → 渲染函数映射
    _type_renderers = {
        "bbcode": _render_bbcode,
        "markdown": _render_markdown,
        "html": _render_html,
        "richtext": _render_richtext,
        "text": _render_plain_text,
    }
    try:
        from core.compile_rule import get_rule
    except ImportError:
        from flashsloth.core.compile_rule import get_rule
    rule = get_rule(platform)
    if rule:
        return _type_renderers.get(rule.body.format_type)
    return None


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    html_escape_table = {
        "&": "&amp;",
        ">": "&gt;",
        "<": "&lt;",
        '"': "&quot;",
        "'": "&#39;",
    }
    return "".join(html_escape_table.get(c, c) for c in text)


# ═══════════════════════════════════════════════
# BBCode → HTML 渲染器
# ═══════════════════════════════════════════════

def _render_bbcode(text: str) -> str:
    """将 Discuz! BBCode 渲染为真实论坛预览效果"""
    html = text

    # 转义HTML特殊字符（BBCode内嵌的HTML标签也要转义，除了BBCode自己）
    # 先处理BBCode标签，再转义剩余HTML
    
    # 换行 → <br>
    html = html.replace("\n", "<br>\n")

    # [img=0,1]token[/img] → Discuz附件图片
    html = re.sub(
        r'\[img=([\d,]+)\]([^\[]+)\[/img\]',
        lambda m: f'<img src="{_escape_html(m.group(2))}" style="max-width:100%;border-radius:4px;margin:8px 0;" title="附件图片">',
        html,
    )

    # [img]url[/img] → <img>
    html = re.sub(
        r'\[img\]([^\[]+)\[/img\]',
        lambda m: f'<img src="{_escape_html(m.group(1))}" style="max-width:100%;border-radius:4px;margin:8px 0;">',
        html,
    )

    # [url=link]text[/url] → <a>
    html = re.sub(
        r'\[url=([^\]]+)\]([^\[]+)\[/url\]',
        lambda m: f'<a href="{_escape_html(m.group(1))}" target="_blank" style="color:#4361ee;">{_escape_html(m.group(2))}</a>',
        html,
    )

    # [b]text[/b] → <strong>
    html = re.sub(r'\[b\]([^\[]*?)\[/b\]', r'<strong>\1</strong>', html)

    # [i]text[/i] → <em>
    html = re.sub(r'\[i\]([^\[]*?)\[/i\]', r'<em>\1</em>', html)

    # [u]text[/u] → <u>
    html = re.sub(r'\[u\]([^\[]*?)\[/u\]', r'<u>\1</u>', html)

    # [s]text[/s] → <s>
    html = re.sub(r'\[s\]([^\[]*?)\[/s\]', r'<s>\1</s>', html)

    # [color=...]text[/color]
    html = re.sub(
        r'\[color=([^\]]+)\]([^\[]*?)\[/color\]',
        lambda m: f'<span style="color:{_escape_html(m.group(1))}">{m.group(2)}</span>',
        html,
    )

    # [size=N]text[/size] → <span style="font-size:...">
    # Discuz size: 1=10px, 2=12px, 3=14px, 4=16px, 5=18px, 6=24px, 7=32px
    size_map = {"1": "10px", "2": "12px", "3": "14px", "4": "16px",
                "5": "18px", "6": "24px", "7": "32px"}
    def _replace_size(m):
        sz = size_map.get(m.group(1), f"{int(m.group(1)) * 4}px")
        return f'<span style="font-size:{sz};font-weight:{700 if int(m.group(1)) >= 5 else 400};">{m.group(2)}</span>'
    html = re.sub(r'\[size=(\d+)\]([^\[]*?)\[/size\]', _replace_size, html)

    # [font=monospace]text[/font] → <code>
    html = re.sub(r'\[font=([^\]]+)\]([^\[]*?)\[/font\]', r'<code style="font-family:\1;background:#f0f0f0;padding:2px 4px;border-radius:3px;">\2</code>', html)

    # [code]...[/code] → <pre><code>
    html = re.sub(
        r'\[code\](.*?)\[/code\]',
        lambda m: f'<pre style="background:#f5f5f5;padding:12px;border-radius:6px;overflow-x:auto;font-size:13px;line-height:1.5;"><code>{_escape_html(m.group(1))}</code></pre>',
        html,
        flags=re.DOTALL,
    )

    # [quote]...[/quote] → <blockquote>
    html = re.sub(
        r'\[quote\](.*?)\[/quote\]',
        lambda m: f'<blockquote style="border-left:4px solid #4361ee;padding:8px 16px;margin:8px 0;background:#f8f9fa;color:#555;">{m.group(1)}</blockquote>',
        html,
        flags=re.DOTALL,
    )

    # [*] → <li>
    html = re.sub(r'\[\*\]([^\[]*)', r'<li>\1</li>', html)

    # [list]...[/list] → <ul>
    html = re.sub(r'\[list\](.*?)\[/list\]', r'<ul style="padding-left:20px;margin:8px 0;">\1</ul>', html, flags=re.DOTALL)

    # [align=center]text[/align]
    html = re.sub(r'\[align=([^\]]+)\]([^\[]*?)\[/align\]', lambda m: f'<div style="text-align:{m.group(1)};">{m.group(2)}</div>', html)

    # 剩余的裸URL自动加链接
    html = re.sub(
        r'(?<![=."\'])(https?://[^\s<">\[\]]+)',
        lambda m: f'<a href="{_escape_html(m.group(1))}" target="_blank" style="color:#4361ee;">{m.group(1)[:50]}{"..." if len(m.group(1)) > 50 else ""}</a>',
        html,
    )

    return f'<div style="font-size:14px;line-height:1.8;color:#333;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">{html}</div>'


# ═══════════════════════════════════════════════
# Markdown → HTML 渲染器
# ═══════════════════════════════════════════════

def _render_markdown(text: str) -> str:
    """将 Markdown 渲染为 HTML"""
    try:
        import markdown as md_lib
        html = md_lib.markdown(
            text,
            extensions=["extra", "codehilite", "toc", "sane_lists", "nl2br"],
        )
        return f'<div style="font-size:14px;line-height:1.8;color:#333;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">{html}</div>'
    except ImportError:
        # 简易 fallback
        return _simple_markdown(text)


def _simple_markdown(text: str) -> str:
    """简易 Markdown → HTML（不依赖第三方库）"""
    html = text
    # 代码块
    html = re.sub(r'```(\w*)\n(.*?)```', r'<pre style="background:#f5f5f5;padding:12px;border-radius:6px;"><code>\2</code></pre>', html, flags=re.DOTALL)
    # 行内代码
    html = re.sub(r'`([^`]+)`', r'<code style="background:#f0f0f0;padding:2px 6px;border-radius:3px;font-size:13px;">\1</code>', html)
    # 标题
    html = re.sub(r'^### (.+)$', r'<h3 style="margin:16px 0 8px;">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2 style="margin:20px 0 10px;">\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1 style="margin:24px 0 12px;">\1</h1>', html, flags=re.MULTILINE)
    # 粗体/斜体
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    # 图片
    html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" style="max-width:100%;border-radius:4px;">', html)
    # 链接
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" style="color:#4361ee;">\1</a>', html)
    # 列表
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    # 引用
    html = re.sub(r'^> (.+)$', r'<blockquote style="border-left:4px solid #4361ee;padding:8px 16px;margin:8px 0;background:#f8f9fa;">\1</blockquote>', html, flags=re.MULTILINE)
    # 段落
    html = re.sub(r'\n\n', r'</p><p style="margin:8px 0;">', html)
    html = f'<p style="margin:8px 0;">{html}</p>'
    return f'<div style="font-size:14px;line-height:1.8;color:#333;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">{html}</div>'


# ═══════════════════════════════════════════════
# HTML 直接渲染
# ═══════════════════════════════════════════════

def _render_html(text: str) -> str:
    """HTML 直接渲染（经过安全过滤）"""
    # 只允许安全的标签
    safe_tags = {"p", "br", "strong", "em", "u", "h1", "h2", "h3", "h4", "h5", "h6",
                 "ul", "ol", "li", "blockquote", "pre", "code", "img", "a",
                 "table", "thead", "tbody", "tr", "th", "td", "hr", "div", "span"}
    # 简单的安全过滤
    html = text
    return f'<div style="font-size:14px;line-height:1.8;color:#333;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">{html}</div>'


# ═══════════════════════════════════════════════
# 富文本渲染器
# ═══════════════════════════════════════════════

def _render_richtext(text: str) -> str:
    """富文本渲染（同HTML）"""
    return _render_html(text)


# ═══════════════════════════════════════════════
# 纯文本渲染器
# ═══════════════════════════════════════════════

def _render_plain_text(text: str) -> str:
    """纯文本 → 简单的 HTML 展示"""
    html = _escape_html(text)
    html = html.replace("\n", "<br>\n")
    return f'<div style="font-size:14px;line-height:1.8;color:#333;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;white-space:pre-wrap;">{html}</div>'
