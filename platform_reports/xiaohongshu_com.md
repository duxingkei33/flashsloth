# 平台探索报告：小红书 (xiaohongshu.com)

> **探索时间**: 2026-07-07 23:41 CST
> **探索方式**: Playwright 预探索（无凭证）
> **账号状态**: ❌ 无账号，需用户提供
> **站点**: https://www.xiaohongshu.com

## 1. 登录方式

| 方式 | 支持 | 说明 |
|------|------|------|
| 手机验证码 | ✅ | 默认 Tab，输入手机号 + 验证码 |
| 扫码登录 | ✅ | 发现 qrcode 选项（需进一步确认） |
| 密码登录 | ❌（默认不可见） | 可能需切换 Tab |
| 微信登录 | ❌（默认不可见） | 可能需切换 Tab |
| 微博登录 | ❌（默认不可见） | 可能需切换 Tab |
| QQ 登录 | ❌（默认不可见） | 可能需切换 Tab |

### CAPTCHA 检测
- 极验(Geetest): ❌ 未检测到
- 网易盾: ❌ 未检测到
- 其他验证码: ❌ 未检测到
- **小红书 CAPTCHA**: 发现 `edith.xiaohongshu.com/api/redcaptcha/v2/getconfig` — 存在自研验证码系统 (redcaptcha)

### 登录字段
- `input[name=xhs-pc-web-phone]` — 手机号输入
- `input[type=number]` — 验证码输入
- 按钮: 「登录」

## 2. 编辑器访问
- 编辑器 URL 猜测: `/editor` → 返回 404（非登录重定向，而是直接404）
- 可能需要其他 URL 路径
- 笔记编辑可能通过 SPA 路由实现

## 3. API 端点

### 安全/验证
- `as.xiaohongshu.com/api/sec/v1/ds?appId=xhs-pc-web` — 安全签名
- `as.xiaohongshu.com/api/sec/v1/sbtsource` — 安全
- `as.xiaohongshu.com/api/sec/v1/scripting` — 安全脚本
- `as.xiaohongshu.com/api/sec/v1/shield/webprofile` — 安全盾

### 编辑/内容 (edith)
- `edith.xiaohongshu.com/api/im/redmoji/version` — emoji 版本
- `edith.xiaohongshu.com/api/qrcode/userinfo` — 扫码登录
- `edith.xiaohongshu.com/api/redcaptcha/v2/getconfig` — 验证码配置
- `edith.xiaohongshu.com/api/sns/web/global/config` — 全局配置

### 监控
- `apm-fe.xiaohongshu.com/api/data` — APM 性能监控

## 4. 首页/探索页发现
- 首页标题: "小红书 - 你的生活兴趣社区"
- 探索页正常加载：标题同首页（SPA 应用）
- 内容形式：图文笔记 + 短视频

## 5. 适配状态
- Publisher: ❌ 未创建
- SDK Adapter: ❌ 未创建
- 登录插件: ❌ 未创建
- 探索报告: ✅ 已保存
- 需要凭证: ✅ 需要用户提供手机号/扫码登录

## 6. 特殊注意事项
- 小红书反爬严格（自研 `as.xiaohongshu.com` 安全签名系统）
- 内容形式：图文笔记 + 短视频，类似 Instagram
- 发布方式：需要进一步探索（有凭证后）
- 编辑器 URL 可能不同（需探索 SPA 路由）
- 有自研验证码系统 `redcaptcha`
- 登录主要方式：手机验证码 + 扫码

## 7. 原始数据
详见 `xiaohongshu_exploration_report.json`
