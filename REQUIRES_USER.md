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

## 🟡 豆瓣 — 登录凭据（最新探索）
**文件**: `platform_reports/douban_exploration_report.json` ✅
**状态**: 🔍 预探索完成 (2026-07-08)
**需要**: 豆瓣账号（手机号 + 短信验证码 / 豆瓣App扫码）
- **推荐登录**: QR码扫码登录（无验证码）
- **备选**: 手机验证码登录
- **无密码登录** — 只有手机号+验证码方式
- **编辑器**: 日记/小组/豆列可发布
- **探索报告**: `platform_reports/douban_com.md` ✅
- **平台能力已入库**: `platform_config` ✅

## 🟡 WordPress — 站点配置
**文件**: `plugins/publisher_wordpress.py`
**状态**: ⏸ 框架就绪
**需要**: WordPress 站点 URL + Application Password

## 🟡 B站 — 登录凭据（优先队列 #1）
**文件**: `plugins/publisher_bilibili.py` + `sdk/adapters/bilibili.py`
**状态**: ⏸ Publisher + SDK 完整就绪 (v4.55)
**需要**: B站 Cookie（推荐）或 账号密码
- **推荐方式**: QR 码扫码登录（无需验证码）
  - B站 passport 提供 `/qrcode/generate` + `/qrcode/poll` API
  - 可通过统一弹窗 QR 码流程完成
- **备选方式**: 密码登录（需处理极验 Geetest 验证码）
- **Cookie 关键字段**: `SESSDATA` + `bili_jct` + `DedeUserID`
- **探索报告**: `platform_reports/bilibili.md` ✅
- **平台能力已入库**: `platform_config` ✅

## 🟡 微信公众号 — API 配置
**文件**: `plugins/publisher_wechat.py`
**状态**: ⏸ Publisher 完整就绪 (v4.57) — 含图片上传 + 封面支持 + 自动摘要
**需要**: 公众号 AppID + AppSecret
- **来源**: [微信公众平台](https://mp.weixin.qq.com) → 开发 → 基本配置
- **注意**: API 只能存草稿，正式发布需在手机微信上操作
- **探索报告**: `platform_reports/wechat_mp.md` ✅
- **平台能力已入库**: `platform_config` ✅

## 🟢 闲鱼 — 已有 Cookie (V2 MTOP)
**文件**: `plugins/publisher_xianyu_v2.py`
**状态**: MTOP 发布器就绪 (v4.39)，需测试 Cookie 有效性
**提示**: QR 扫码登录兜底已实现，可直接后台操作

## 🟢 Discuz/Amobbs/Mydigit — 已有 Cookie ✅
**状态**: E2E 验证通过 (v4.24-4.28)
