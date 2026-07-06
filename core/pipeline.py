"""
FlashSloth — 统一内容流水线调度器

三大模块(文章/视频/商品)共享同一套工作流抽象：
  采集(Collect) → 编译(Compile) → 预览(Preview) → 存草稿(Draft) → 发布(Publish)

差异只在对象模型和编译规则，流水线框架一致。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
from datetime import datetime


# ═══════════════════════════════════════════════
# 流水线阶段定义
# ═══════════════════════════════════════════════

class PipelineStage(Enum):
    COLLECT = "collect"      # 采集/获取原始素材
    COMPILE = "compile"      # 编译/转换/处理
    PREVIEW = "preview"      # 预览/检查
    DRAFT   = "draft"        # 保存草稿
    PUBLISH = "publish"      # 发布到目标平台


CONTENT_TYPES = {
    "article": "文章",
    "video":   "视频",
    "product": "商品",
}


# ═══════════════════════════════════════════════
# 统一内容数据模型
# ═══════════════════════════════════════════════

@dataclass
class ContentObject:
    """统一内容对象 — 所有类型都用这个传递"""
    type: str                          # article | video | product
    title: str = ""
    body: str = ""                     # Markdown / 描述 / 脚本
    summary: str = ""
    tags: list = field(default_factory=list)
    
    # 媒体资源
    images: list = field(default_factory=list)       # 图片URL列表
    videos: list = field(default_factory=list)       # 视频URL列表
    attachments: list = field(default_factory=list)  # 附件列表
    
    # 内容特定字段
    price: float = 0.0                 # 商品价格
    duration: int = 0                  # 视频时长(秒)
    cover: Optional[str] = None        # 封面图
    
    # 元数据
    source: str = ""                   # 来源平台
    source_url: str = ""               # 来源链接
    source_id: str = ""                # 来源ID
    status: str = "draft"              # draft | ready | published | retracted
    created_at: str = ""
    updated_at: str = ""
    
    # 流水线状态
    current_stage: str = "collect"
    compile_result: Any = None         # 编译产物
    preview_url: Optional[str] = None
    
    # 原始数据（调试用）
    raw: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


# ═══════════════════════════════════════════════
# 阶段处理器抽象
# ═══════════════════════════════════════════════

class StageHandler(ABC):
    """流水线中单个阶段的处理器基类"""
    
    @abstractmethod
    def execute(self, content: ContentObject, **kwargs) -> ContentObject:
        """执行本阶段处理，返回更新后的 ContentObject"""
        ...


class CollectHandler(StageHandler):
    """采集阶段基类"""
    pass


class CompileHandler(StageHandler):
    """编译阶段基类"""
    pass


class PreviewHandler(StageHandler):
    """预览阶段基类"""
    pass


class DraftHandler(StageHandler):
    """草稿阶段基类"""
    pass


class PublishHandler(StageHandler):
    """发布阶段基类"""
    pass


# ═══════════════════════════════════════════════
# 流水线调度器
# ═══════════════════════════════════════════════

class Pipeline:
    """
    统一流水线调度器。
    
    用法:
        pipe = Pipeline(content_type="article")
        pipe.set_handler("collect", MyCollectHandler())
        pipe.set_handler("compile", MyCompileHandler())
        
        obj = ContentObject(type="article", title="...", body="...")
        result = pipe.run(obj)
    """
    
    def __init__(self, content_type: str):
        if content_type not in CONTENT_TYPES:
            raise ValueError(f"不支持的内容类型: {content_type}，可选: {list(CONTENT_TYPES.keys())}")
        self.content_type = content_type
        self._handlers: dict[str, StageHandler] = {}
    
    def set_handler(self, stage: str, handler: StageHandler):
        """注册某个阶段的处理器"""
        self._handlers[stage] = handler
    
    def get_handler(self, stage: str) -> Optional[StageHandler]:
        return self._handlers.get(stage)
    
    def run_stage(self, content: ContentObject, stage: str, **kwargs) -> ContentObject:
        """执行单个阶段"""
        handler = self._handlers.get(stage)
        if not handler:
            raise ValueError(f"未注册 {stage} 阶段的处理器")
        content.current_stage = stage
        result = handler.execute(content, **kwargs)
        return result
    
    def run(self, content: ContentObject, **kwargs) -> ContentObject:
        """执行完整流水线：collect → compile → preview → draft → publish"""
        stages = ["collect", "compile", "preview", "draft", "publish"]
        for stage in stages:
            handler = self._handlers.get(stage)
            if not handler:
                continue  # 跳过未注册的阶段
            content = self.run_stage(content, stage, **kwargs)
        return content
    
    def run_until(self, content: ContentObject, until_stage: str, **kwargs) -> ContentObject:
        """执行到指定阶段为止"""
        stages = ["collect", "compile", "preview", "draft", "publish"]
        for stage in stages:
            if stage not in self._handlers:
                continue
            content = self.run_stage(content, stage, **kwargs)
            if stage == until_stage:
                break
        return content


# ═══════════════════════════════════════════════
# 快捷工厂
# ═══════════════════════════════════════════════

def create_pipeline(content_type: str) -> Pipeline:
    """创建指定类型的流水线（自动注册默认处理器）"""
    pipe = Pipeline(content_type)
    
    if content_type == "article":
        # 文章：空壳，使用外部 compiler 注册
        pass
    
    elif content_type == "product":
        # 商品：空壳
        pass
    
    elif content_type == "video":
        # 视频：空壳
        pass
    
    return pipe
