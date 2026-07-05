"""
CompileRule — 每平台编译规则定义

每个平台一个 CompileRule 实例，描述该平台对源材料的处理要求。
Compiler Engine 根据这些规则自动转换格式、处理图片、适配编辑器。
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageRule:
    """平台对图片的具体限制"""
    max_width: int = 0                  # 0 = 不限
    max_height: int = 0                 # 0 = 不限
    max_size_mb: float = 0              # 0 = 不限
    allowed_formats: list[str] = field(default_factory=lambda: ["jpg", "jpeg", "png", "gif", "webp"])
    upload_method: str = "attachment"   # attachment | api | base64_embed | third_party
    upload_api: str = ""                # API 端点路径（如果 upload_method=api）
    max_count: int = 0                  # 单篇文章最大图片数 (0=不限)
    auto_compress: bool = True          # 超过限制是否自动压缩


@dataclass
class BodyFormat:
    """正文格式规则"""
    format_type: str = "markdown"       # markdown | bbcode | html | richtext
    # markdown: 直接传 Markdown（CSDN/掘金/GitHub Pages）
    # bbcode:   Discuz! 系列
    # html:     WordPress 经典编辑器
    # richtext: 知乎/B站 富文本编辑器
    
    allow_html: bool = False            # 是否允许内嵌 HTML 标签
    allow_code_block: bool = True       # 是否支持代码块
    allow_table: bool = True            # 是否支持表格
    allow_image_caption: bool = False   # 图片是否支持额外描述
    
    # BBCode 特有
    bbcode_max_font_size: int = 7       # Discuz 字体大小最大 7
    
    # 额外头部/尾部（如 Discuz 需要加 [align=center] 等）
    header_template: str = ""
    footer_template: str = ""


@dataclass
class EditorField:
    """编辑器字段映射"""
    field_name: str                     # 字段ID（如 HTML 中 name/id 属性）
    field_type: str = "text"            # text | textarea | select | hidden
    label: str = ""
    required: bool = False
    selector: str = ""                  # CSS 选择器（Selenium/Playwright 用）
    placeholder: str = ""


@dataclass
class PublishOptions:
    """发布选项"""
    support_draft: bool = True          # 是否支持存草稿
    support_schedule: bool = False      # 是否支持定时发布
    support_categories: bool = False    # 是否支持分类/版块
    support_tags: bool = True           # 是否支持标签
    support_cover: bool = False         # 是否支持封面图
    need_review: bool = False           # 发布后是否需要人工审核


@dataclass
class CompileRule:
    """
    平台编译规则 — 描述一个平台如何编译源文章。
    
    每个 PlatformAdapter 在类级别定义此规则，Compiler Engine 自动读取使用。
    """
    # 基本信息
    platform: str = ""                  # 平台标识（对应 adapter name）
    display_name: str = ""
    
    # 标题规则
    max_title_length: int = 80
    
    # 正文规则
    body: BodyFormat = field(default_factory=BodyFormat)
    
    # 图片规则
    image: ImageRule = field(default_factory=ImageRule)
    
    # 编辑器字段映射
    fields: list[EditorField] = field(default_factory=list)
    
    # 发布选项
    publish: PublishOptions = field(default_factory=PublishOptions)
    
    # 媒体类型
    media_type: str = "article"         # article | video | product | tweet
    
    # 特殊注意事项（展示给用户）
    notes: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════
# 预设规则
# ═══════════════════════════════════════════════

# —— Discuz! 系列 (mydigit.cn / amobbs.com) ——
DISCUZ_RULE = CompileRule(
    platform="discuz",
    display_name="Discuz! 论坛",
    max_title_length=80,
    body=BodyFormat(
        format_type="bbcode",
        allow_html=False,
        allow_code_block=True,
        allow_table=True,
        bbcode_max_font_size=7,
        header_template="",
        footer_template="",
    ),
    image=ImageRule(
        max_width=1000,
        max_size_mb=2.0,
        allowed_formats=["jpg", "jpeg", "png", "gif"],
        upload_method="attachment",
        max_count=50,
        auto_compress=True,
    ),
    fields=[
        EditorField(field_name="subject", field_type="text", label="标题",
                    selector="#subject", required=True),
        EditorField(field_name="message", field_type="textarea", label="正文",
                    selector="#e_content"),
        EditorField(field_name="fid", field_type="select", label="版块"),
    ],
    publish=PublishOptions(support_draft=True, support_categories=True,
                           support_tags=False, need_review=True),
    notes=["发布后可能需要等待版主审核", "图片通过论坛附件上传"],
)

# —— CSDN ——
CSDN_RULE = CompileRule(
    platform="csdn",
    display_name="CSDN",
    max_title_length=60,
    body=BodyFormat(format_type="markdown", allow_html=True, allow_code_block=True),
    image=ImageRule(
        max_width=1920, max_size_mb=5.0,
        upload_method="api", upload_api="/api/file/upload",
        auto_compress=True,
    ),
    fields=[
        EditorField(field_name="title", selector="input[placeholder*='标题']"),
        EditorField(field_name="content", selector=".editor-content"),
        EditorField(field_name="article_type", field_type="select"),
    ],
    publish=PublishOptions(support_draft=True, support_tags=True, support_cover=True),
    notes=["CSDN 编辑器支持 Markdown", "图片通过 CSDN 图床上传"],
)

# —— GitHub Pages ——
GITHUB_PAGES_RULE = CompileRule(
    platform="github_pages",
    display_name="GitHub Pages",
    max_title_length=200,
    body=BodyFormat(format_type="markdown", allow_html=True),
    image=ImageRule(upload_method="local", auto_compress=False),
    publish=PublishOptions(support_draft=False, support_tags=True, support_cover=True),
    notes=["文章直接提交到 Git 仓库，无需模拟浏览器"],
)

# —— OSHWHub ——
OSHWHUB_RULE = CompileRule(
    platform="oshwhub",
    display_name="立创开源硬件平台",
    max_title_length=50,
    body=BodyFormat(format_type="markdown", allow_html=False),
    image=ImageRule(max_width=1200, max_size_mb=3.0, upload_method="api"),
    fields=[
        EditorField(field_name="title", label="项目名称"),
        EditorField(field_name="description", field_type="textarea", label="项目描述"),
        EditorField(field_name="content", field_type="textarea", label="正文"),
    ],
    publish=PublishOptions(support_draft=True, support_tags=True, support_cover=True),
    notes=['OSHWHub 以"项目"形式发布，需要封面图'],
)

# —— 知乎 ——
ZHIHU_RULE = CompileRule(
    platform="zhihu",
    display_name="知乎",
    max_title_length=50,
    body=BodyFormat(format_type="richtext", allow_html=True, allow_code_block=False),
    image=ImageRule(max_width=1920, max_size_mb=10.0, upload_method="api"),
    publish=PublishOptions(support_draft=True, support_tags=True, need_review=True),
    notes=["知乎使用富文本编辑器（非 Markdown）", "需将 Markdown 转为富文本"],
)

# —— B站 ——
BILIBILI_RULE = CompileRule(
    platform="bilibili",
    display_name="B站",
    max_title_length=30,
    body=BodyFormat(format_type="richtext", allow_html=False, allow_code_block=False),
    image=ImageRule(max_width=1920, max_size_mb=10.0, upload_method="api"),
    publish=PublishOptions(support_draft=True, support_tags=True, support_cover=True),
    notes=["B站专栏有自己富文本格式", "需注意敏感词过滤"],
)

# —— 掘金 ——
JUEJIN_RULE = CompileRule(
    platform="juejin",
    display_name="掘金",
    max_title_length=60,
    body=BodyFormat(format_type="markdown", allow_html=True, allow_code_block=True),
    image=ImageRule(max_width=1920, max_size_mb=5.0, upload_method="api"),
    publish=PublishOptions(support_draft=True, support_tags=True, support_cover=True),
)

# —— WordPress ——
WORDPRESS_RULE = CompileRule(
    platform="wordpress",
    display_name="WordPress",
    max_title_length=200,
    body=BodyFormat(format_type="html", allow_html=True),
    image=ImageRule(upload_method="api", upload_api="/wp-json/wp/v2/media"),
    publish=PublishOptions(support_draft=True, support_tags=True, support_categories=True,
                           support_cover=True, support_schedule=True),
    notes=["WordPress 通过 REST API 发布", "图片通过 media API 上传"],
)

# —— 微信公众号 ——
WECHAT_RULE = CompileRule(
    platform="wechat",
    display_name="微信公众号",
    max_title_length=64,
    body=BodyFormat(format_type="html", allow_html=True, allow_code_block=False),
    image=ImageRule(max_width=1080, max_size_mb=10.0, upload_method="api",
                    allowed_formats=["jpg", "jpeg", "png", "gif"]),
    publish=PublishOptions(support_draft=True, support_tags=False, support_cover=True,
                           need_review=True),
    notes=["公众号发文需通过素材管理接口", "部分图片格式可能被压缩"],
)

# —— 闲鱼 ——
XIANYU_RULE = CompileRule(
    platform="xianyu",
    display_name="闲鱼",
    max_title_length=30,
    body=BodyFormat(format_type="html", allow_html=False),
    image=ImageRule(max_width=1920, max_size_mb=10.0, upload_method="api",
                    max_count=9),
    publish=PublishOptions(support_draft=True, support_tags=False, support_cover=True),
    notes=["闲鱼是商品发布，标题要短", "最多 9 张图片"],
)

# —— Twitter/X ——
TWITTER_RULE = CompileRule(
    platform="twitter",
    display_name="Twitter/X",
    max_title_length=0,  # 无标题，用首句
    body=BodyFormat(format_type="text", allow_html=False, allow_code_block=False),
    image=ImageRule(max_width=1920, max_size_mb=5.0, upload_method="api",
                    max_count=4),
    publish=PublishOptions(support_draft=True, support_tags=False, need_review=False),
    notes=["推文长度限制 280/4000 字符", "单条最多 4 张图片"],
)

# —— YouTube ——
YOUTUBE_RULE = CompileRule(
    platform="youtube",
    display_name="YouTube",
    max_title_length=100,
    body=BodyFormat(format_type="text", allow_html=False),
    image=ImageRule(upload_method="api"),
    publish=PublishOptions(support_draft=True, support_tags=True, support_cover=True,
                           support_schedule=True),
    notes=["视频发布需要先上传视频文件", "描述支持标签和链接"],
    media_type="video",
)

# 规则注册表
_RULES: dict[str, CompileRule] = {}


def register_rule(rule: CompileRule):
    """注册一条编译规则"""
    _RULES[rule.platform] = rule


def get_rule(platform: str) -> Optional[CompileRule]:
    """获取指定平台的编译规则"""
    return _RULES.get(platform)


def list_rules() -> list[CompileRule]:
    """列出所有已注册的编译规则"""
    return list(_RULES.values())


def list_media_types() -> dict[str, list[str]]:
    """按媒体类型分组列出平台"""
    result: dict[str, list[str]] = {}
    for name, rule in _RULES.items():
        mt = rule.media_type
        if mt not in result:
            result[mt] = []
        result[mt].append(name)
    return result


# 注册预设规则
for _rule in [DISCUZ_RULE, CSDN_RULE, GITHUB_PAGES_RULE, OSHWHUB_RULE,
              ZHIHU_RULE, BILIBILI_RULE, JUEJIN_RULE, WORDPRESS_RULE,
              WECHAT_RULE, XIANYU_RULE, TWITTER_RULE, YOUTUBE_RULE]:
    register_rule(_rule)
