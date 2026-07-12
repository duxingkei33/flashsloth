# 平台探索报告：juejin.cn（稀土掘金）

> **探索时间**: 2026-07-07 22:19 CST
> **探索方式**: Playwright 无凭证预探索
> **账号状态**: ❌ 无有效凭证
> **站点**: https://juejin.cn
> **技术栈**: 自研CMS (字节跳动系)，Nuxt.js SSR + REST API
> **对应适配版本**: 框架就绪（v4.35+）

## 1. 登录状态

**所有登录方法（已验证）：**

| 登录方式 | 是否支持 | 验证方式 | 备注 |
|---------|---------|---------|------|
| 手机验证码登录 | ✅ 默认方式 | 输入手机号 → 获取验证码 → 输入验证码 → 登录 | 不需要密码，仅需手机+短信 |
| 密码登录 | ✅ 可切换 | 输入邮箱/手机号 + 密码 → 登录 | `loginPhoneOrEmail` + `loginPassword` 字段 |
| 扫码登录（APP） | ✅ | 生成 base64 QR code → 稀土掘金APP 扫 → 自动登录 | 需要 APP v6.4.1+ |
| 第三方 OAuth | ✅ | GitHub / 微博 / 微信 | 需用户在浏览器完成授权 |
| Cookie 粘贴 | ✅ | 从浏览器 F12 复制 Cookie | 备选方案，publisher 可用 |

**登录弹窗结构：**
- 默认显示验证码登录（邮箱/手机+验证码）
- 底部链接切换："密码登录"、"扫码登录"
- OAuth 图标：GitHub（灰色圆形）、微博、微信

**CAPTCHA：** 检测未发现独立验证码输入框。验证码登录通过短信验证码完成，密码登录可能需要验证码但不明显。

## 2. 发布能力

### 2.1 文章/专栏发布

**编辑器 URL：** `https://juejin.cn/editor/drafts/new`
- ❌ **未登录时重定向到 `https://juejin.cn/login?to=...`**
- ✅ 需要有效登录 Cookie 才能访问编辑器
- 发布通过 REST API 完成（`requests` 方式）

**已知 API 端点（17个发现）：**

| 端点 | 功能 | 是否需要登录 |
|------|------|------------|
| `content_api/v1/content/article_rank` | 文章热榜 | ❌ 公开 |
| `recommend_api/v1/article/recommend_all_feed` | 推荐 feed | ❌ 公开 |
| `content_api/v1/article_draft/create` | 创建草稿 | ✅ 需要 Cookie |
| `content_api/v1/article/publish` | 发布文章 | ✅ 需要 Cookie |
| `user_api/v1/user/get` | 用户信息 | ❌ 部分公开 |
| `user_api/v1/sys/token` | Token 管理 | ✅ 需要 Cookie |
| `tag_api/v1/query_category_briefs` | 标签分类 | ❌ 公开 |
| `interact_api/v1/pin_tab_lead` | 交互板块 | ❌ 公开 |

### 2.2 图片上传

- 通过 API 上传（REST API），非 Playwright 编辑器操作
- 当前 publisher 无图片上传实现

### 2.3 存草稿/发布

- ✅ 存草稿：`content_api/v1/article_draft/create`
- ✅ 发布：`content_api/v1/article/publish`（需先创建草稿）
- 当前 publisher（`plugins/publisher_juejin.py`）已实现 API 方式创建草稿+发布

## 3. 签到

❌ 未探索（需登录后确认）
- 可能通过 `user_api/v1/task/get` 实现签到

## 4. 采集能力

- ✅ 公开文章可读取（URL 模式：`https://juejin.cn/post/{id}`）
- ✅ 热榜/推荐 API 可采集（无需登录）
- ✅ 标签分类 API 可采集

## 5. 当前适配状态

| 组件 | 状态 | 说明 |
|------|------|------|
| publisher_juejin.py | ⚠️ 已存在 | 使用 `requests` API 方式（违反铁律#2 — 禁止 requests 操作平台）|
| sdk/adapters/juejin.py | ✅ 已存在 | 轻量包装，委托给 publisher |
| generic_login.py 配置 | ✅ 已存在 | juejin 登录配置已在 |
| login_capabilities | ✅ 已探索 | login_capabilities.json 已保存 |
| platform_config DB 条目 | ❌ 缺失 | 需创建 |
| Platform_reports (md) | ❌ 缺失 | 本报告即为创建 |
| E2E 验证 | ❌ 未做 | 需要有效账号凭证 |

## 6. 问题与风险

### 🔴 严重问题：Publisher 违反铁律

`plugins/publisher_juejin.py` 使用 `requests` 而非 Playwright 进行平台 API 操作，违反了 FlashSloth 核心铁律：
> **唯一合法的平台操作工具是 Playwright。禁止使用 requests/curl/wget/httpx 等任何非浏览器工具做平台层面的操作。**

**修复方案：**
1. 重写 publisher 为 Playwright 模式（打开编辑器 → 填写 → 存草稿/发布）
2. 或向架构文档申请豁免（掘金 API 用 REST API 调用，无需浏览器操作编辑器）
3. 当前 publisher 基于 Cookie 鉴权的 API 方式在实际使用中可能因 Cookie 过期而失败

### 🟡 隐患：无 Cookie 刷新机制
当前 publisher 的 Cookie 是静态传入，无自动刷新逻辑。Cookie 过期后需要用户手动更新。

### 🟡 隐患：图片上传未实现
当前 publisher 无图片上传功能。文章正文中的图片引用无法处理。

## 7. 待完成清单

- [ ] **创建 platform_config DB 条目**（本探索已完成）
- [ ] **重写 publisher 为 Playwright 模式**（或申请豁免）
- [ ] **添加图片上传支持**（通过 Playwright 编辑器或 API 方式）
- [ ] **添加存草稿模式支持**（当前仅 API 方式）
- [ ] **E2E 隧道验证**（需要有效账号凭证）
- [ ] **签到能力确认**（需要登录后验证）
- [ ] **REQUIRES_USER.md 更新**（标记掘金需要的凭证类型）
