"""Provider Registry — 动态AI供应商注册表

从 provider_registry.json 加载所有供应商预设，支持：
1. 运行时动态发现供应商（无需改代码）
2. 统一 OpenAI 兼容格式调用
3. 用户通过 UI 自定义添加供应商
4. 所有供应商配置可互相引用
"""
import json, os, re
from typing import Optional
from dataclasses import dataclass, field


_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "provider_registry.json")


@dataclass
class ProviderDefinition:
    """单个AI供应商的定义（从JSON加载，不包含敏感信息）"""
    name: str
    display_name: str
    category: str = "custom"
    description: str = ""
    icon: str = "🤖"
    website: str = ""
    api_base: str = ""
    api_format: str = "openai"  # openai | anthropic | gemini
    models: list = field(default_factory=list)
    capabilities: list = field(default_factory=list)
    config_fields: list = field(default_factory=list)


class ProviderRegistry:
    """供应商注册表 — 加载 + 查询 + 自定义"""

    def __init__(self, path: str = ""):
        self._path = path or _REGISTRY_PATH
        self._providers: dict[str, ProviderDefinition] = {}
        self._categories: dict[str, dict] = {}
        self._custom_providers: dict[str, ProviderDefinition] = {}
        self._load()

    def _load(self):
        """从JSON文件加载供应商预设"""
        if not os.path.exists(self._path):
            self._providers = {}
            self._categories = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._categories = data.get("categories", {})
            for p in data.get("providers", []):
                self._providers[p["name"]] = ProviderDefinition(**p)
        except Exception as e:
            print(f"[ProviderRegistry] 加载失败: {e}")
            self._providers = {}

    def load_custom(self, custom_json: str):
        """加载用户自定义供应商（从数据库存储的JSON）"""
        try:
            data = json.loads(custom_json) if isinstance(custom_json, str) else custom_json
            for p in data if isinstance(data, list) else data.get("providers", []):
                self._custom_providers[p["name"]] = ProviderDefinition(**p)
        except Exception:
            pass

    def get_all(self) -> list[ProviderDefinition]:
        """获取所有供应商（预设 + 自定义）"""
        result = list(self._providers.values())
        result.extend(self._custom_providers.values())
        return result

    def get(self, name: str) -> Optional[ProviderDefinition]:
        """按名称获取供应商定义"""
        return self._providers.get(name) or self._custom_providers.get(name)

    def get_by_category(self) -> dict[str, list[ProviderDefinition]]:
        """按分类获取供应商列表"""
        grouped = {}
        for p in self.get_all():
            cat = p.category or "custom"
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(p)
        return grouped

    def get_categories(self) -> list[dict]:
        """获取分类列表"""
        return [
            {"key": k, "name": v.get("name", k), "icon": v.get("icon", "📦")}
            for k, v in self._categories.items()
        ]

    def to_json(self, include_custom: bool = True) -> dict:
        """导出为可序列化的字典"""
        providers = []
        for p in self._providers.values():
            providers.append({
                "name": p.name,
                "display_name": p.display_name,
                "category": p.category,
                "description": p.description,
                "icon": p.icon,
                "website": p.website,
                "api_base": p.api_base,
                "api_format": p.api_format,
                "models": p.models,
                "capabilities": p.capabilities,
                "config_fields": p.config_fields,
            })
        if include_custom:
            for p in self._custom_providers.values():
                providers.append({
                    "name": p.name,
                    "display_name": p.display_name,
                    "category": "custom",
                    "description": p.description or "自定义供应商",
                    "icon": p.icon,
                    "website": p.website,
                    "api_base": p.api_base,
                    "api_format": p.api_format or "openai",
                    "models": p.models,
                    "capabilities": p.capabilities,
                    "config_fields": p.config_fields,
                })
        return {
            "version": "1.0",
            "categories": self._categories,
            "providers": providers,
        }


# 全局单例
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


# ═══════════════════════════════════════════════
# 统一适配器 — 用任何供应商定义 + API Key 调用
# ═══════════════════════════════════════════════

class UnifiedAIAdapter:
    """统一AI适配器 — 根据供应商定义自动选择合适的API格式调用

    支持:
    - openai: OpenAI Chat Completions 格式（最广泛）
    - anthropic: Anthropic Messages API 格式
    - gemini: Gemini generateContent 格式
    """

    def __init__(self, provider_def: ProviderDefinition, api_key: str = "", api_base: str = ""):
        self.defn = provider_def
        self.api_key = api_key
        self.api_base = api_base or provider_def.api_base

    def test_connection(self) -> dict:
        """测试连接"""
        fmt = self.defn.api_format
        if fmt == "openai":
            return self._test_openai()
        elif fmt == "anthropic":
            return self._test_anthropic()
        elif fmt == "gemini":
            return self._test_gemini()
        return {"success": False, "error": f"不支持的API格式: {fmt}"}

    def generate(self, prompt: str, model: str = "", capability: str = "writing",
                 temperature: float = 0.7, max_tokens: int = 4096) -> dict:
        """生成内容"""
        fmt = self.defn.api_format
        if fmt == "openai":
            return self._generate_openai(prompt, model, capability, temperature, max_tokens)
        elif fmt == "anthropic":
            return self._generate_anthropic(prompt, model, capability, temperature, max_tokens)
        elif fmt == "gemini":
            return self._generate_gemini(prompt, model, capability, temperature, max_tokens)
        return {"success": False, "error": f"不支持的API格式: {fmt}"}

    def _test_openai(self) -> dict:
        """测试 OpenAI 兼容 API"""
        import requests
        try:
            base = self.api_base.rstrip("/")
            resp = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.defn.models[0] if self.defn.models else "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "OK"}],
                    "max_tokens": 8,
                },
                timeout=15,
            )
            data = resp.json()
            if resp.ok:
                content = data["choices"][0]["message"]["content"]
                return {"success": True, "content": content, "model": data.get("model", ""), "provider": self.defn.name}
            err = data.get("error", {}).get("message", str(data))
            return {"success": False, "error": f"API错误: {err}"}
        except Exception as e:
            return {"success": False, "error": f"连接异常: {e}"}

    def _test_anthropic(self) -> dict:
        """测试 Anthropic API"""
        import requests
        try:
            base = self.api_base.rstrip("/")
            resp = requests.post(
                f"{base}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.defn.models[0] if self.defn.models else "claude-sonnet-4-20250514",
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "OK"}],
                },
                timeout=15,
            )
            data = resp.json()
            if resp.ok:
                content = data["content"][0]["text"] if data.get("content") else ""
                return {"success": True, "content": content, "model": data.get("model", ""), "provider": self.defn.name}
            err = data.get("error", {}).get("message", str(data))
            return {"success": False, "error": f"API错误: {err}"}
        except Exception as e:
            return {"success": False, "error": f"连接异常: {e}"}

    def _test_gemini(self) -> dict:
        """测试 Gemini API"""
        import requests
        try:
            base = self.api_base.rstrip("/")
            model = self.defn.models[0] if self.defn.models else "gemini-2.0-flash"
            resp = requests.post(
                f"{base}/v1beta/models/{model}:generateContent",
                headers={"Content-Type": "application/json"},
                params={"key": self.api_key},
                json={"contents": [{"parts": [{"text": "OK"}]}]},
                timeout=15,
            )
            data = resp.json()
            if resp.ok:
                content = data["candidates"][0]["content"]["parts"][0]["text"] if data.get("candidates") else ""
                return {"success": True, "content": content, "model": model, "provider": self.defn.name}
            err = data.get("error", {}).get("message", str(data))
            return {"success": False, "error": f"API错误: {err}"}
        except Exception as e:
            return {"success": False, "error": f"连接异常: {e}"}

    def _generate_openai(self, prompt: str, model: str, capability: str,
                         temperature: float, max_tokens: int) -> dict:
        import requests
        base = self.api_base.rstrip("/")
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": model or self.defn.models[0] if self.defn.models else "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": f"你是一个{'翻译' if capability == 'translate' else '写作'}助手"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        data = resp.json()
        if resp.ok:
            content = data["choices"][0]["message"]["content"]
            return {"success": True, "content": content, "model": data.get("model", model), "provider": self.defn.name}
        return {"success": False, "error": str(data.get("error", {}).get("message", str(data)))}

    def _generate_anthropic(self, prompt: str, model: str, capability: str,
                            temperature: float, max_tokens: int) -> dict:
        import requests
        base = self.api_base.rstrip("/")
        resp = requests.post(
            f"{base}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model or (self.defn.models[0] if self.defn.models else "claude-sonnet-4-20250514"),
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        data = resp.json()
        if resp.ok:
            content = data["content"][0]["text"] if data.get("content") else ""
            return {"success": True, "content": content, "model": data.get("model", model), "provider": self.defn.name}
        return {"success": False, "error": str(data.get("error", {}).get("message", str(data)))}

    def _generate_gemini(self, prompt: str, model: str, capability: str,
                         temperature: float, max_tokens: int) -> dict:
        import requests
        base = self.api_base.rstrip("/")
        m = model or (self.defn.models[0] if self.defn.models else "gemini-2.0-flash")
        resp = requests.post(
            f"{base}/v1beta/models/{m}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
            },
            timeout=120,
        )
        data = resp.json()
        if resp.ok:
            content = data["candidates"][0]["content"]["parts"][0]["text"] if data.get("candidates") else ""
            return {"success": True, "content": content, "model": m, "provider": self.defn.name}
        return {"success": False, "error": str(data.get("error", {}).get("message", str(data)))}


# 快速创建适配器
def create_adapter(provider_name: str, api_key: str = "", api_base: str = "") -> Optional[UnifiedAIAdapter]:
    """根据供应商名称快速创建适配器"""
    reg = get_registry()
    defn = reg.get(provider_name)
    if not defn:
        return None
    return UnifiedAIAdapter(defn, api_key, api_base)
