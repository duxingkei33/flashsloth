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

class TelegramProvider(GatewayProvider):
    """Telegram Bot — 通过 Bot API 发送消息"""
    name = "telegram"
    display_name = "Telegram"
    icon = "✈️"
    description = "Telegram Bot API 消息通知"
    config_fields = [
        {"key": "bot_token", "label": "Bot Token", "type": "password", "required": True,
         "placeholder": "123456:ABCdef..."},
        {"key": "chat_id", "label": "聊天ID / Channel ID", "type": "text", "required": True,
         "placeholder": "-1001234567890"},
        {"key": "parse_mode", "label": "解析模式", "type": "select", "default": "HTML",
         "options": [{"value": "HTML", "label": "HTML"}, {"value": "MarkdownV2", "label": "MarkdownV2"}, {"value": "text", "label": "纯文本"}]},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        token = config.get("bot_token", "")
        chat_id = config.get("chat_id", "")
        if not token or not chat_id:
            return {"success": False, "error": "Bot Token 或 Chat ID 未配置"}
        import urllib.request
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")
        text = f"<b>{icon} {message.title}</b>\n"
        if message.body:
            text += f"{message.body}\n"
        if message.source:
            text += f"\n🔹 <i>{message.source}</i>"
        mode = config.get("parse_mode", "HTML")
        payload = {"chat_id": chat_id, "text": text, "parse_mode": mode, "disable_web_page_preview": True}
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class DiscordProvider(GatewayProvider):
    """Discord Webhook — 通过 Discord Webhook 发送消息"""
    name = "discord"
    display_name = "Discord"
    icon = "🎮"
    description = "Discord 频道 Webhook"
    config_fields = [
        {"key": "webhook_url", "label": "Discord Webhook URL", "type": "url", "required": True,
         "placeholder": "https://discord.com/api/webhooks/..."},
        {"key": "username", "label": "机器人名称（可选）", "type": "text", "placeholder": "FlashSloth Bot"},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "Discord Webhook URL 未配置"}
        import urllib.request
        level_colors = {"info": 0x3498db, "success": 0x2ecc71, "warn": 0xf39c12, "error": 0xe74c3c}
        embed = {"title": message.title, "description": message.body, "color": level_colors.get(message.level, 0x3498db)}
        if message.source:
            embed["footer"] = {"text": f"来源: {message.source}"}
        payload = {"embeds": [embed]}
        if config.get("username"):
            payload["username"] = config["username"]
        try:
            req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SlackProvider(GatewayProvider):
    """Slack Webhook — 通过 Slack Incoming Webhook 发送"""
    name = "slack"
    display_name = "Slack"
    icon = "💬"
    description = "Slack 频道 Incoming Webhook"
    config_fields = [
        {"key": "webhook_url", "label": "Slack Webhook URL", "type": "url", "required": True,
         "placeholder": "https://hooks.slack.com/services/..."},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "Slack Webhook URL 未配置"}
        import urllib.request
        level_icons = {"info": ":information_source:", "success": ":white_check_mark:", "warn": ":warning:", "error": ":x:"}
        icon = level_icons.get(message.level, ":information_source:")
        text = f"{icon} *{message.title}*\n{message.body}"
        if message.source:
            text += f"\n_来源: {message.source}_"
        payload = {"text": text}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}



# ═══════════════════════════════════════════════
# 新增 Provider（移植自 Hermes Agent）
# ═══════════════════════════════════════════════


class WhatsAppProvider(GatewayProvider):
    """WhatsApp Business Cloud API"""
    name = "whatsapp"
    display_name = "WhatsApp"
    icon = "💬"
    description = "WhatsApp Business Cloud API 发送消息"
    config_fields = [
        {"key": "access_token", "label": "永久 Access Token", "type": "password", "required": True,
         "placeholder": "EAAx..."},
        {"key": "phone_number_id", "label": "发件号码 ID", "type": "text", "required": True,
         "placeholder": "123456789012345"},
        {"key": "to", "label": "目标号码（含国家码）", "type": "text", "required": True,
         "placeholder": "8613800138000"},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        token = config.get("access_token", "")
        phone_id = config.get("phone_number_id", "")
        to = config.get("to", "")
        if not token or not phone_id or not to:
            return {"success": False, "error": "WhatsApp 配置不完整"}
        import urllib.request
        body_text = f"{message.title}\n\n{message.body}" if message.body else message.title
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body_text},
        }
        try:
            req = urllib.request.Request(
                f"https://graph.facebook.com/v18.0/{phone_id}/messages",
                data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class DingTalkProvider(GatewayProvider):
    """钉钉机器人 Webhook"""
    name = "dingtalk"
    display_name = "钉钉"
    icon = "🔔"
    description = "钉钉群机器人 Webhook"
    config_fields = [
        {"key": "webhook_url", "label": "钉钉 Webhook URL", "type": "url", "required": True,
         "placeholder": "https://oapi.dingtalk.com/robot/send?access_token=xxx"},
        {"key": "secret", "label": "加签密钥（可选）", "type": "password",
         "placeholder": "SEC..."},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "钉钉 Webhook URL 未配置"}
        import urllib.request
        import hashlib, base64, time as time_mod, hmac
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")
        content = f"{icon} **{message.title}**\n{message.body or ''}"
        if message.source:
            content += f"\n\n_来源: {message.source}_"
        payload = {"msgtype": "markdown", "markdown": {"title": message.title[:50], "text": content}}
        secret = config.get("secret", "")
        if secret:
            ts = str(int(time_mod.time() * 1000))
            string_to_sign = f"{ts}\n{secret}"
            sign = base64.b64encode(hmac.new(secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256).digest()).decode()
            url = f"{url}&timestamp={ts}&sign={sign}"
        try:
            req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class WeChatProvider(GatewayProvider):
    """个人微信（通过 iLink Bot API 或 WeChat Ferret / 企业微信通道）"""
    name = "wechat"
    display_name = "微信"
    icon = "💚"
    description = "微信个人号通知（通过 iLink Bot API 或企业微信应用消息）"
    config_fields = [
        {"key": "mode", "label": "接入方式", "type": "select", "required": True,
         "options": [{"value": "qywx_app", "label": "企业微信应用消息"},
                     {"value": "ilink", "label": "iLink Bot API"}],
         "default": "qywx_app"},
        {"key": "corpid", "label": "企业 ID（企业微信模式）", "type": "text", "placeholder": "ww..."},
        {"key": "corpsecret", "label": "应用 Secret（企业微信模式）", "type": "password", "placeholder": "..."},
        {"key": "agentid", "label": "应用 AgentId（企业微信模式）", "type": "text", "placeholder": "1000002"},
        {"key": "touser", "label": "接收人（@all 或 UserID）", "type": "text", "placeholder": "@all"},
        {"key": "api_url", "label": "iLink API URL", "type": "url", "placeholder": "http://localhost:8066/..."},
        {"key": "to_wxid", "label": "接收人 wxid（iLink模式）", "type": "text", "placeholder": "wxid_..."},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        mode = config.get("mode", "qywx_app")
        if mode == "qywx_app":
            return self._send_qywx_app(message, config)
        elif mode == "ilink":
            return self._send_ilink(message, config)
        return {"success": False, "error": f"未知模式: {mode}"}

    def _send_ilink(self, message: GatewayMessage, config: dict) -> dict:
        """通过 iLink Bot API 发送消息到微信个人号"""
        api_url = config.get("api_url", "").rstrip("/")
        to_wxid = config.get("to_wxid", "")
        if not api_url:
            return {"success": False, "error": "iLink API URL 未配置"}
        import urllib.request
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")
        content = f"{icon} {message.title}\n{message.body or ''}"
        if message.source:
            content += f"\n🔹 {message.source}"
        if message.link:
            content += f"\n🔗 {message.link}"
        try:
            payload = json.dumps({"to_wxid": to_wxid, "content": content}, ensure_ascii=False).encode()
            req = urllib.request.Request(
                f"{api_url}/send_text",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=15)
            resp_data = json.loads(resp.read())
            if resp_data.get("code") == 0 or resp_data.get("success"):
                return {"success": True, "message_id": str(resp_data.get("msg_id", ""))}
            return {"success": True, "status": resp.status}
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode()
                return {"success": False, "error": f"iLink 发送失败 (HTTP {e.code}): {err_body[:200]}"}
            except Exception:
                return {"success": False, "error": f"iLink 发送失败 (HTTP {e.code})"}
        except Exception as e:
            return {"success": False, "error": f"iLink 发送异常: {e}"}

    def _send_qywx_app(self, message: GatewayMessage, config: dict) -> dict:
        corpid = config.get("corpid", "")
        corpsecret = config.get("corpsecret", "")
        agentid = config.get("agentid", "")
        touser = config.get("touser", "@all")
        if not corpid or not corpsecret or not agentid:
            return {"success": False, "error": "企业微信应用配置不完整"}
        import urllib.request
        try:
            # 获取 access_token
            token_req = urllib.request.Request(
                f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}")
            token_resp = json.loads(urllib.request.urlopen(token_req, timeout=10).read())
            access_token = token_resp.get("access_token", "")
            if not access_token:
                return {"success": False, "error": f"获取 token 失败: {token_resp.get('errmsg', '')}"}
            level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
            icon = level_icons.get(message.level, "ℹ️")
            content = f"{icon} {message.title}\n{message.body or ''}"
            if message.link:
                content += f"\n<a href='{message.link}'>查看详情</a>"
            payload = {
                "touser": touser, "msgtype": "text", "agentid": int(agentid),
                "text": {"content": content},
            }
            req = urllib.request.Request(
                f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}",
                data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
            if resp.get("errcode") == 0:
                return {"success": True, "message_id": str(resp.get("msgid", ""))}
            return {"success": False, "error": f"发送失败: {resp.get('errmsg', '')}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class EmailProvider(GatewayProvider):
    """Email (SMTP)"""
    name = "email"
    display_name = "邮件"
    icon = "📧"
    description = "通过 SMTP 发送邮件通知"
    config_fields = [
        {"key": "smtp_host", "label": "SMTP 服务器", "type": "text", "required": True,
         "placeholder": "smtp.gmail.com"},
        {"key": "smtp_port", "label": "端口", "type": "text", "required": True, "default": "587",
         "placeholder": "587"},
        {"key": "use_tls", "label": "使用 TLS", "type": "select", "default": "true",
         "options": [{"value": "true", "label": "是"}, {"value": "false", "label": "否"}]},
        {"key": "username", "label": "用户名", "type": "text", "required": True},
        {"key": "password", "label": "密码/App Password", "type": "password", "required": True},
        {"key": "from_addr", "label": "发件地址", "type": "text", "required": True},
        {"key": "to_addr", "label": "收件地址", "type": "text", "required": True},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        host = config.get("smtp_host", "")
        port = int(config.get("smtp_port", 587))
        use_tls = config.get("use_tls", "true") == "true"
        username = config.get("username", "")
        password = config.get("password", "")
        from_addr = config.get("from_addr", "")
        to_addr = config.get("to_addr", "")
        if not host or not username or not password or not to_addr:
            return {"success": False, "error": "SMTP 配置不完整"}
        try:
            import smtplib
            from email.mime.text import MIMEText
            body = f"{message.title}\n\n{message.body or ''}"
            if message.source:
                body += f"\n\n来源: {message.source}"
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = message.title
            msg["From"] = from_addr
            msg["To"] = to_addr
            if use_tls:
                server = smtplib.SMTP(host, port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(host, port) if port == 465 else smtplib.SMTP(host, port)
            server.login(username, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
            server.quit()
            return {"success": True, "message_id": str(int(time.time()))}
        except Exception as e:
            return {"success": False, "error": str(e)}


class MatrixProvider(GatewayProvider):
    """Matrix 协议"""
    name = "matrix"
    display_name = "Matrix"
    icon = "🧩"
    description = "Matrix 协议消息通知"
    config_fields = [
        {"key": "homeserver", "label": "Homeserver URL", "type": "url", "required": True,
         "placeholder": "https://matrix.org"},
        {"key": "access_token", "label": "Access Token", "type": "password", "required": True},
        {"key": "room_id", "label": "房间 ID", "type": "text", "required": True,
         "placeholder": "!roomid:matrix.org"},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        hs = config.get("homeserver", "").rstrip("/")
        token = config.get("access_token", "")
        room = config.get("room_id", "")
        if not hs or not token or not room:
            return {"success": False, "error": "Matrix 配置不完整"}
        import urllib.request
        import urllib.parse
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")
        body = f"{icon} **{message.title}**\n\n{message.body or ''}"
        payload = {"msgtype": "m.text", "body": f"{icon} {message.title}\n{message.body or ''}",
                   "format": "org.matrix.custom.html", "formatted_body": body.replace('\n', '<br>')}
        try:
            req = urllib.request.Request(
                f"{hs}/_matrix/client/r0/rooms/{urllib.parse.quote(room, safe='')}/send/m.room.message",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class TeamsProvider(GatewayProvider):
    """Microsoft Teams Webhook"""
    name = "teams"
    display_name = "Microsoft Teams"
    icon = "💼"
    description = "Teams 频道 Webhook"
    config_fields = [
        {"key": "webhook_url", "label": "Teams Webhook URL", "type": "url", "required": True,
         "placeholder": "https://outlook.office.com/webhook/..."},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "Teams Webhook URL 未配置"}
        import urllib.request
        level_colors = {"info": "0078D7", "success": "28A745", "warn": "FFC107", "error": "DC3545"}
        color = level_colors.get(message.level, "0078D7")
        sections = [{"activityTitle": message.title, "text": message.body or "", "activitySubtitle": f"来源: {message.source}" if message.source else ""}]
        payload = {"@type": "MessageCard", "@context": "http://schema.org/extensions",
                   "themeColor": color, "summary": message.title, "sections": sections}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class LINEProvider(GatewayProvider):
    """LINE Notify / Messaging API"""
    name = "line"
    display_name = "LINE"
    icon = "💚"
    description = "LINE 消息通知（支持 Notify 和 Messaging API）"
    config_fields = [
        {"key": "mode", "label": "模式", "type": "select", "required": True,
         "options": [{"value": "notify", "label": "LINE Notify"},
                     {"value": "messaging", "label": "Messaging API"}],
         "default": "notify"},
        {"key": "token", "label": "Access Token / Channel Token", "type": "password", "required": True},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        mode = config.get("mode", "notify")
        token = config.get("token", "")
        if not token:
            return {"success": False, "error": "LINE Token 未配置"}
        import urllib.request
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")

        if mode == "notify":
            try:
                payload = urllib.parse.urlencode({"message": f"{icon} {message.title}\n{message.body or ''}"}).encode()
                req = urllib.request.Request("https://notify-api.line.me/api/notify", data=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"},
                    method="POST")
                resp = urllib.request.urlopen(req, timeout=15)
                return {"success": True, "status": resp.status}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            try:
                payload = json.dumps({"messages": [{"type": "text", "text": f"{icon} {message.title}\n{message.body or ''}"}]}).encode()
                req = urllib.request.Request("https://api.line.me/v2/bot/message/broadcast", data=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    method="POST")
                resp = urllib.request.urlopen(req, timeout=15)
                return {"success": True, "status": resp.status}
            except Exception as e:
                return {"success": False, "error": str(e)}


class MattermostProvider(GatewayProvider):
    """Mattermost Webhook"""
    name = "mattermost"
    display_name = "Mattermost"
    icon = "🔷"
    description = "Mattermost Incoming Webhook"
    config_fields = [
        {"key": "webhook_url", "label": "Webhook URL", "type": "url", "required": True,
         "placeholder": "https://mattermost.example.com/hooks/xxx"},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "Mattermost Webhook URL 未配置"}
        import urllib.request
        level_icons = {"info": ":information_source:", "success": ":white_check_mark:", "warn": ":warning:", "error": ":x:"}
        icon = level_icons.get(message.level, ":information_source:")
        text = f"{icon} **{message.title}**\n\n{message.body or ''}"
        payload = {"text": text}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class GoogleChatProvider(GatewayProvider):
    """Google Chat Webhook"""
    name = "google_chat"
    display_name = "Google Chat"
    icon = "💬"
    description = "Google Chat Webhook 通知"
    config_fields = [
        {"key": "webhook_url", "label": "Webhook URL", "type": "url", "required": True,
         "placeholder": "https://chat.googleapis.com/v1/spaces/.../messages"},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "Google Chat Webhook URL 未配置"}
        import urllib.request
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")
        text = f"{icon} <b>{message.title}</b>\n{message.body or ''}"
        payload = {"text": text}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class QQBotProvider(GatewayProvider):
    """QQ 频道机器人 / QQ 群机器人"""
    name = "qqbot"
    display_name = "QQ Bot"
    icon = "🐧"
    description = "QQ 机器人消息通知（QQ 频道 / 群机器人）"
    config_fields = [
        {"key": "mode", "label": "模式", "type": "select", "required": True,
         "options": [{"value": "channel", "label": "QQ 频道"},
                     {"value": "group", "label": "QQ 群"}],
         "default": "channel"},
        {"key": "appid", "label": "Bot AppID", "type": "text", "required": True},
        {"key": "token", "label": "Bot Token", "type": "password", "required": True},
        {"key": "channel_id", "label": "频道 ID / 群 ID", "type": "text", "required": True},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        appid = config.get("appid", "")
        token = config.get("token", "")
        channel_id = config.get("channel_id", "")
        if not appid or not token or not channel_id:
            return {"success": False, "error": "QQ Bot 配置不完整"}
        import urllib.request
        level_icons = {"info": "ℹ️", "success": "✅", "warn": "⚠️", "error": "❌"}
        icon = level_icons.get(message.level, "ℹ️")
        content = f"{icon}{message.title}\n{message.body or ''}"
        payload = {"content": content}
        try:
            req = urllib.request.Request(
                f"https://api.sgroup.qq.com/channels/{channel_id}/messages",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bot {appid}.{token}", "Content-Type": "application/json"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ntfyProvider(GatewayProvider):
    """ntfy.sh — 轻量级推送通知"""
    name = "ntfy"
    display_name = "ntfy"
    icon = "🔔"
    description = "ntfy.sh 轻量级推送通知"
    config_fields = [
        {"key": "topic", "label": "Topic", "type": "text", "required": True,
         "placeholder": "my_notifications"},
        {"key": "server", "label": "服务器（可选）", "type": "url", "default": "https://ntfy.sh",
         "placeholder": "https://ntfy.sh"},
        {"key": "priority", "label": "优先级", "type": "select", "default": "3",
         "options": [{"value": "1", "label": "1-最低"}, {"value": "2", "label": "2-低"},
                     {"value": "3", "label": "3-普通"}, {"value": "4", "label": "4-高"}, {"value": "5", "label": "5-紧急"}]},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        topic = config.get("topic", "")
        server = (config.get("server") or "https://ntfy.sh").rstrip("/")
        if not topic:
            return {"success": False, "error": "ntfy Topic 未配置"}
        import urllib.request
        priority_map = {"info": "3", "success": "3", "warn": "4", "error": "5"}
        priority = config.get("priority", priority_map.get(message.level, "3"))
        try:
            payload = f"{message.title}\n{message.body or ''}".encode()
            req = urllib.request.Request(f"{server}/{topic}", data=payload,
                headers={"Title": message.title[:100], "Priority": priority,
                         "Tags": "flashsloth", "Content-Type": "text/plain"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class HomeAssistantProvider(GatewayProvider):
    """Home Assistant 通知"""
    name = "home_assistant"
    display_name = "Home Assistant"
    icon = "🏠"
    description = "通过 Home Assistant 的 notify 服务发送通知"
    config_fields = [
        {"key": "ha_url", "label": "HA 服务器 URL", "type": "url", "required": True,
         "placeholder": "http://homeassistant.local:8123"},
        {"key": "token", "label": "Long-Lived Access Token", "type": "password", "required": True},
        {"key": "service", "label": "Notify 服务名", "type": "text", "default": "notify.mobile_app_phone",
         "placeholder": "notify.mobile_app_xxx"},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        ha_url = config.get("ha_url", "").rstrip("/")
        token = config.get("token", "")
        service = config.get("service", "notify.mobile_app_phone")
        if not ha_url or not token:
            return {"success": False, "error": "Home Assistant 配置不完整"}
        import urllib.request
        level_map = {"info": "info", "success": "success", "warn": "warning", "error": "error"}
        level = level_map.get(message.level, "info")
        payload = {
            "service": service,
            "data": {"title": message.title, "message": message.body or "",
                     "data": {"tag": "flashsloth", "priority": "high", "level": level,
                              "url": message.link or ""}},
        }
        try:
            req = urllib.request.Request(f"{ha_url}/api/services/notify/{service}",
                data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SignalProvider(GatewayProvider):
    """Signal 消息（signal-cli HTTP 接口）"""
    name = "signal"
    display_name = "Signal"
    icon = "🔒"
    description = "通过 signal-cli REST API 发送消息"
    config_fields = [
        {"key": "signal_url", "label": "signal-cli HTTP URL", "type": "url", "required": True,
         "placeholder": "http://127.0.0.1:8080"},
        {"key": "account", "label": "Signal 账号（手机号）", "type": "text", "required": True,
         "placeholder": "+8613800138000"},
        {"key": "recipient", "label": "接收者（手机号或 Group ID）", "type": "text", "required": True},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("signal_url", "").rstrip("/")
        account = config.get("account", "")
        recipient = config.get("recipient", "")
        if not url or not account or not recipient:
            return {"success": False, "error": "Signal 配置不完整"}
        import urllib.request
        body = f"{message.title}\n\n{message.body or ''}"
        try:
            payload = json.dumps({"message": body, "number": account, "recipients": [recipient]}).encode()
            req = urllib.request.Request(f"{url}/v2/send",
                data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=30)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SimpleXProvider(GatewayProvider):
    """SimpleX Chat 通知"""
    name = "simplex"
    display_name = "SimpleX"
    icon = "🟣"
    description = "SimpleX Chat 消息通知"
    config_fields = [
        {"key": "webhook_url", "label": "SimpleX Bot Webhook URL", "type": "url", "required": True},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        url = config.get("webhook_url", "")
        if not url:
            return {"success": False, "error": "SimpleX Webhook URL 未配置"}
        import urllib.request
        payload = json.dumps({"text": f"{message.title}\n{message.body or ''}"}).encode()
        try:
            req = urllib.request.Request(url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SMSProvider(GatewayProvider):
    """SMS 短信通知（通用 HTTP API）"""
    name = "sms"
    display_name = "短信"
    icon = "📱"
    description = "通过 SMS API 网关发送短信"
    config_fields = [
        {"key": "api_url", "label": "SMS API URL", "type": "url", "required": True},
        {"key": "api_key", "label": "API Key", "type": "password", "required": True},
        {"key": "phone", "label": "目标手机号", "type": "text", "required": True},
        {"key": "template", "label": "消息模板（{title} 和 {body} 会被替换）", "type": "text",
         "default": "【FlashSloth】{title}: {body}",
         "placeholder": "【FlashSloth】{title}: {body}"},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        api_url = config.get("api_url", "")
        api_key = config.get("api_key", "")
        phone = config.get("phone", "")
        if not api_url or not api_key or not phone:
            return {"success": False, "error": "SMS 配置不完整"}
        import urllib.request
        template = config.get("template", "【FlashSloth】{title}: {body}")
        text = template.replace("{title}", message.title).replace("{body}", message.body or "")
        payload = json.dumps({"phone": phone, "message": text, "api_key": api_key}).encode()
        try:
            req = urllib.request.Request(api_url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


class iMessageProvider(GatewayProvider):
    """iMessage / BlueBubbles"""
    name = "imessage"
    display_name = "iMessage"
    icon = "💬"
    description = "通过 BlueBubbles API 发送 iMessage"
    config_fields = [
        {"key": "api_url", "label": "BlueBubbles API URL", "type": "url", "required": True,
         "placeholder": "http://127.0.0.1:1234"},
        {"key": "password", "label": "API Password", "type": "password", "required": True},
        {"key": "chat_guid", "label": "聊天 GUID", "type": "text", "required": True},
    ]

    def send(self, message: GatewayMessage, config: dict) -> dict:
        api_url = config.get("api_url", "").rstrip("/")
        password = config.get("password", "")
        chat_guid = config.get("chat_guid", "")
        if not api_url or not password or not chat_guid:
            return {"success": False, "error": "iMessage 配置不完整"}
        import urllib.request
        body = f"{message.title}\n\n{message.body or ''}"
        payload = json.dumps({"chatGuid": chat_guid, "text": body}).encode()
        try:
            req = urllib.request.Request(f"{api_url}/api/v1/chat/send",
                data=payload,
                headers={"password": password, "Content-Type": "application/json"},
                method="POST")
            resp = urllib.request.urlopen(req, timeout=30)
            return {"success": True, "status": resp.status}
        except Exception as e:
            return {"success": False, "error": str(e)}


# 注册内置 Provider
register_provider(WebhookProvider())
register_provider(FeishuProvider())
register_provider(WeComProvider())
register_provider(TelegramProvider())
register_provider(DiscordProvider())
register_provider(SlackProvider())
register_provider(WhatsAppProvider())
register_provider(DingTalkProvider())
register_provider(WeChatProvider())
register_provider(EmailProvider())
register_provider(MatrixProvider())
register_provider(TeamsProvider())
register_provider(LINEProvider())
register_provider(MattermostProvider())
register_provider(GoogleChatProvider())
register_provider(QQBotProvider())
register_provider(ntfyProvider())
register_provider(HomeAssistantProvider())
register_provider(SignalProvider())
register_provider(SimpleXProvider())
register_provider(SMSProvider())
register_provider(iMessageProvider())


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
