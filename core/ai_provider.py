"""
AI Provider — 统一AI能力框架

每个AI服务商写一个Provider，注册到全局注册表。
一个能力(写作/画图/配音/视频等)可配多个Provider，支持并行/自动切换。

模式：PlatformAdapter 一致的注册+发现模式，方便开源扩展。
"""
from typing import Optional, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import json, os


# ═══════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════

@dataclass
class AIRequest:
    """一次AI请求"""
    capability: str               # 能力类型: writing/image_gen/audio_gen/video_gen/translate
    prompt: str                   # 提示词
    model: str = ""               # 指定模型（可选）
    provider: str = ""            # 指定Provider（可选）
    images: list = field(default_factory=list)      # 参考图片URL
    context: dict = field(default_factory=dict)     # 额外上下文
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class AIResponse:
    """AI响应"""
    success: bool = True
    content: str = ""             # 文本内容（写作/翻译等）
    images: list = field(default_factory=list)      # 生成的图片URL/path
    audio: str = ""               # 音频URL/path
    video: str = ""               # 视频URL/path
    model: str = ""               # 实际使用的模型
    provider: str = ""            # 实际使用的Provider
    error: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class AIProviderConfig:
    """单个AI Provider的配置"""
    provider: str = ""            # provider名
    api_key: str = ""
    api_base: str = ""
    model: str = ""
    enabled: bool = True
    weight: int = 1               # 权重（用于负载均衡）
    extra: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════
# AI Provider 基类
# ═══════════════════════════════════════════════

class AIProvider(ABC):
    """
    AI Provider 基类。
    
    子类需设置:
        name: str          唯一标识，如 "openai", "doubao"
        display_name: str  显示名
        capabilities: list 支持的能力列表
    
    子类需实现:
        generate(request: AIRequest) -> AIResponse
    """
    name: str = ""
    display_name: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    config_fields: list[dict] = field(default_factory=list)
    models: list[str] = field(default_factory=list)  # 支持的模型列表
    icon: str = "🤖"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.api_key = self.config.get("api_key", "")
        self.api_base = self.config.get("api_base", "")

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """执行AI生成请求"""
        ...

    def supports(self, capability: str) -> bool:
        """检查是否支持某能力"""
        return capability in self.capabilities

    def test_connection(self) -> dict:
        """测试连接"""
        return {"success": True, "error": "", "status": "未实现"}


# ═══════════════════════════════════════════════
# Provider 实现示例
# ═══════════════════════════════════════════════

@register_ai_provider
class OpenAIProvider(AIProvider):
    name = "openai"
    display_name = "OpenAI"
    description = "OpenAI GPT-4o / DALL-E 3 / TTS"
    icon = "🟢"
    capabilities = ["writing", "image_gen", "audio_gen", "translate"]
    models = ["gpt-4o", "gpt-4o-mini", "dall-e-3", "tts-1"]
    config_fields = [
        {"key": "api_key", "label": "API Key", "type": "password", "required": True},
        {"key": "api_base", "label": "API Base URL", "type": "text", "required": False,
         "placeholder": "https://api.openai.com/v1"},
    ]

    def generate(self, request: AIRequest) -> AIResponse:
        import requests
        base = self.api_base or "https://api.openai.com/v1"

        if request.capability == "image_gen":
            # DALL-E 画图
            resp = requests.post(
                f"{base}/images/generations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": request.model or "dall-e-3",
                    "prompt": request.prompt,
                    "n": 1,
                    "size": "1024x1024",
                },
                timeout=60,
            )
            data = resp.json()
            if resp.ok:
                images = [d["url"] for d in data.get("data", [])]
                return AIResponse(content=request.prompt, images=images, provider="openai")
            return AIResponse(success=False, error=str(data), provider="openai")

        elif request.capability == "audio_gen":
            # TTS 配音
            resp = requests.post(
                f"{base}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": request.model or "tts-1",
                    "input": request.prompt,
                    "voice": "alloy",
                },
                timeout=60,
            )
            if resp.ok:
                audio_path = f"/tmp/ai_audio_{int(time.time())}.mp3"
                with open(audio_path, "wb") as f:
                    f.write(resp.content)
                return AIResponse(content="", audio=audio_path, provider="openai")
            return AIResponse(success=False, error=resp.text, provider="openai")

        else:
            # 文本生成（写作/翻译）
            resp = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": request.model or "gpt-4o",
                    "messages": [
                        {"role": "system", "content": f"你是一个{'翻译' if request.capability == 'translate' else '文章写作'}助手"},
                        {"role": "user", "content": request.prompt},
                    ],
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                },
                timeout=120,
            )
            data = resp.json()
            if resp.ok:
                content = data["choices"][0]["message"]["content"]
                return AIResponse(content=content, model=request.model or "gpt-4o", provider="openai")
            return AIResponse(success=False, error=str(data), provider="openai")


@register_ai_provider
class DoubaoProvider(AIProvider):
    """豆包 / 火山引擎（画图专用）"""
    name = "doubao"
    display_name = "豆包 (火山引擎)"
    description = "字节跳动豆包大模型 — 画图/写作"
    icon = "🫘"
    capabilities = ["image_gen", "writing"]
    models = ["doubao-pro", "doubao-pro-32k"]
    config_fields = [
        {"key": "api_key", "label": "API Key", "type": "password", "required": True},
        {"key": "api_base", "label": "API Endpoint", "type": "text", "required": False},
    ]

    def generate(self, request: AIRequest) -> AIResponse:
        # TODO: 实现豆包API调用
        return AIResponse(success=False, error="豆包API尚未接入", provider="doubao")


@register_ai_provider
class DeepSeekProvider(AIProvider):
    """DeepSeek — 高性价比写作"""
    name = "deepseek"
    display_name = "DeepSeek"
    description = "DeepSeek V3 — 高性价比文本生成"
    icon = "🔮"
    capabilities = ["writing", "translate"]
    models = ["deepseek-chat", "deepseek-reasoner"]
    config_fields = [
        {"key": "api_key", "label": "API Key", "type": "password", "required": True},
    ]

    def generate(self, request: AIRequest) -> AIResponse:
        import requests
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": request.model or "deepseek-chat",
                "messages": [
                    {"role": "system", "content": f"你是一个{'翻译' if request.capability == 'translate' else '文章写作'}助手"},
                    {"role": "user", "content": request.prompt},
                ],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            },
            timeout=120,
        )
        data = resp.json()
        if resp.ok:
            content = data["choices"][0]["message"]["content"]
            return AIResponse(content=content, provider="deepseek", model=request.model or "deepseek-chat")
        return AIResponse(success=False, error=str(data), provider="deepseek")


# ═══════════════════════════════════════════════
# 注册中心
# ═══════════════════════════════════════════════

_registry: dict[str, type[AIProvider]] = {}
# 能力 → [provider列表] （按权重排序）
_capability_map: dict[str, list[str]] = {}


def register_ai_provider(cls):
    """装饰器：注册AI Provider"""
    _registry[cls.name] = cls
    for cap in cls.capabilities:
        if cap not in _capability_map:
            _capability_map[cap] = []
        _capability_map[cap].append(cls.name)
    return cls


def get_ai_provider(name: str, config: Optional[dict] = None) -> Optional[AIProvider]:
    """获取Provider实例"""
    cls = _registry.get(name)
    if not cls:
        return None
    return cls(config)


def get_providers_for_capability(capability: str) -> list[str]:
    """获取支持某能力的所有Provider名称"""
    return _capability_map.get(capability, [])


def list_ai_providers() -> list[dict]:
    """列出所有已注册的AI Provider"""
    result = []
    for name, cls in _registry.items():
        inst = cls()
        result.append({
            "name": name,
            "display_name": inst.display_name,
            "description": inst.description,
            "capabilities": inst.capabilities,
            "models": inst.models,
            "config_fields": inst.config_fields,
            "icon": inst.icon,
        })
    return result


# ═══════════════════════════════════════════════
# 能力路由器 — 调用时自动选择Provider
# ═══════════════════════════════════════════════

class AIRouter:
    """
    AI 能力路由器。
    
    用法:
        router = AIRouter()
        # 写作能力：用deepseek
        router.set_capability_config("writing", {"provider": "deepseek", "model": "deepseek-chat"})
        # 画图能力：并行调用openai和doubao，取最优
        router.set_capability_config("image_gen", {
            "providers": [
                {"name": "openai", "model": "dall-e-3", "weight": 2},
                {"name": "doubao", "model": "doubao-pro", "weight": 1},
            ],
            "mode": "parallel",  # parallel=并行取最佳, fallback=故障切换
        })
        
        result = router.call("writing", "写一篇关于...的文章")
        results = router.call_parallel("image_gen", ["提示词1", "提示词2"])
    """

    _capability_configs: dict = {}
    _provider_configs: dict[str, dict] = {}

    def __init__(self, config_path: str = ""):
        self._config_path = config_path or os.environ.get(
            "AI_CONFIG_PATH",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "ai_capabilities.json"),
        )
        self._load_config()

    def _load_config(self):
        """从配置文件加载能力配置"""
        if os.path.exists(self._config_path):
            with open(self._config_path) as f:
                data = json.load(f)
                self._capability_configs = data.get("capabilities", {})
                self._provider_configs = data.get("providers", {})

    def save_config(self):
        """保存配置文件"""
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w") as f:
            json.dump({
                "capabilities": self._capability_configs,
                "providers": self._provider_configs,
            }, f, indent=2, ensure_ascii=False)

    def set_capability_config(self, capability: str, config: dict):
        """设置某能力的路由配置"""
        self._capability_configs[capability] = config

    def get_capability_config(self, capability: str) -> dict:
        """获取某能力的路由配置"""
        return self._capability_configs.get(capability, {})

    def set_provider_config(self, provider: str, config: dict):
        """设置Provider的API密钥等配置"""
        self._provider_configs[provider] = config

    def get_provider_config(self, provider: str) -> dict:
        """获取Provider配置"""
        return self._provider_configs.get(provider, {})

    def call(self, capability: str, prompt: str, **kwargs) -> AIResponse:
        """
        调用AI能力（单次）。
        
        内部自动选择Provider：按配置的主Provider → fallback顺序。
        """
        config = self._capability_configs.get(capability, {})

        # 主Provider模式
        if "provider" in config:
            provider_name = config["provider"]
            provider_cfg = {**self._provider_configs.get(provider_name, {}), **kwargs}
            provider = get_ai_provider(provider_name, provider_cfg)
            if provider:
                request = AIRequest(capability=capability, prompt=prompt,
                                    model=kwargs.get("model") or config.get("model", ""),
                                    **{k: v for k, v in kwargs.items() if k in ["temperature", "max_tokens", "images"]})
                return provider.generate(request)

        # 多个Provider：fallback模式
        providers_list = config.get("providers", [])
        if providers_list:
            for pcfg in providers_list:
                provider = get_ai_provider(pcfg["name"], self._provider_configs.get(pcfg["name"], {}))
                if provider:
                    try:
                        request = AIRequest(capability=capability, prompt=prompt,
                                            model=pcfg.get("model", ""), **kwargs)
                        result = provider.generate(request)
                        if result.success:
                            return result
                    except Exception:
                        continue

        # 自动发现：尝试所有支持此能力的Provider
        for pname in get_providers_for_capability(capability):
            provider = get_ai_provider(pname, self._provider_configs.get(pname, {}))
            if provider:
                try:
                    request = AIRequest(capability=capability, prompt=prompt, **kwargs)
                    result = provider.generate(request)
                    if result.success:
                        return result
                except Exception:
                    continue

        return AIResponse(success=False, error=f"没有可用的{capability}能力Provider")

    def call_parallel(self, capability: str, prompts: list[str], **kwargs) -> list[AIResponse]:
        """
        并行调用AI能力（适合画图等）。
        多个prompt同时发送。
        """
        import concurrent.futures

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(prompts)) as executor:
            futures = {executor.submit(self.call, capability, p, **kwargs): p for p in prompts}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append(AIResponse(success=False, error=str(e)))
        return results


# ═══════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════

_router: Optional[AIRouter] = None


def get_router() -> AIRouter:
    """获取全局AIRouter实例"""
    global _router
    if _router is None:
        _router = AIRouter()
    return _router


# 默认配置
DEFAULT_CONFIG = {
    "capabilities": {
        "writing": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "fallback": "openai",
        },
        "image_gen": {
            "providers": [
                {"name": "openai", "model": "dall-e-3", "weight": 2},
            ],
            "mode": "fallback",
        },
        "translate": {
            "provider": "openai",
            "model": "gpt-4o-mini",
        },
        "audio_gen": {
            "provider": "openai",
            "model": "tts-1",
        },
    }
}
