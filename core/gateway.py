"""FlashSloth — 通知网关核心

设计思路（移植自 Hermes Gateway）：
将消息通知抽象为统一的发送接口，对接多个终端平台。
每个平台一个 Provider 适配器，通过注册表发现。

消息流：
  notify() → Gateway.dispatch() → [Provider1.send(), Provider2.send(), ...]
                                   ↑
                             gateway_channels 表（存储每个终端的配置）

平台支持（当前）：
  - webhook: 通用 HTTP Webhook（最灵活）
  - feishu:  飞书/Lark 机器人
  - wecom:   企业微信机器人
  - wechat:  个人微信（iLink Bot API）
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from flashsloth.core.database import get_db

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════

@dataclass
class GatewayMessage:
    """统一网关消息格式"""
    title: str = ""
    body: str = ""
    level: str = "info"          # info | success | warn | error
    source: str = "system"       # 来源模块
    link: str = ""               # 点击跳转链接
    timestamp: str = ""
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "body": self.body,
            "level": self.level,
            "source": self.source,
            "link": self.link,
            "timestamp": self.timestamp or datetime.now().isoformat(),
        }


@dataclass
class ChannelConfig:
    """终端渠道配置"""
    id: int = 0
    name: str = ""
    platform: str = ""           # webhook | feishu | wecom | wechat | discord
    config_json: dict = field(default_factory=dict)
    enabled: bool = True
    user_id: int = 1
    created_at: str = ""


# ═══════════════════════════════════════════════
# Provider 基类
# ═══════════════════════════════════════════════

class GatewayProvider(ABC):
    """Provider 基类 — 每个终端平台继承此类"""
    
    name: str = ""               # 唯一标识
    display_name: str = ""       # 显示名
    icon: str = "🔌"             # 图标
    description: str = ""        # 描述
    
    # 配置字段定义（供UI自动渲染）
    config_fields: list[dict] = field(default_factory=list)
    
    @abstractmethod
    def send(self, message: GatewayMessage, config: dict) -> dict:
        """发送消息到该终端
        
        返回:
            {"success": True, "message_id": "..."} 或
            {"success": False, "error": "..."}
        """
        ...
    
    def validate_config(self, config: dict) -> tuple[bool, str]:
        """验证配置是否有效，默认检查必要字段"""
        required = [f["key"] for f in self.config_fields if f.get("required")]
        missing = [k for k in required if not config.get(k)]
        if missing:
            return False, f"缺少必要字段: {', '.join(missing)}"
        return True, ""


# ═══════════════════════════════════════════════
# 具体 Provider 实现
# ═══════════════════════════════════════════════

class WebhookProvider(GatewayProvider):
    """通用 Webhook — 最灵活的终端，直接 HTTP POST"""
    name = "webhook"
    display_name = "Webhook"
    icon = "🔗"
    description = "通用 HTTP Webhook，支持任意接收端"
    config_fields = [
        {"key": "url", "label": "Webhook URL", "type": "url", "required": True,
         "placeholder": "https://hooks.example.com/notify"},
        {"key": "secret", "label": "签名密钥（可选）", "type": "password",
         "placeholder": "用于 HMAC 签名"},
        {"key": "method", "label": "请求方法", "type": "select", "default": "POST",
         "options": [{"value": "POST", "label": "POST"}, {"value": "PUT", "label": "PUT"}]},
        {"key": "format", "label": "消息格式", "type": "select", "default": "json",
         "options": [{"value": "json", "label": "JSON"}, {"value": "form", "label": "Form"}]},
    ]
    
    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("url", "")
        if not url:
            return {"success": False, "error": "Webhook URL 未配置"}
        
        import urllib.request
        payload = json.dumps(message.to_dict(), ensure_ascii=False).encode()
        secret = config.get("secret", "")
        
        headers = {"Content-Type": "application/json"}
        if secret:
            import hmac
            sig = hmac.new(secret.encode(), payload, "sha256").hexdigest()
            headers["X-Signature"] = sig
        
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method=config.get("method", "POST"))
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status, "message_id": str(int(time.time()))}
        except Exception as e:
            return {"success": False, "error": str(e)}


class FeishuProvider(GatewayProvider):
    """飞书/Lark 机器人"""
    name = "feishu"
    display_name = "飞书"
    icon = "✈️"
    description = "飞书/Lark 群机器人 Webhook"
    config_fields = [
        {"key": "webhook_url", "label": "飞书 Webhook URL", "type": "url", "required": True,
         "placeholder": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"},
        {"key": "secret", "label": "签名密钥（可选）", "type": "password",
         "placeholder": "飞书机器人安全设置中的签名密钥"},
    ]
    
    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "飞书 Webhook URL 未配置"}
        
        import urllib.request
        import hashlib, base64
        
        # 构建飞书消息卡片
        level_colors = {"info": "blue", "success": "green", "warn": "orange", "error": "red"}
        color = level_colors.get(message.level, "blue")
        
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": message.title},
                      "template": color},
            "elements": []
        }
        
        if message.body:
            card["elements"].append({"tag": "div", "text": {"tag": "lark_md", "content": message.body}})
        if message.source:
            card["elements"].append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"来源: {message.source}"}]})
        if message.link:
            card["elements"].append({"tag": "action", "actions": [{
                "tag": "button", "text": {"tag": "plain_text", "content": "查看详情"},
                "url": message.link, "type": "default"
            }]})
        
        payload = {"msg_type": "interactive", "card": card}
        
        # 签名
        secret = config.get("secret", "")
        if secret:
            ts = str(int(time.time()))
            string_to_sign = ts + "\n" + secret
            sign = base64.b64encode(hashlib.sha256(string_to_sign.encode()).digest()).decode()
            payload["timestamp"] = ts
            payload["sign"] = sign
        
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status, "message_id": str(int(time.time()))}
        except Exception as e:
            return {"success": False, "error": str(e)}


class WeComProvider(GatewayProvider):
    """企业微信机器人"""
    name = "wecom"
    display_name = "企业微信"
    icon = "💼"
    description = "企业微信群机器人 Webhook"
    config_fields = [
        {"key": "webhook_url", "label": "企微 Webhook URL", "type": "url", "required": True,
         "placeholder": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"},
    ]
    
    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "企微 Webhook URL 未配置"}
        
        import urllib.request
        
        # 企微支持 Markdown 消息
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")
        
        content = f"{icon} **{message.title}**\n"
        if message.body:
            content += f">{message.body}\n"
        if message.source:
            content += f">来源: {message.source}\n"
        if message.link:
            content += f">[查看详情]({message.link})"
        
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"}, method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status, "message_id": str(int(time.time()))}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════
# Provider 注册表
# ═══════════════════════════════════════════════

_providers: dict[str, GatewayProvider] = {}

def register_provider(provider: GatewayProvider):
    """注册 Provider"""
    _providers[provider.name] = provider

def get_provider(name: str) -> Optional[GatewayProvider]:
    return _providers.get(name)

def list_providers() -> list[GatewayProvider]:
    return list(_providers.values())

# 注册内置 Provider
register_provider(WebhookProvider())
register_provider(FeishuProvider())
register_provider(WeComProvider())


# ═══════════════════════════════════════════════
# 网关调度器
# ═══════════════════════════════════════════════

class Gateway:
    """通知网关调度器 — 负责消息路由和派发"""
    
    def __init__(self):
        self._channel_cache = None
        self._cache_time = 0
    
    def _load_channels(self, force: bool = False) -> list[ChannelConfig]:
        """从数据库加载渠道列表"""
        now = time.time()
        if self._channel_cache and not force and (now - self._cache_time) < 30:
            return self._channel_cache
        
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT * FROM gateway_channels WHERE enabled=1 ORDER BY platform"
            ).fetchall()
            conn.close()
            channels = []
            for r in rows:
                try:
                    cfg = json.loads(r["config_json"]) if isinstance(r["config_json"], str) else {}
                except:
                    cfg = {}
                channels.append(ChannelConfig(
                    id=r["id"], name=r["name"], platform=r["platform"],
                    config_json=cfg, enabled=bool(r["enabled"]),
                    user_id=r["user_id"], created_at=r.get("created_at", ""),
                ))
            self._channel_cache = channels
            self._cache_time = now
            return channels
        except Exception as e:
            logger.error(f"加载渠道失败: {e}")
            return []
    
    def dispatch(self, message: GatewayMessage) -> list[dict]:
        """将消息派发到所有启用的渠道
        
        返回每个渠道的发送结果列表
        """
        channels = self._load_channels()
        if not channels:
            return [{"success": False, "error": "没有已启用的通知渠道，请先在网关配置页面添加"}]
        
        results = []
        for ch in channels:
            provider = get_provider(ch.platform)
            if not provider:
                results.append({"channel": ch.name, "success": False,
                              "error": f"不支持的平台: {ch.platform}"})
                continue
            
            try:
                result = provider.send(message, ch.config_json)
                result["channel"] = ch.name
                result["platform"] = ch.platform
                results.append(result)
            except Exception as e:
                results.append({"channel": ch.name, "success": False, "error": str(e)})
        
        return results
    
    def test_channel(self, channel_id: int) -> dict:
        """测试指定渠道是否可达"""
        try:
            conn = get_db()
            row = conn.execute(
                "SELECT * FROM gateway_channels WHERE id=?", (channel_id,)
            ).fetchone()
            conn.close()
            if not row:
                return {"success": False, "error": "渠道不存在"}
            
            try:
                cfg = json.loads(row["config_json"]) if isinstance(row["config_json"], str) else {}
            except:
                cfg = {}
            
            provider = get_provider(row["platform"])
            if not provider:
                return {"success": False, "error": f"不支持的平台: {row['platform']}"}
            
            test_msg = GatewayMessage(
                title="🔔 FlashSloth 网关测试",
                body="这是一条测试消息，如果您收到此消息说明通知网关配置正确 ✅",
                level="info",
                source="gateway",
            )
            result = provider.send(test_msg, cfg)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}


# 全局单例
_gateway = None

def get_gateway() -> Gateway:
    global _gateway
    if _gateway is None:
        _gateway = Gateway()
    return _gateway


# ═══════════════════════════════════════════════
# 快捷发送接口（对接现有 notifier.py）
# ═══════════════════════════════════════════════

def gateway_send(
    title: str,
    body: str = "",
    level: str = "info",
    source: str = "system",
    link: str = "",
) -> list[dict]:
    """通过网关发送消息到所有绑定的终端"""
    msg = GatewayMessage(
        title=title, body=body, level=level,
        source=source, link=link,
        timestamp=datetime.now().isoformat(),
    )
    return get_gateway().dispatch(msg)
