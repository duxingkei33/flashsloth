# 🦥 FlashSloth — 项目全景报告

**报告日期**: 2026-07-07  
**当前版本**: v4.60-signin-stats-deploy-enhance  
**Git**: master, 3 commits ahead of origin/master  
**检出**: 86bf0f8 → fix: refreshStats JS 索引修正  

---

## 目录

1. [项目概览](#1-项目概览)
2. [架构总览](#2-架构总览)
3. [铁律与开发规矩](#3-铁律与开发规矩)
4. [功能清单](#4-功能清单)
5. [待办事项](#5-待办事项)
6. [服务运行状态](#6-服务运行状态)
7. [Cron Job 审计报告](#7-cron-job-审计报告)
8. [推荐推进计划](#8-推荐推进计划)

---

## 1. 项目概览

### 1.1 项目定位

**FlashSloth** — 个人数字资产全聚合平台。一个后台管理你在互联网上的所有数字资产：文章、视频、商品、账号。

> 树懒的速度，闪电的发布 🦥⚡

### 1.2 核心目标

- **统一管理**: 多平台账号集中管理（Discuz/CSDN/知乎/掘金/B站/闲鱼/OSHWHub/GitHub Pages）
- **内容发布**: 文章采集 → AI 编译 → 预览 → 存草稿 → 多平台发布
- **自动签到**: 定时执行多论坛/平台签到，积分自动化
- **价格监控**: 闲鱼/LCSC 元器件价格追踪与报警
- **通知网关**: 22+ 渠道的系统事件推送（Telegram/Discord/飞书/企微等）
- **评论监控**: 帖子回复自动检测 + AI 自动回帖
- **工作台流水线**: Provider → 编译 → 预览 → 发布的统一调度

### 1.3 目标用户

技术创作者 / 多平台运营者 / 数码爱好者

### 1.4 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | Flask 3.0 + Jinja2 |
| 认证 | Flask-Login + Session + API Key |
| 数据库 | SQLite (WAL mode + FK constraints) |
| 浏览器自动化 | Playwright (Chromium) |
| AI 路由 | 多供应商框架 (DeepSeek/OpenAI/等 21+) |
| 加密 | Fernet AES-128-CBC + HMAC-SHA256 |
| 发布器 | 14 个平台 Publisher + 3 个签到插件 |
| SDK | 15+ 平台适配器 (sdk/adapters/) |
| 外部暴露 | frpc tunnel (127.0.0.1:5000 → remote:5001) |
| CI | GitHub Actions (test + import check) |
| 部署 | Docker (python:3.11-slim) |

### 1.5 规模指标

| 指标 | 数值 |
|------|------|
| Python 文件 | ~136 |
| HTML 模板 | 30 |
| 数据库表 | 26 |
| 活跃账号 | 7 (5 平台) |
| 文章 | 18 (9 published + 9 draft) |
| 发布记录 | 14 |
| 签到记录 | 185 |
| 探索版块 | 130 (amobbs 95 + mydigit 33 + oshwhub 2) |
| 用户 | 1 (admin) |
| 标签 | v4.0 ~ v4.60 |
| 代码行 | ~59K (DEVELOPMENT_SPECIFICATION.md 文档行数) |

---

## 2. 架构总览

### 2.1 四层架构

```
┌───────────────────────────────────────────────────────────────┐
│                   用户界面层 (Flask Web UI)                      │
│  仪表盘 · 账号管理 · 文章管理 · 签到管理 · 闲鱼搜索             │
│  配置中心 · 探索数据 · 通知网关 · 审批管理 · AI配置 · 工作台    │
│  评论监控 · 论坛阅读器 · AI调用日志 · Playwright设置           │
│  routes/ 22个 Blueprint + templates/ 30个 HTML                  │
└───────────────────────────────────────────────────────────────┘
                              ↕
┌───────────────────────────────────────────────────────────────┐
│                   Gateway API 层                               │
│  routes/api_v1.py — 原始 REST API (API Key 鉴权)              │
│  routes/api_v2.py — 升级版 RESTful Gateway API                │
│  认证: Session / API Key + HMAC-SHA256 签名                   │
└───────────────────────────────────────────────────────────────┘
                              ↕
┌───────────────────────────────────────────────────────────────┐
│                   统一工作流引擎 (core/)                         │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  核心引擎 (29 文件)                                    │   │
│  │  publisher · gateway · scheduler · database            │   │
│  │  credential_crypto · anti_detect · explorer            │   │
│  │  price_monitor · approval · notifier · ai_provider     │   │
│  │  article · deployer · compiler · pipeline · image      │   │
│  │  signin · status_detector · status_cache               │   │
│  │  forum_registry · compiled_cache · renderers           │   │
│  │  compile_rule · provider · browser_engine              │   │
│  │  provider_registry · captcha_handler · storage         │   │
│  └────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                              ↕
┌───────────────────────────────────────────────────────────────┐
│                   发布器 + 适配器层                             │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  plugins/ (45+ 文件)                                  │   │
│  │  14 个 Publisher · 3 个 Signin · 通用/专用登录器       │   │
│  │  forum_signin · forum_reader · reply_monitor           │   │
│  │  xianyu_client SDK (mtop/sign/session/media/category)  │   │
│  │  Provider (markdown/notion) · Deployer                 │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  sdk/ (19 文件) — 平台适配器                            │   │
│  │  adapter.py — PlatformAdapter 统一基类                 │   │
│  │  router.py — 内容路由引擎                              │   │
│  │  adapters/ — 15+ 平台实现 (xianyu_v2/bilibili/csdn/..) │   │
│  └────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                              ↕
┌───────────────────────────────────────────────────────────────┐
│                   公共基础设施层                                │
│  SQLite (flashsloth.db + status_cache.db)                     │
│  .fs_key 加密密钥 · config/ (4 配置) · platform_reports/      │
│  static/ · storage/ · scripts/ (4 脚本) · tests/ (16 测试)    │
│  Dockerfile · requirements.txt · .github/workflows/           │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 核心数据流

```
(A) 文章发布流水线:
  Provider采集 → AI编译 (MD→IR→平台格式) → 预览 → 存草稿 → Publisher发布 → 通知

(B) 签到流水线:
  Scheduler每分钟检查 → 窗口匹配 → 账号ID偏移随机化 → SigninBase插件 → Playwright执行 → 日志

(C) 通知推送:
  notify() → notifications表 → Gateway.dispatch() → 各Provider.send() → 飞书/企微/Telegram等

(D) 登录状态检测 (三层):
  页面请求 → status_cache (5min TTL) → ① API轻量检测 → 
  ② Playwright快速检测 → ③ Playwright全量检测 → 缓存写入

(E) 论坛探索:
  hourly_forum_check.py → explore_cooldown检查 (1次/小时/域名) →
  Playwright访问 → 爬取版块 → 内容哈希变更检测 → 更新DB
```

### 2.3 数据库表（26张）

| 表 | 用途 |
|---|------|
| `users` | 管理员账号 |
| `platform_accounts` | 多平台账号 (config_json 加密存储) |
| `articles` | 文章 (draft/published/archived) |
| `publish_log` | 发布记录 |
| `signin_log` | 签到记录 |
| `gateway_channels` | 通知网关渠道 |
| `forum_exploration` | 论坛版块探索数据 |
| `explore_cooldown` | 探索限流 (1次/小时/域名) |
| `price_monitors` / `price_history` | 价格监控 |
| `approval_requests` | 审批请求 |
| `notifications` | 站内通知 |
| `ai_call_log` | AI 调用日志 |
| `comment_replies` / `comment_monitor_config` | 评论监控 |
| `deployer_configs` / `deploy_log` | 部署器配置 |
| `compiled_cache` | 编译缓存 |
| `provider_config` / `ai_configs` | AI/Provider 配置 |
| `browser_engine_config` / `playwright_config` | 浏览器引擎 |

---

## 3. 铁律与开发规矩

### 3.1 安全铁律

| # | 规则 | 说明 |
|---|------|------|
| 1 | **Playwright 优先** | 所有登录和发布操作必须使用 Playwright，禁止 requests/curl/wget/httpx |
| 2 | **凭证加密** | password/cookie/token/api_key 必须经 `encrypt_config()` 加密 (Fernet AES-128-CBC) |
| 3 | **配置脱敏** | 页面显示敏感字段为 `••••••••`，只读 API 返回脱敏值 |
| 4 | **密钥文件 600 权限** | `.fs_key` 权限 600，自动生成 |
| 5 | **向下兼容加密** | 非 `enc:` 前缀的值原样返回，兼容旧数据 |
| 6 | **API Key + HMAC 签名** | 外部 API 认证：X-API-Key + X-Timestamp + HMAC-SHA256 签名 |

### 3.2 反检测与限流铁律

| # | 规则 | 说明 |
|---|------|------|
| 7 | **反检测统一** | 所有 Playwright 交互必须使用 `core/anti_detect.py` 的人类行为模拟 |
| 8 | **探索限流** | 每域名每小时最多探索一次 (`explore_cooldown` 表持久化) |
| 9 | **签到随机化** | 基于 account_id 确定偏移 (0~44分钟)，避免7账号同时签到 |
| 10 | **Xianyu 频率限制** | 单账号闲鱼请求 ≤ 3次/分钟 |
| 11 | **通知静默** | 网关不可用时静默跳过，不阻塞主流程 |
| 12 | **防风双缓存** | 探索限流使用内存 + SQLite 双缓存，跨进程共享 |

### 3.3 架构铁律

| # | 规则 | 说明 |
|---|------|------|
| 13 | **Publisher 注册制** | 新平台发布器必须通过 `@register` 注册 + 继承 `Publisher` 基类 |
| 14 | **签到插件注册制** | 新签到插件必须 `@register` + 继承 `SigninBase` |
| 15 | **兼容性优先** | 新增功能不破坏现有 URL 路由和数据表结构 |
| 16 | **变更检测** | 论坛探索使用内容哈希检测版块变更 |
| 17 | **审批先过** | AI 发起的敏感操作必须先过审批流程 |
| 18 | **流水线可配置** | Pipeline 支持按需设置处理阶段 |
| 19 | **三层检测降级** | 登录状态检测：API轻量 → Playwright快速 → Playwright全量 |
| 20 | **状态缓存 TTL** | 登录状态缓存 5 分钟 TTL (内存+SQLite)，避免高频检测 |

---

## 4. 功能清单

### 4.1 🔐 账号管理

| 功能 | 状态 | 说明 |
|------|------|------|
| 多平台统一 CRUD | ✅ | 添加/编辑/删除/启用禁用 |
| 密码+验证码登录 | ✅ | Playwright 浏览器自动处理验证码 |
| QR 码扫码登录 | ✅ | 远程浏览器截图+10秒轮询 Cookie 捕获 |
| 手机验证码登录 | ✅ | phone_login + SMS 验证码 |
| Cookie 粘贴（调试） | ✅ | 调试模式手动粘贴 |
| 登录方式演示说明卡 | ✅ | 小程序风格步骤指引 |
| 凭证加密 (Fernet AES) | ✅ | password/cookie/token 全部加密 |
| 三层状态检测 | ✅ | BrowserEngine + API轻量 + Playwright 验证 |
| 三层缓存 | ✅ | 内存(5min TTL) + SQLite 持久化 + 实时刷新 |
| 统一浏览器登录按钮 | ✅ | 所有平台共用统一编辑弹窗登录流程 |
| 浏览检测引擎设置 | ✅ | Playwright 浏览器引擎参数配置 |

### 4.2 📝 多平台文章发布

| 功能 | 状态 | 说明 |
|------|------|------|
| Discuz! 论坛 | ✅ | amobbs/mydigit — 发帖+存草稿+签到 |
| WordPress | ✅ | REST API + App Password |
| 微信公众号 | ✅ | 官方 API 存草稿 |
| CSDN | ✅ | Playwright 发布+签到 |
| 知乎 | ✅ | Playwright 全面重写 |
| OSHWHub 立创 | ✅ | Playwright 发布+签到 |
| 掘金 | ✅ | Cookie 模拟发布 |
| Bilibili 专栏 | ✅ | Playwright 发布+存草稿+图片上传 |
| Twitter/X | ✅ | tweepy API v2 OAuth1.0a |
| 闲鱼商品发布 (v1) | ✅ | XianyuAutoAgent API |
| 闲鱼商品发布 (v2 MTOP) | ✅ | MTOP 签名V2 + AI类目 + CDN 图片 |
| 闲鱼商品发布 (预留) | 🟡 | 框架预留 (商品图片/价格/分类/成色) |
| RSS 订阅 | ✅ | 纯 Python 生成 |
| GitHub Pages | ✅ | git push 自动部署 |
| Gallery 商品发布 | 🔴 | 预留未实现 |

### 4.3 🔔 通知网关

| 功能 | 状态 | 说明 |
|------|------|------|
| 22 通知渠道 | ✅ | Telegram/Discord/Slack/WhatsApp/钉钉/企微/飞书/微信/邮件/Matrix/Teams/LINE 等 |
| QR 扫码自动配置 | ✅ | /callback 端点一键绑定 |
| 消息队列 + Provider 注册表 | ✅ | 统一调度 |
| 批量/单渠道测试 | ✅ | Web 界面可视化测试 |
| **已配置渠道** | 🔴 | **无已启用渠道** — 网关搭建完成但未配置任何终端 |

### 4.4 👨‍👩‍👧‍👦 自动签到

| 功能 | 状态 | 实际表现 |
|------|------|---------|
| OSHWHub 签到 | ✅ | 成功率 ~47.5% (56/118)，存在问题 |
| CSDN 签到 | ✅ | 成功率 **0%** (0/4)，**全部失败** |
| Discuz! 签到 | ✅ | 成功率 **95.2%** (60/63)，表现优秀 |
| 签到随机化 | ✅ | account_id 偏移 + 1小时窗口内随机 |
| 签到统计 | ✅ | 成功/失败分解展示 |
| 已签到检测 | ✅ | 检查 signin_log 避免重复签到 |
| Cookie 过期自动重登 | ✅ | OSHWHub 支持自动重新登录 |

### 4.5 🛒 闲鱼集成

| 功能 | 状态 | 说明 |
|------|------|------|
| 商品搜索 | ✅ | 关键词/价格范围/排序/分页 |
| 价格监控 (LCSC) | ✅ | 元器件价格追踪 + 报警 |
| MTOP 签名 V2 发布器 | ✅ | AI 类目识别 + CDN 图片 |
| xianyu_client SDK | ✅ | mtop/sign/session/media/category/limiter/guard |
| 闲鱼 API 适配器 | ✅ | 搜索/详情/比价/Token 管理 |
| **Cookie 状态** | 🔴 | **已失效** — xianyu 账号 Cookie 已过期 |

### 4.6 🔍 平台探索

| 功能 | 状态 | 说明 |
|------|------|------|
| Discuz 版块自动探索 | ✅ | Playwright 爬取，130个版块 |
| 登录能力探索 | ✅ | 7 平台登录方式自动检测 + JSON 报告 |
| 每小时增量轮询 | ✅ | scripts/hourly_forum_check.py |
| 防风限流 | ✅ | 1次/小时/域名 + 双缓存 |
| 探索数据管理页面 | ✅ | 版块管理 + 关键词匹配 |
| 平台发布能力展示 | ✅ | 标签栏目管理 |
| Bilibili 完整探索 | ✅ | 报告+登录插件+平台能力入库 |
| 微信公众平台探索 | ✅ | 完整报告+发布能力+登录能力 |
| 探索数据覆盖 | 📊 | amobbs 95版块, mydigit 33版块, oshwhub 2版块 |

### 4.7 🧠 AI 能力

| 功能 | 状态 | 说明 |
|------|------|------|
| AI 供应商框架 | ✅ | 21+ 供应商统一接口 |
| 余额查询 | ✅ | DeepSeek/OpenAI 等余额 API |
| 测试连接 | ✅ | 一键测试供应商连通性 |
| AI 调用日志 | ✅ | 自动记录 token/费用/成功失败 |
| 动态供应商注册表 | ✅ | 运行时添加自定义供应商 |
| 版块智能匹配 | ✅ | AI 多平台版块匹配 |
| 关键词库同步 | ✅ | scripts/sync_registry_keywords.py |
| 写作/翻译/图像生成 | ✅ | 多能力类型路由 |

### 4.8 📋 其他功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 审批流程 | ✅ | 创建/通过/拒绝/取消 + Webhook 端点 |
| 统一工作台流水线 | ✅ | Provider → 编译 → 预览 → 发布 |
| 评论监控引擎 | ✅ | Discuz 回复采集 + 去重 + AI 自动回帖 |
| AI 逛论坛 | ✅ | Discuz 帖子读取 + AI 筛选推荐 |
| 规范设置页面 | ✅ | 存储/部署器/Playwright 设置 |
| 文章编译缓存 | ✅ | compiled_cache + source_hash 变更检测 |
| 多格式渲染器 | ✅ | BBCode/MD/HTML/Richtext → 预览 HTML |
| 编译规则定义 | ✅ | 每平台图片/正文/BBCode 限制规则 |
| Notion/MD Provider | ✅ | 统一内容来源 |
| GitHub Pages 部署器 | ✅ | git push 自动部署 |
| AList 网盘存储 | ✅ | AList API 集成 |
| 移动端 CSS 增强 | ✅ | 768px + 480px 双断点响应式 |
| 论坛文章阅读器 | ✅ | Web 端论坛帖子阅读 |
| frpc 隧道 | ✅ | 5000 → 5001 外网暴露 |
| Docker 部署 | ✅ | python:3.11-slim |

---

## 5. 待办事项

### 5.1 P0 — 阻塞级（影响核心功能）

| # | 事项 | 模块 | 问题 | 优先级 |
|---|------|------|------|--------|
| P0-1 | **CSDN 签到全部失败** | signin_csdn | 4次尝试 0% 成功率，CSDN 签到已迁移至微信小程序 | 🔴 最高 |
| P0-2 | **OSHWHub 签到成功率 47.5%** | signin_oshwhub | 118次中62次失败，需要排查 Cookie 过期/重登逻辑 | 🔴 最高 |
| P0-3 | **闲鱼 Cookie 已过期** | xianyu | 账号 `admin_redacted` 状态为 ❌ Cookie已失效 | 🔴 最高 |
| P0-4 | **DeepSeek API 402 余额不足** | ai_provider | AI 调用可能受限制 | 🔴 最高 |

### 5.2 P1 — 重要级

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P1-1 | **通知网关无已启用渠道** | gateway | 22 渠道可用但未配置任一端点，事件通知全部丢失 | 🟠 高 |
| P1-2 | **无系统级 cron 配置** | scripts | 每小时论坛探索脚本依赖手动启动，非持久化 | 🟠 高 |
| P1-3 | **GitHub Pages 发布失败** | deployer | 最近一次部署失败 (art#25) | 🟠 高 |
| P1-4 | **Push 落后** | git | 3 commits ahead of origin/master，未推送 | 🟠 高 |

### 5.3 P2 — 功能增强

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P2-1 | **签到重复执行** | scheduler | 日志显示同一分钟多次签到，窗口匹配逻辑需优化 | 🟡 中 |
| P2-2 | **API Gateway v2 文档** | api_v2 | API 网关框架就绪但缺少完整文档 | 🟡 中 |
| P2-3 | **视频模块** | core/video_compiler.py | 架构预留，实际未实现 | 🟡 中 |
| P2-4 | **商品模块** | core/product.py | 数据模型 + 编译器未实现 | 🟡 中 |
| P2-5 | **探索限流异常** | forum_exploration | DB 缺少 `last_checked`/`hash` 字段 (与 spec 不一致) | 🟡 中 |

### 5.4 P3 — 优化提升

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P3-1 | **单元测试覆盖** | tests | 16 个测试文件，缺少自动化运行 | 🟢 低 |
| P3-2 | **CI 流水线可用性** | .github/workflows | check_imports.py + test_core.py 仅基础检查 | 🟢 低 |
| P3-3 | **DB schema vs 文档一致性** | database | `forum_exploration` 缺少 `last_checked`/`hash` 字段 | 🟢 低 |
| P3-4 | **代码清理** | routes | 已 orphan 的 `pipeline_ui.py`/`pipeline.html` 在 v4.56 清理 | 🟢 低 |

### 5.5 P4 — 远期规划

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P4-1 | **视频模块实现** | video | 剧本→转码→字幕→打包→多平台分发 | 🔵 远期 |
| P4-2 | **购物模块实现** | product | 闲鱼/淘宝搜索→比价→监控→自动下单 | 🔵 远期 |
| P4-3 | **AI 增强写作** | ai_provider | renhua 人话集成 / 写作风格学习 / 自动回复 | 🔵 远期 |
| P4-4 | **系统级 cron 迁移** | ops | 将内部调度迁移至系统 cron 以增强可靠性 | 🔵 远期 |
| P4-5 | **Gallery 商品发布** | publisher | 预留的 Gallery 抽按商品发布 | 🔵 远期 |

### 5.6 待办任务 ↔ Cron Job 映射

| 内部调度 | 周期 | 映射待办 |
|----------|------|---------|
| 签到调度 (`core/scheduler.py`) | 每分钟 (守护线程) | P0-1, P0-2 |
| 状态缓存刷新 | 每5分钟 | 无 |
| 论坛探索 (`scripts/hourly_forum_check.py`) | 每小时 | P1-2 (无外部 cron 触发器) |
| 评论监控检查 | 按配置时段 | 无 |
| 价格刷新 | 手动触发 | 无 |

---

## 6. 服务运行状态

### 6.1 运行中进程

| 服务 | PID | 状态 | 说明 |
|------|-----|------|------|
| **Flask** | 286854 | ✅ **Running** | `python3 admin.py` (venv) |
| **Hermes Gateway** | 87055 | ✅ Running | Hermes Agent 消息网关 |
| **Hermes CLI** | 87088 | ✅ Running | Hermes Agent 会话 |
| **frpc tunnel** | 125571 | ✅ Running | 5000 → 103.97.178.234:5001 |
| **fs-scheduler** | (thread) | ✅ Running | 签到调度守护线程 (60s loop) |

### 6.2 健康检查

| 项目 | 状态 | 备注 |
|------|------|------|
| Flask 进程 | ✅ | PID 286854, 持续运行 |
| 端口 5000 | ✅ | Flask 监听中 |
| frpc 隧道 | ✅ | 外网可访问 |
| 数据库文件 | ✅ | flashsloth.db (750KB), status_cache.db (12KB) |
| 加密密钥 | ✅ | .fs_key (44字节, 权限600) |
| 数据库 WAL 模式 | ✅ | 外键约束启用 |
| 模板热重载 | ✅ 已禁用 | 生产环境关闭 (v4.58) |

### 6.3 风险状态

| 风险点 | 严重度 | 说明 |
|--------|--------|------|
| 🔴 **闲鱼 Cookie 失效** | 高 | 无法使用闲鱼搜索/发布/价格监控 |
| 🔴 **CSDN 签到全失败** | 高 | 迁移至小程序后脱离现有 Playwright 逻辑 |
| 🟠 **DeepSeek 余额不足 (402)** | 中 | AI 能力受限 |
| 🟠 **通知系统完全静默** | 中 | 22 渠道可用但无配置 → 事件无推送 |
| 🟠 **无外部 cron 触发器** | 中 | 论坛探索脚本依赖手动执行 |
| 🟢 **Git 3 commits 未推送** | 低 | 本地修改未推送远端 |

---

## 7. Cron Job 审计报告

> FlashSloth **没有使用系统 crontab**。所有定时任务通过应用内守护线程 (`fs-scheduler`) 实现。

### 7.1 当前定时任务清单

| 任务 | 类型 | 周期 | 实现方式 | 状态 |
|------|------|------|----------|------|
| 自动签到 | 守护线程 | 每分钟 tick | `core/scheduler.py` → `plugins/forum_signin.py` | ✅ 运行中 |
| 状态缓存刷新 | 守护线程 | 每5分钟 | `_refresh_status_cache()` | ✅ 运行中 |
| 论坛探索 | 外部脚本 | 每小时 | `scripts/hourly_forum_check.py` | ❌ **无定时触发** |
| 评论监控检查 | 应用内定时 | 按配置时段 | `routes/comment_monitor.py` | ✅ 配置就绪 |
| 价格刷新 | 手动 | 手动触发 | `core/price_monitor.py` | ⚠️ 需手动 |
| AI 调用日志 | 被动 | N/A | 自动记录每次 AI 调用 | ✅ 自动 |

### 7.2 签到调度分析

**架构**: `_tick_scheduler()` → 每分钟执行 → 基于时间窗口 + account_id 偏移触发

**时间窗口**: 默认 08:00~09:00 (可配置)，每次 tick 检查 `now_minutes ∈ [base, base+60)`

**偏移机制**: `(id * 7 + 13) % 45` → 0~44 分钟偏移 → ±1 分钟容忍

**观察到的异常**:
- OSHWHub 账号 `134` 在同一分钟 (04:26:22) 连续失败，重复执行
- 同一 tick 内多个账号同时触发 (00:58~00:59 密集执行)
- 日志显示大量 `already_signed` 重复签到（正常行为，但有冗余）

### 7.3 签到成功/失败统计

| 平台 | 总数 | 成功 | 失败 | 成功率 | 最近执行 | 诊断 |
|------|------|------|------|--------|----------|------|
| **Discuz!** | 63 | 60 | 3 | **95.2%** ✅ | 2026-07-07 | 表现稳定，偶尔网络问题 |
| **OSHWHub** | 118 | 56 | 62 | **47.5%** ⚠️ | 2026-07-07 | 账号134持续失败，账号173正常 |
| **CSDN** | 4 | 0 | 4 | **0%** ❌ | 2026-07-07 | 签到已迁移至微信小程序 |

### 7.4 论坛探索分析

| 域名 | 版块数 | 最近探索 | 状态 |
|------|--------|----------|------|
| amobbs.com | 95 | 有数据 | ✅ 数据完整 |
| mydigit.cn | 33 | 有数据 | ✅ 数据完整 |
| oshwhub.com | 2 | 有数据 | ⚠️ 仅2版块 |

**发现的问题**:
- `forum_exploration` 表缺少 `last_checked` 和 `hash` 字段（文档中声明存在但实际 DB schema 与文档不一致）
- 无外部 cron 触发器 → `scripts/hourly_forum_check.py` 未被定时调用

### 7.5 评论监控分析

- `comment_monitor_config`: 有配置框架但 **无有效数据**
- `comment_replies`: **空表** — 未采集到回复记录
- 未启用自动回复配置

---

## 8. 推荐推进计划

### 8.1 立即处理 (P0 — 本周)

#### P0-1: CSDN 签到适配微信小程序
```
□ 分析 CSDN 小程序签到 API
□ 修改 plugins/signin_csdn.py 适配新接口
□ 验证签到成功率 > 80%
□ 回退计划: 如无可用 API，在 UI 标注"CSDN 签到已迁移"
```

#### P0-2: OSHWHub 签到故障排查
```
□ 分析账号 134 与 173 的差异
□ 抓取 OSHWHub 签到失败的 Playwright 日志
□ 检查 Cookie 自动重登逻辑
□ 检查浏览器锁死/超时 (参考 v4.58 engine-deadlock-fix)
```

#### P0-3: 闲鱼 Cookie 重新登录
```
□ 手动执行 QR 码扫码重新登录 xianyu
□ 验证搜索/发布功能可用
□ 配置 xianyu_v2 MTOP 发布器 Cookie
```

#### P0-4: AI 供应商余额补充
```
□ 检查 DeepSeek API 余额/充值
□ 配置备用供应商 (如 OpenAI)
□ 或启用余额告警通知
```

### 8.2 重要事项 (P1 — 1~2周)

#### P1-1: 配置通知网关
```
□ 添加至少一个通知渠道 (飞书/企微/Telegram)
□ 配置签到失败 / 发布成功 / 价格报警等事件推送
□ 验证消息可达性
```

#### P1-2: 建立系统 cron 定时任务
```bash
# 添加到系统 crontab
0 * * * * cd /path && venv/bin/python scripts/hourly_forum_check.py
# 可选: 每日签到统计邮件
30 9 * * * cd /path && venv/bin/python -c "from flashsloth.core.scheduler import _tick_scheduler; _tick_scheduler()"
```

#### P1-3: GitHub Pages 部署器修复
```
□ 分析 deploy_log 最近失败原因
□ 检查 git push 凭证/权限
□ 修复后重新部署 art#25
```

### 8.3 功能增强 (P2 — 1个月)

#### P2-1: 签到调度逻辑优化
```
□ 解决同一分钟多次触发问题
□ 优化窗口匹配：跳过多余的 already_signed 检查
□ 增加签到失败自动重试 1次
```

#### P2-2: Gateway API v2 文档与测试
```
□ 编写 api_v2 路由的完整 OpenAPI 文档
□ 添加 API Key 自动管理界面
□ 端到端测试每个端点
```

#### P2-3: DB schema 对齐
```
□ 检查 forum_exploration 表是否缺少 last_checked/hash 字段
□ 添加缺失字段或更新文档
□ 增加迁移脚本确保兼容性
```

### 8.4 长期推进 (P3-P4 — 1~3个月)

| 阶段 | 内容 | 时间预估 |
|------|------|----------|
| **Phase 0: 基础设施完善** | 系统 cron + 网关配置 + 供应商余额管理 | 1 周 |
| **Phase 1: 稳定性提升** | 签到修复 + CI 流水线 + 部署器修复 | 1 周 |
| **Phase 2: 测试覆盖** | 单元测试增强 + API 测试 + E2E 发布测试 | 2 周 |
| **Phase 3: 购物模块** | 商品数据模型 + 编译器 + 价格监控增强 | 2~3 周 |
| **Phase 4: 视频模块** | 视频数据模型 + 编译流水线 + B站分发 | 2~3 周 |
| **Phase 5: AI 增强** | 写作风格学习 / 自动回复 / 语音操作 | 持续 |

### 8.5 关键指标 (KPI)

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| Discuz 签到成功率 | 95.2% | > 98% |
| OSHWHub 签到成功率 | 47.5% | > 90% |
| CSDN 签到成功率 | 0% | > 85% |
| 闲鱼 Cookie 有效 | ❌ | ✅ |
| 通知网关配置 | 0 渠道 | ≥ 2 渠道 |
| 论坛探索自动触发 | ❌ | ✅ (每小时) |
| Git 同步状态 | 3 commits ahead | up to date |
| AI 调用成功率 | ✅ | > 95% |

---

## 附录 A: 文件结构树

```
flashsloth/
├── admin.py                 # 入口点 (79行)
├── ARCHITECTURE.md          # 架构文档
├── README.md                # 项目说明
├── DEVELOPMENT_SPECIFICATION.md  # 开发说明书 (1194行)
├── Dockerfile               # Docker 部署
├── requirements.txt         # Python 依赖
├── frpc.toml                # frpc 隧道配置
├── .fs_key                  # Fernet 加密密钥 (44B, 600权限)
├── flashsloth.db            # SQLite 主数据库 (750KB)
├── status_cache.db          # 状态缓存 (12KB)
│
├── core/                    # 核心引擎 (30 Python 文件)
│   ├── ai_provider.py       # AI 路由 + 日志
│   ├── anti_detect.py       # 反检测/人类行为模拟
│   ├── approval.py          # 审批流程
│   ├── article.py           # 文章模型
│   ├── browser_engine.py    # 浏览器引擎管理
│   ├── captcha_handler.py   # 验证码处理
│   ├── compile_rule.py      # 编译规则
│   ├── compiled_cache.py    # 编译缓存
│   ├── compiler.py          # 编译器
│   ├── config.py            # 全局配置
│   ├── credential_crypto.py # 凭证加密 (Fernet)
│   ├── database.py          # 数据库初始化
│   ├── deployer.py          # 部署器基类
│   ├── explorer.py          # 论坛探索引擎
│   ├── forum_registry.py    # 版块注册中心
│   ├── gateway.py           # 通知网关核心
│   ├── image_pipeline.py    # 图片流水线
│   ├── notifier.py          # 统一通知系统
│   ├── pipeline.py          # 内容流水线
│   ├── price_monitor.py     # 价格监控
│   ├── provider.py          # Provider 基类
│   ├── provider_registry.py # AI 供应商注册表
│   ├── publisher.py         # Publisher 基类
│   ├── renderers.py         # 渲染器
│   ├── scheduler.py         # 签到调度器
│   ├── signin.py            # 签到基类
│   ├── status_cache.py      # 状态缓存
│   ├── status_detector.py   # 登录状态检测器
│   └── storage.py           # 存储抽象层
│
├── routes/                  # 蓝图层 (22 Python 文件)
│   ├── __init__.py          # 路由中心 (应用工厂)
│   ├── _app.py              # 共享 Flask 实例
│   ├── accounts.py          # 账号管理
│   ├── ai.py                # AI 供应商
│   ├── api_v1.py            # API v1
│   ├── api_v2.py            # API v2 (Gateway)
│   ├── approval.py          # 审批管理
│   ├── auth.py              # 登录/注册
│   ├── browser_engine.py    # 浏览器引擎设置
│   ├── browser_login.py     # Playwright 登录
│   ├── captcha_browser.py   # 验证码浏览器
│   ├── comment_monitor.py   # 评论监控
│   ├── exploration.py       # 探索数据
│   ├── forum.py             # 论坛阅读器
│   ├── gateway.py           # 通知网关
│   ├── notifications.py     # 通知系统
│   ├── platforms.py         # 平台预设
│   ├── posts.py             # 文章管理
│   ├── price_monitor.py     # 价格监控
│   ├── signin.py            # 签到管理
│   ├── storage_deploy.py    # 存储/部署
│   ├── workspace_ui.py      # 工作台
│   └── xianyu_search.py     # 闲鱼搜索
│
├── plugins/                 # 插件层 (45+ 文件)
│   ├── publisher_*.py       # 14个发布器
│   ├── signin_*.py          # 3个签到插件
│   ├── generic_login.py     # 通用登录器
│   ├── amobbs_login.py      # 阿莫论坛登录器
│   ├── bilibili_login.py    # B站登录器
│   ├── xianyu_login.py      # 闲鱼登录器
│   ├── oshwhub_login.py     # OSHWHub 登录器
│   ├── forum_signin.py      # 论坛签到 Orchestrator
│   ├── forum_reader.py      # AI 逛论坛
│   ├── reply_monitor.py     # 评论监控引擎
│   ├── provider_markdown.py # Markdown Provider
│   ├── provider_notion.py   # Notion Provider
│   ├── deployer_github_pages.py  # GitHub Pages 部署
│   ├── storage_alist.py     # AList 存储
│   ├── xianyu/              # 闲鱼旧 API 层
│   └── xianyu_client/       # 闲鱼 MTOP SDK
│       ├── mtop.py          # MTOP API 调用
│       ├── sign.py          # 签名生成
│       ├── session.py       # Cookie 会话
│       ├── media.py         # 图片上传 CDN
│       ├── category.py      # AI 类目推荐
│       ├── location.py      # 地址获取
│       ├── guard.py         # 风控监控
│       ├── limiter.py       # 频率限制
│       └── errors.py        # 错误类型
│
├── sdk/                     # SDK 适配器层 (19 文件)
│   ├── adapter.py           # 统一基类
│   ├── router.py            # 内容路由
│   ├── scaffold.py          # 脚手架生成
│   └── adapters/            # 15+ 平台实现
│
├── templates/               # 30个 HTML 模板
├── static/                  # 静态资源
├── config/                  # 平台配置 (4 JSON)
├── platform_reports/        # 探索报告 (20+ 文件)
├── scripts/                 # 4个运维脚本
├── tests/                   # 16个测试文件
├── storage/                 # 本地存储
├── .github/workflows/       # CI/CD
└── .agents/                 # Agent 工作区
```

---

## 附录 B: Git 最近提交

```
86bf0f8 fix: refreshStats JS 索引修正 — 按行分组定位统计卡片
c59e75e feat: 部署配置增强 — 账号页嵌入部署区块+deployers增强版
5f7d360 fix: 签到统计去重+手动签到实时刷新+看门狗增强
274f6ef feat: add phone login method to CSDN and Bilibili publishers
a3c9230 fix: BrowserEngine锁死导致已登录页面全部超时
40d29aa chore: cleanup — remove orphaned pipeline_ui.py/pipeline.html
7d124ce perf: 生产环境关闭模板热重载 + BrowserEngine状态2秒缓存
c1316e2 fix: 登录页卡死 — browser_engine context_processor 对未登录用户也调get_engine()
e35d4f2 feat: WeChat Official Account full exploration + publisher improved
78adab1 feat: 账号三层状态检测系统 — BrowserEngine+API轻量检测+缓存
```

---

*报告由 AI 自动生成于 2026-07-07。数据来源: 代码文件分析 + SQLite 数据库查询 + 进程状态检查。*
