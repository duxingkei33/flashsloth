# Requis: User Action Required

## 🔴 Twitter/X — API 凭证
**文件**: `plugins/publisher_twitter.py`
**状态**: ⏸ 框架就绪，缺凭证
**需要提供**:
- API Key + API Secret
- Access Token + Access Token Secret
- Bearer Token（只读用）
- 来源: [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)

## 🟡 知乎 — 登录凭据
**文件**: `plugins/publisher_zhihu.py`
**状态**: ⏸ Playwright 发布器已就绪 ✅ (v4.33)
**需要**: 知乎账号密码 + 手机号（用于扫码/验证码兜底）

## 🟡 掘金 — 登录凭据
**文件**: `plugins/publisher_juejin.py`
**状态**: ⏸ 框架就绪
**需要**: 掘金 Cookie / 账号密码

## 🟡 WordPress — 站点配置
**文件**: `plugins/publisher_wordpress.py`
**状态**: ⏸ 框架就绪
**需要**: WordPress 站点 URL + Application Password

## 🟡 B站 — 登录凭据
**文件**: `plugins/publisher_bilibili.py`
**状态**: ⏸ 框架就绪
**需要**: B站 Cookie / 账号密码

## 🟡 微信公众号 — API 配置
**文件**: `plugins/publisher_wechat.py`
**状态**: ⏸ 框架就绪，需研究素材 API
**需要**: 公众号 AppID + AppSecret

## 🟢 闲鱼 — 已有 Cookie (V2 MTOP)
**文件**: `plugins/publisher_xianyu_v2.py`
**状态**: MTOP 发布器就绪 (v4.39)，需测试 Cookie 有效性
**提示**: QR 扫码登录兜底已实现，可直接后台操作

## 🟢 Discuz/Amobbs/Mydigit — 已有 Cookie ✅
**状态**: E2E 验证通过 (v4.24-4.28)
