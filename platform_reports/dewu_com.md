# 得物 (dewu.com)

> **探索时间**: 2026-07-08 00:19
> **探索方式**: Playwright 无头浏览器
> **账号状态**: ❌ 未登录
> **站点**: https://www.dewu.com/
> **架构**: React SPA + Mobile App

## 🔐 登录能力

### 登录方式

| 方式 | 支持 | 说明 |
|------|------|------|
| 📱 手机号+验证码 | ✅ App内 | 得物App主要登录方式 |
| 🔑 手机号+密码 | ✅ 开放平台 | open.dewu.com 有完整登录表单 |
| 💬 微信OAuth | ✅ App内 | 微信授权登录 |
| 🐧 QQ OAuth | ✅ App内 | QQ授权登录 |
| 📣 微博OAuth | ✅ App内 | 微博授权登录 |
| 📷 App扫码登录 | ✅ | 支持App扫码登录PC端 |

### 验证码

- **类型**: 阿里云 FeiLin 滑块验证码（阿里云Captcha）
- **触发条件**: 访问首页即触发
- **自研风控**: `risk-stone-captcha` API (`app.dewu.com/api/v1/h5/risk-stone-captcha/captcha/call`)
- **前端SDK**: `AliyunCaptcha.js` + `FeiLin/1.4.2`

### 输入字段

**开放平台 (open.dewu.com) 登录页**:
- `input[placeholder='请输入手机号码']` — 手机号
- `input[type='password']` — 密码

### 按钮

- 登录按钮: `登录`
- 注册按钮: `注册`

### 登录入口路径

1. **PC网站 (www.dewu.com)**: ❌ 无登录入口（纯展示/App下载引导页）
2. **SPA路由 (/#/login)**: ⏳ 路由存在但未登录不渲染表单
3. **开放平台 (open.dewu.com)**: ✅ 有完整登录系统
4. **得物App**: ✅ 主力产品，全部核心功能在App内

## 📝 发布能力

| 能力 | 状态 |
|------|------|
| 编辑器类型 | 移动App专用 |
| PC端发布 | ❌ 不支持 |
| 发帖 | ❌ 仅App内 |
| 图片上传 | ❌ 仅App内 |
| API端点 | 0个（PC端无发布API） |

**结论**: 得物是移动App优先平台，PC网站仅为展示页+App下载引导。所有内容创作（发帖、图片上传等）均在得物App内完成。PC端适配FlashSloth发布系统**不可行**。

## ⚙️ 技术信息

| 项目 | 值 |
|------|-----|
| 架构 | React SPA |
| 反爬 | ✅ 强烈（阿里云FeiLin验证码 + 自研risk-stone-captcha） |
| 频率限制 | ✅ app.dewu.com API有频率限制（401 操作频繁） |
| 动态内容 | ✅ SPA渲染 |
| 反爬脚本 | pceptor.js, preinforce2.js, pyuntu.js |

### 子域名

| 子域名 | 用途 |
|--------|------|
| www.dewu.com | 主站（展示页） |
| app.dewu.com | API服务端 |
| open.dewu.com | 开放平台（开发者/商家） |
| cdn.dewu.com | CDN |
| cdn.poizon.com | CDN（poizon旧域名） |
| dav.dewu.com | 数据/风控 |
| davstatic.dewu.com | 风控静态资源 |
| h5static.dewucdn.com | H5静态资源 |
| cdn-jumper.dewu.com | SDK跳转 |
| cdn-config.dewu.com | 配置中心 |

### 备注

得物（原名"毒"）是新一代潮流网购社区（潮牌球鞋鉴定交易平台）。PC端定位为品牌展示+App下载引导，不提供任何登录/发布功能。全部用户操作（购物、社区、发布内容）均在移动App中完成。强风控体系（阿里云Captcha + 自研risk-stone-captcha）使得Playwright自动化操作极其困难。

## 📋 适配评估

| 需求 | 可行性 | 备注 |
|------|--------|------|
| PC端登录适配 | ❌ 不可行 | PC无独立登录页，全部在App内 |
| PC端发布 | ❌ 不可行 | PC无发布能力 |
| 开放平台API | ⏸ 需评估 | 面向开发者/商家，非普通用户 |
| Cookie登录 | ⏸ 需评估 | token/session 可能来自App登录后注入 |

## 🔗 相关链接
- https://www.dewu.com/ — 得物首页
- https://open.dewu.com/ — 得物开放平台
- https://seller.dewu.com/ — 得物商家后台（DNS解析失败）
