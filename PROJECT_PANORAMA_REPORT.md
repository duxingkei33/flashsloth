# 🦥 FlashSloth — 项目全景报告

**报告日期**: 2026-07-09
**当前版本**: v5.21
**Git**: master, **dirty** (admin.py uncommitted), latest commit `2cb1738`
**标签**: v5.21 (最新)

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

- **统一管理**: 多平台账号集中管理（Discuz 系/CSDN/知乎/掘金/B站/OSHWHub/闲鱼/微信公众号/WordPress/Twitter 等）
- **内容发布**: Provider 采集 → AI 编译 → 预览 → 存草稿 → 多平台发布
- **自动签到**: 定时执行多论坛/平台签到，积分自动化
- **价格监控**: LCSC 元器件价格追踪与报警
- **通知网关**: 22+ 渠道的系统事件推送（Telegram/Discord/飞书/企微等）
- **评论监控**: 帖子回复自动检测 + AI 自动回帖
- **工作台流水线**: Provider → 采集 → 编译 → 预览 → 发布的统一调度
- **平台探索**: 各平台版块结构自动采集 + 登录能力雷达探测

### 1.3 目标用户

技术创作者 / 多平台运营者 / 数码爱好者

### 1.4 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | Flask 3.0 + Jinja2 |
| 认证 | Flask-Login + Session + API Key + HMAC-SHA256 |
| 数据库 | SQLite (WAL mode + FK constraints) |
| 浏览器自动化 | Playwright (Chromium) |
| AI 路由 | 多供应商框架 (DeepSeek/OpenAI 等 21+) |
| 加密 | Fernet AES-128-CBC + HMAC-SHA256 |
| 发布器 | 19 个平台 Publisher + 3 个签到插件 |
| SDK | 15 平台适配器 (sdk/adapters/) |
| 外部暴露 | frpc tunnel (127.0.0.1:5000 → 103.97.178.234:5001) |
| CI | GitHub Actions (test + import check) |
| 部署 | Docker (python:3.11-slim) |

### 1.5 规模指标

| 指标 | 数值 |
|------|------|
| Python 文件 | 167 |
| HTML 模板 | 36 |
| 数据库表 | 28 |
| 活跃账号 | 多平台 (is_active=1) |
| 文章 | 含 draft/published/archived |
| 发布器 | 19 个 (含得物/什么值得买/小红书) |
| 探索报告 | 13 平台 |
| 论坛版块 | 130 (forum_exploration 表) |
| 用户 | 1 (admin) |
| 标签 | v4.0 ~ v5.21 |
| 代码行 | ~59K |
| 铁律 | 42 条 (fs-iron-rules skill) |

---

## 2. 架构总览

### 2.1 四层架构

```
┌───────────────────────────────────────────────────────────────┐
│                   用户界面层 (Flask Web UI)                      │
│  仪表盘 · 账号管理 · 文章管理 · 签到管理 · 闲鱼搜索             │
│  配置中心 · 探索数据 · 通知网关 · 审批管理 · AI配置 · 工作台    │
│  评论监控 · 论坛阅读器 · AI调用日志 · Playwright设置           │
│  统一日志 · 部署管理 · 外部服务 · 存储设置                      │
│  routes/ 22 个 Blueprint + templates/ 36 个 HTML                │
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
│  │  核心引擎 (33 文件)                                    │   │
│  │  publisher · gateway · scheduler · database            │   │
│  │  credential_crypto · credential_provider · cookie_validator │
│  │  anti_detect · explorer · forum_registry               │   │
│  │  price_monitor · approval · notifier · ai_provider     │   │
│  │  article · deployer · compiler · pipeline · image      │   │
│  │  signin · status_detector · status_cache               │   │
│  │  compiled_cache · renderers · compile_rule             │   │
│  │  provider · provider_registry · browser_engine         │   │
│  │  captcha_handler · storage · credential_guard          │   │
│  │  platform_exploration_loader                           │   │
│  └────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                              ↕
┌───────────────────────────────────────────────────────────────┐
│                   发布器 + 适配器层                             │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  plugins/ (19 个 Publisher + 3 个 Signin + 登录器)      │   │
│  │  forum_signin · forum_reader · reply_monitor           │   │
│  │  xianyu_client SDK (mtop/sign/session/media/category)  │   │
│  │  Provider (markdown/notion/taobao) · Deployer         │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  sdk/ (15 适配器) — 平台适配器                          │   │
│  │  adapter.py — PlatformAdapter 统一基类                 │   │
│  │  router.py — 内容路由引擎                              │   │
│  │  adapters/ — 15 平台实现                               │   │
│  └────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                              ↕
┌───────────────────────────────────────────────────────────────┐
│                   公共基础设施层                                │
│  SQLite (flashsloth.db 749KB + status_cache.db 12KB)          │
│  .fs_key 加密密钥 · config/ · platform_reports/ (13 报告)      │
│  static/ · storage/ · scripts/ · tests/                        │
│  Dockerfile · requirements.txt · .github/workflows/            │
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

(E) 平台探索:
  定时脚本 → explore_cooldown检查 (1次/小时/域名) →
  Playwright访问 → 爬取版块 → 内容哈希变更检测 → 更新DB (platform_exploration表)

(F) 统一凭证体系 (v4.92):
  ScanLoginEngine → QR码轮询 → Cookie捕获 → save_credential() → verify_credential() → Cookie验证器
```

### 2.3 数据库表（28张）

| 表 | 用途 |
|---|------|
| `users` | 管理员账号 |
| `platform_accounts` | 多平台账号 (config_json 加密存储, is_active 状态) |
| `articles` | 文章 (draft/published/archived) |
| `publish_log` | 发布记录 |
| `signin_log` | 签到记录 |
| `gateway_channels` | 通知网关渠道 |
| `forum_exploration` | 论坛版块探索数据 |
| `platform_exploration` | 平台探索数据 (v5.14 JSON→DB迁移) |
| `explore_cooldown` | 探索限流 (1次/小时/域名) |
| `price_monitors` / `price_history` | 价格监控 |
| `approval_requests` | 审批请求 |
| `notifications` | 站内通知 |
| `ai_call_log` | AI 调用日志 |
| `comment_replies` / `comment_monitor_config` | 评论监控 |
| `deployer_configs` / `deploy_log` | 部署器配置 |
| `compiled_cache` | 编译缓存 |
| `provider_config` / `ai_configs` | AI/Provider 配置 |
| `platform_config` / `site_configs` | 平台/站点配置 |
| `playwright_config` / `browser_engine_config` | 浏览器引擎 |
| `api_keys` / `verify_codes` / `forum_recommendations` | API密钥/验证码/论坛推荐 |

---

## 3. 铁律与开发规矩

FlashSloth 项目遵循 **40 条铁律**，统一维护在 `fs-iron-rules` skill 中。完整内容请加载该 skill 查看。

### 3.1 铁律分类概览

| 类别 | 条数 | 覆盖范围 |
|------|:----:|---------|
| 🔴 DB/账号铁律（最高优先级） | 3 | 绝不动 users 表、账号清理、platform_accounts 保护 |
| 平台登录与适配规则 | 9 | SSO cookie 结构化、数据驱动登录验证、验证码检测前置、硬性兜底 |
| 基本开发规则 | 28 | Playwright 优先、凭证加密、反检测、硬编码禁止、JS 缓存、备份流程 |
| **总计** | **40** | 完整覆盖安全/架构/开发/测试/运维 |

### 3.2 关键铁律引用

- **铁律 #1**: 不反问，自己决策执行完报告
- **铁律 #2**: 所有外部平台操作必须 Playwright，禁止 requests/curl
- **铁律 #12**: 密码/Cookie/Token 必须 `encrypt_config()` 加密
- **铁律 #18**: 禁止硬编码平台列表/配置，必须从 DB/JSON 动态加载
- **铁律 #19**: 禁止硬编码平台名/URL/登录方法，数据驱动（v5.18 全量修复 39 项违规）
- **铁律 #35**: 探索数据启动时导入 DB，运行时从 DB 读取（v5.14 完成 JSON→DB 迁移）
- **铁律 #40**: 大改前三位一体备份（tar.gz + tag + push）

### 3.3 备份体系

铁律 #40 强制三位一体备份流程：
1. ZIP 全量备份到 `~/fastsloth/flashsloth_v{version}-{date}-{desc}.tar.gz`
2. `git tag` 标注版本号
3. `git push origin master` + `git push --tags`

每日 4:30 自动执行备份 cron 任务。

---

## 4. 功能清单

### 4.1 🔐 账号管理

| 功能 | 状态 | 说明 |
|------|------|------|
| 多平台统一 CRUD | ✅ | 添加/编辑/删除/启用禁用 (is_active) |
| 密码+验证码登录 | ✅ | Playwright 浏览器自动处理，验证码检测前置 |
| QR 码扫码登录 | ✅ | 远程浏览器截图+10秒轮询 Cookie 捕获（优先级#1） |
| 手机验证码登录 | ✅ | phone_login + SMS 验证码 |
| 统一扫码登录引擎 | ✅ | ScanLoginEngine (v4.92), 线程安全 |
| Cookie 粘贴（调试） | ✅ | 调试模式手动粘贴 |
| 登录方式演示说明卡 | ✅ | 小程序风格步骤指引 + 7 步进度条 |
| 凭证加密 (Fernet AES) | ✅ | password/cookie/token 全部加密 |
| 三层状态检测 | ✅ | BrowserEngine + API轻量 + Playwright 验证 |
| 三层缓存 | ✅ | 内存(5min TTL) + SQLite 持久化 + 实时刷新 |
| 统一 Cookie 验证器 | ✅ | v4.92 消除 4 处散落校验代码 |
| 统一浏览器登录按钮 | ✅ | 所有平台共用统一编辑弹窗登录流程 |
| 登录引擎数据驱动 | ✅ | v5.16 从探索 JSON 动态推导引擎路由 |
| 账号管理模块化拆分 | ✅ | v5.14 routes/accounts/ 包 (7 子模块) |
| 前端 JS 模块化 | ✅ | v5.17 内联 2900 行 JS 拆为 5 独立模块 |
| 凭证健康检查 | ✅ | 每 30 分钟自动守护脚本 |

### 4.2 📝 多平台文章发布

| 功能 | 状态 | 说明 |
|------|------|------|
| Discuz! 论坛 | ✅ | amobbs/mydigit — 发帖+存草稿+签到 |
| WordPress | ✅ | REST API + App Password |
| 微信公众号 | ✅ | 官方 API 存草稿 |
| CSDN | ✅ | Playwright 发布+签到 |
| 知乎 | ✅ | Playwright 全面重写 |
| OSHWHub 立创 | ✅ | Playwright 发布+签到 (v5.19 SSO 登录修复) |
| 掘金 | ✅ | Cookie 模拟发布 |
| Bilibili 专栏 | ✅ | Playwright 发布+存草稿+图片上传 |
| Twitter/X | ✅ | tweepy API v2 OAuth1.0a |
| 闲鱼商品发布 (v1) | ✅ | XianyuAutoAgent API |
| 闲鱼商品发布 (v2 MTOP) | ✅ | MTOP 签名V2 + AI类目 + CDN 图片 |
| 闲鱼商品发布 (预留) | 🟡 | 框架预留 (商品图片/价格/分类/成色) |
| 得物 | ✅ | Playwright 发布器 (v5.18 新增) |
| 什么值得买 | ✅ | Playwright 发布器 (v5.18 新增) |
| 小红书 | ✅ | Playwright 发布器 (v5.18 新增) |
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
| OSHWHub 签到 | ✅ | 成功率极低，存在问题 |
| CSDN 签到 | ✅ | 成功率 **0%**，已迁移至微信小程序 |
| Discuz! 签到 | ✅ | 表现正常 |
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
| Discuz 版块自动探索 | ✅ | Playwright 爬取，130 个版块 |
| 登录能力探索 | ✅ | 13 平台登录方式自动检测 + JSON 报告 |
| 探索数据 JSON→DB 迁移 | ✅ | v5.14 完成，platform_exploration 表 |
| 每小时增量轮询 | ✅ | 防风限流 + 双缓存 |
| 探索数据管理页面 | ✅ | 版块管理 + 关键词匹配 |
| 平台发布能力展示 | ✅ | 标签栏目管理 |
| 探索雷达 v2 | ✅ | 得物/什么值得买/小红书完整探索报告 |
| 登录能力自动刷新 | ✅ | 每 15 分钟自动轮询全平台 |
| Mydigit 探索数据 | ✅ | v5.20 新增 |

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
| **DeepSeek 余额** | ⚠️ | ¥36.52，偏低 |

### 4.8 📋 其他功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 审批流程 | ✅ | 创建/通过/拒绝/取消 + Webhook 端点 |
| 统一工作台流水线 | ✅ | Provider → 编译 → 预览 → 发布 |
| Provider 抽象框架 | ✅ | Markdown/Notion/淘宝 3 个 Provider |
| 评论监控引擎 | ✅ | Discuz 回复采集 + 去重 + AI 自动回帖 |
| AI 逛论坛 | ✅ | Discuz 帖子读取 + AI 筛选推荐 |
| 统一日志管理 | ✅ | v4.90 发布/签到/部署/AI 四表合一 Tab 页 |
| 文章编译缓存 | ✅ | compiled_cache + source_hash 变更检测 |
| 多格式渲染器 | ✅ | BBCode/MD/HTML/Richtext → 预览 HTML |
| 编译规则定义 | ✅ | 每平台图片/正文/BBCode 限制规则 |
| GitHub Pages 部署器 | ✅ | git push 自动部署 |
| AList 网盘存储 | ✅ | AList API 集成 |
| 移动端响应式 | ✅ | 375px 视口零水平溢出 |
| 论坛文章阅读器 | ✅ | Web 端论坛帖子阅读 |
| frpc 隧道 | ✅ | 5000 → 5001 外网暴露 |
| Docker 部署 | ✅ | python:3.11-slim |
| 验证码修复 | ✅ | v5.20 Playwright 元素截图替代 urllib |
| 浏览器死锁修复 | ✅ | v4.64 threading.Lock 不可重入修复 |
| QR 码线程安全 | ✅ | 22/22 测试通过 |
| Cookie 假阳性修复 | ✅ | v5.06 严格登录态检测 |

---

## 5. 待办事项

### 5.1 P0 — 阻塞级（影响核心功能）

| # | 事项 | 模块 | 问题 | 优先级 |
|---|------|------|------|--------|
| P0-1 | **CSDN 签到全部失败** | signin_csdn | 签到已迁移至微信小程序，现有 Playwright 逻辑失效 | 🔴 最高 |
| P0-2 | **OSHWHub 签到成功率极低** | signin_oshwhub | 需要排查 Cookie 过期/SSO 重登逻辑 | 🔴 最高 |
| P0-3 | **闲鱼 Cookie 已过期** | xianyu | 账号 Cookie 已失效，无法使用搜索/发布/价格监控 | 🔴 最高 |
| P0-4 | **DeepSeek API 余额偏低** | ai_provider | ¥36.52，AI 调用可能受限制 | 🔴 最高 |

### 5.2 P1 — 重要级

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P1-1 | **通知网关无已启用渠道** | gateway | 22 渠道可用但未配置任一端点，事件通知全部丢失 | 🟠 高 |
| P1-2 | **CSDN 签到实测验证** | signin | 需用户在场验证新方案 | 🟠 高 |
| P1-3 | **Bilibili/闲鱼V2/Twitter 发布实测** | publisher | 缺真实账号 E2E 验证 | 🟠 高 |
| P1-4 | **验证探索脚本完全修复** | exploration | flashsloth-exploration 脚本验证 | 🟠 高 |

### 5.3 P2 — 功能增强

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P2-1 | **签到调度逻辑优化** | scheduler | 减少重复签到检查，优化窗口匹配 | 🟡 中 |
| P2-2 | **API Gateway v2 文档** | api_v2 | API 网关框架就绪但缺少完整文档 | 🟡 中 |
| P2-3 | **视频模块** | core/video_compiler.py | 架构预留，实际未实现 | 🟡 中 |
| P2-4 | **商品模块** | core/product.py | 数据模型 + 编译器未实现 | 🟡 中 |
| P2-5 | **监控 PM 每日进度** | cron | flashsloth-pm-daily-progress 首次运行 | 🟡 中 |

### 5.4 P3 — 优化提升

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P3-1 | **单元测试覆盖** | tests | 测试文件缺少自动化运行 | 🟢 低 |
| P3-2 | **CI 流水线可用性** | .github/workflows | check_imports.py + test_core.py 仅基础检查 | 🟢 低 |
| P3-3 | **Git 工作区脏文件** | git | 5 个文件 modified but unstaged | 🟢 低 |

### 5.5 P4 — 远期规划

| # | 事项 | 模块 | 说明 | 优先级 |
|---|------|------|------|--------|
| P4-1 | **视频模块实现** | video | 剧本→转码→字幕→打包→多平台分发 | 🔵 远期 |
| P4-2 | **购物模块实现** | product | 闲鱼/淘宝搜索→比价→监控→自动下单 | 🔵 远期 |
| P4-3 | **AI 增强写作** | ai_provider | 写作风格学习 / 自动回复 / 语音操作 | 🔵 远期 |
| P4-4 | **Gallery 商品发布** | publisher | 预留的 Gallery 抽按商品发布 | 🔵 远期 |

### 5.6 已取消/不做

| 任务 | 原因 |
|------|------|
| FRPC 隧道自动管理 | 铁律禁止，frpc 独立守护 |
| browser-use/video-use 集成 FS | 仅学技能，不与 FS 绑定 |
| 闲鱼 AutoReply 运行/安装 | 只学代码思路移植，已移出 FS 目录 |
| CSDN 签到修复 | 用户说不做了 |
| 视频下载模块 | 不与 FS 绑定 |

---

## 6. 服务运行状态

### 6.1 运行中进程

| 服务 | 状态 | 说明 |
|------|------|------|
| **Flask** | ✅ Running | `python3 admin.py` (venv), 端口 5000 |
| **Hermes Gateway** | ✅ Running | Hermes Agent 消息网关 |
| **Hermes CLI** | ✅ Running | Hermes Agent 会话 |
| **frpc tunnel** | ✅ Running | 5000 → 103.97.178.234:5001 |
| **fs-scheduler** | ✅ Running | 签到调度守护线程 (60s loop) |

### 6.2 健康检查

| 项目 | 状态 | 备注 |
|------|------|------|
| Flask 进程 | ✅ | 持续运行 |
| 端口 5000 | ✅ | Flask 监听中 |
| frpc 隧道 | ✅ | 外网可访问 |
| 数据库文件 | ✅ | flashsloth.db (749KB), status_cache.db (12KB) |
| 加密密钥 | ✅ | .fs_key (44字节, 权限600) |
| 数据库 WAL 模式 | ✅ | 外键约束启用 |
| 模板热重载 | ✅ 已禁用 | 生产环境关闭 |

### 6.3 风险状态

| 风险点 | 严重度 | 说明 |
|--------|--------|------|
| 🔴 **闲鱼 Cookie 失效** | 高 | 无法使用闲鱼搜索/发布/价格监控 |
| 🔴 **CSDN 签到全失败** | 高 | 迁移至小程序后脱离现有 Playwright 逻辑 |
| 🟠 **DeepSeek 余额偏低 (¥36.52)** | 中 | AI 能力受限 |
| 🟠 **通知系统完全静默** | 中 | 22 渠道可用但无配置 → 事件无推送 |
| 🟢 **Git 工作区有未暂存文件** | 低 | 5 个文件 modified |

---

## 7. Cron Job 审计报告

> FlashSloth 的定时任务体系采用 **Hermes Cron** 管理，含应用内守护线程 (`fs-scheduler`) + Hermes 定时任务。

### 7.1 当前定时任务清单（24 个）

#### 核心执行任务（3 个）

| 任务 | 周期 | 状态 |
|------|------|:----:|
| flashsloth-autonomous-dev | 1,7,13,19 点 | ✅ |
| fs-auto-task-executor | 每 30 分钟 (错峰) | ✅ |
| FS 文档同步+代码审计看门狗 | 每 15 分钟 | ✅ |

#### E2E 测试任务（6 个）

| 任务 | 周期 | 状态 |
|------|------|:----:|
| E2E-01-登录会话 | 每日 12:00 | ⚠️ (4/6 通过) |
| E2E-02-账号管理 | 每日 2:00 | ⚠️ (12/14 通过) |
| E2E-03-发布工作台 | 每日 8:00 | ✅ |
| E2E-04-社区探索 | 每日 6:00 | ✅ |
| E2E-05-日志设置 | 每日 4:00 | ✅ |
| E2E-06-杂项 | 每日 18:00 | ✅ |

#### 脚本任务（4 个）

| 任务 | 周期 | 模式 | 状态 |
|------|------|------|:----:|
| FS 每日自动备份（三位一体） | 每日 4:30 | no-agent | ⚠️ (tar 文件变化) |
| 扫码登录 Session 清理+凭证健康检查 | 每 30 分钟 | no-agent | ✅ |
| FS 清理 | 每周日 3:00 | no-agent | ✅ |
| 添加账号修复计划 | 9,15,21 点 | agent | ✅ |

#### 暂停任务（7 个）

| 任务 | 原因 |
|------|------|
| 平台适配流水线-B站等 | 等探索完成 |
| 补探索-得物/什么值得买/小红书 | 等需要时 |
| 编码适配-小红书/得物/值得买 | 等探索完成 |
| 新平台适配项目-每日进度 | 等需要时 |
| flashsloth-exploration (每小时) | 已有 2 小时版本替代 |
| flashsloth-morning-report | DeepSeek 余额不足 |
| flashsloth-hardcode-audit-daily | PM 自己盯 |

#### 已清理（多个）

| 任务 | 删除原因 |
|------|----------|
| 3 个看门狗 (TODO/铁律/审计) | 功能重复，已合并到文档同步看门狗 |
| 开发说明书自动生成 | 低优先级 |
| README 中英同步 | 低优先级 |
| 日志统一管理页面 | 单次任务已完成 |
| UX 体验日报 | delivery error |
| 扫码登录优化项目 | 已完成 |
| flashsloth-pm-daily-progress | PM 自己盯 |
| code-review-weekly | 需要时手动触发 |
| weekly-regression | 需要时手动触发 |

### 7.2 签到调度分析

**架构**: `_tick_scheduler()` → 每分钟执行 → 基于时间窗口 + account_id 偏移触发

**时间窗口**: 默认 08:00 起 1 小时窗口内随机执行，支持 ±30min 随机偏移

**偏移机制**: 基于 account_id 确定性偏移，避免多账号同时签到

### 7.3 签到统计

| 平台 | 总数 | 成功 | 失败 | 诊断 |
|------|------|------|------|------|
| **Discuz!** | 11 | 5 | 6 | 表现正常 |
| **OSHWHub** | 65 | 3 | 62 | 成功率极低，SSO 问题 |
| **CSDN** | 5 | 0 | 5 | **0%** — 已迁移至微信小程序 |

### 7.4 论坛探索分析

| 平台 | 版块数 | 状态 |
|------|--------|------|
| forum_exploration 表 | 130 | ✅ 数据完整 |
| explore_cooldown 表 | 8 | ✅ 限流正常 |
| 探索报告文件 | 13 | ✅ 覆盖充分 |

---

## 8. 推荐推进计划

### 8.1 立即处理 (P0 — 本周)

#### P0-1: 闲鱼 Cookie 重新登录
```
□ 手动执行 QR 码扫码重新登录 xianyu
□ 验证搜索/发布功能可用
□ 配置 xianyu_v2 MTOP 发布器 Cookie
```

#### P0-2: OSHWHub 签到故障排查
```
□ 分析签到失败的 Playwright 日志
□ 检查 SSO Cookie 自动重登逻辑 (v5.19 已修复 SSO 登录)
□ 验证 v5.19 SSO 即时登录修复效果
```

#### P0-3: AI 供应商余额补充
```
□ 检查 DeepSeek API 余额/充值
□ 配置备用供应商
□ 或启用余额告警通知
```

### 8.2 重要事项 (P1 — 1~2周)

#### P1-1: 配置通知网关
```
□ 添加至少一个通知渠道 (飞书/企微/Telegram)
□ 配置签到失败 / 发布成功 / 价格报警等事件推送
□ 验证消息可达性
```

#### P1-2: 发布器 E2E 实测
```
□ Bilibili 发布实测
□ 闲鱼 V2 发布实测
□ Twitter 发布实测
```

### 8.3 功能增强 (P2 — 1个月)

#### P2-1: 签到调度逻辑优化
```
□ 减少重复签到检查
□ 优化窗口匹配
□ 增加签到失败自动重试
```

#### P2-2: Gateway API v2 文档与测试
```
□ 编写 api_v2 路由的完整文档
□ 端到端测试每个端点
```

### 8.4 长期推进 (P3-P4 — 1~3个月)

| 阶段 | 内容 | 时间预估 |
|------|------|----------|
| **Phase 0: 基础设施完善** | 网关配置 + 供应商余额管理 | 1 周 |
| **Phase 1: 稳定性提升** | 签到修复 + 发布器 E2E 实测 | 1-2 周 |
| **Phase 2: 测试覆盖** | 单元测试增强 + API 测试 | 2 周 |
| **Phase 3: 购物模块** | 商品数据模型 + 编译器 + 价格监控增强 | 2-3 周 |
| **Phase 4: 视频模块** | 视频数据模型 + 编译流水线 + B站分发 | 2-3 周 |
| **Phase 5: AI 增强** | 写作风格学习 / 自动回复 / 语音操作 | 持续 |

### 8.5 关键指标 (KPI)

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| Discuz 签到成功率 | ~45% | > 95% |
| OSHWHub 签到成功率 | ~4.6% | > 90% |
| CSDN 签到成功率 | 0% | 标注"已迁移" |
| 闲鱼 Cookie 有效 | ❌ | ✅ |
| 通知网关配置 | 0 渠道 | ≥ 2 渠道 |
| Git 同步状态 | 已推送 | up to date |
| AI 调用成功率 | ✅ | > 95% |

---

## 附录 A: 版本变更历史 (v4.60 → v5.21)

| 版本 | 日期 | 关键变更 |
|------|------|---------|
| **v5.21** | 2026-07-08 | Amobbs 验证码四大修复 (.seccodecheck分流/跨线程刷新/提交回归/border click误触) + 铁律 #41(文档同步) #42(Bug记录) + docs/bug-fixes/ 创建 + 文档全面审计 |
| **v5.20** | 2026-07-08 | Amobbs 验证码修复 (Playwright 元素截图+前端 base64) + 铁律 #40 + Mydigit 探索数据 |
| v5.19 | 2026-07-07 | OSHWHub SSO 登录修复 + 验证码检测前置 |
| v5.18 | 2026-07-06 | 39 项铁律 #19 硬编码违规全量修复 + 3 新 Publisher (得物/什么值得买/小红书) |
| v5.16-17 | 2026-07-05 | 登录引擎数据驱动 + 账号管理模块化拆分 + 前端 JS 模块化 |
| v5.14 | 2026-07-04 | 探索数据 JSON→DB 迁移 (platform_exploration 表) |
| v4.92 | 2026-07-02 | 统一凭证体系 (ScanLoginEngine + Cookie 验证器) |
| v4.90 | 2026-07-01 | 统一日志管理页面 |
| v4.64 | 2026-06-30 | 浏览器死锁修复 (threading.Lock 不可重入) |
| v4.60 | 2026-06-29 | 签到统计增强 + 部署配置增强 |

---

## 附录 B: 文件结构树

```
flashsloth/
├── admin.py                 # 入口点
├── ARCHITECTURE.md          # 架构文档
├── README.md                # 项目说明
├── DEVELOPMENT_SPECIFICATION.md  # 开发说明书
├── PROJECT_STATUS.md        # 项目状态
├── PROJECT_PANORAMA_REPORT.md    # 本报告
├── Dockerfile               # Docker 部署
├── requirements.txt         # Python 依赖
├── frpc.toml                # frpc 隧道配置
├── .fs_key                  # Fernet 加密密钥 (600权限)
├── flashsloth.db            # SQLite 主数据库 (749KB)
├── status_cache.db          # 状态缓存 (12KB)
│
├── core/                    # 核心引擎 (33 Python 文件)
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
│   ├── credential_guard.py  # 凭证守护 (v4.92)
│   ├── credential_provider.py # 统一扫码登录引擎 (v4.92)
│   ├── cookie_validator.py  # 统一 Cookie 验证器 (v4.92)
│   ├── database.py          # 数据库初始化
│   ├── deployer.py          # 部署器基类
│   ├── explorer.py          # 论坛探索引擎
│   ├── forum_registry.py    # 版块注册中心
│   ├── gateway.py           # 通知网关核心
│   ├── image_pipeline.py    # 图片流水线
│   ├── notifier.py          # 统一通知系统
│   ├── pipeline.py          # 内容流水线
│   ├── platform_exploration_loader.py # 探索数据 DB 导入 (v5.14)
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
├── routes/                  # 蓝图层 (22 文件)
│   ├── __init__.py          # 路由中心
│   ├── accounts/            # 账号管理包 (v5.14 拆分)
│   │   ├── __init__.py
│   │   ├── crud.py          # 账号 CRUD
│   │   ├── helpers.py       # 辅助函数
│   │   ├── login.py         # 登录流程
│   │   ├── qrcode.py        # QR 扫码
│   │   ├── search.py        # 搜索/筛选
│   │   └── status.py        # 状态检测
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
│   ├── external_services.py # 外部服务
│   ├── forum.py             # 论坛阅读器
│   ├── gateway.py           # 通知网关
│   ├── logs.py              # 统一日志管理 (v4.90)
│   ├── notifications.py     # 通知系统
│   ├── platforms.py         # 平台预设
│   ├── posts.py             # 文章管理
│   ├── price_monitor.py     # 价格监控
│   ├── signin.py            # 签到管理
│   ├── storage_deploy.py    # 存储/部署
│   ├── workspace_ui.py      # 工作台
│   └── xianyu_search.py     # 闲鱼搜索
│
├── plugins/                 # 插件层
│   ├── publisher_*.py       # 19 个发布器
│   ├── signin_*.py          # 3 个签到插件
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
│   ├── provider_taobao.py   # 淘宝 Provider
│   ├── deployer_github_pages.py  # GitHub Pages 部署
│   ├── storage_alist.py     # AList 存储
│   └── xianyu_client/       # 闲鱼 MTOP SDK
│
├── sdk/                     # SDK 适配器层
│   ├── adapter.py           # 统一基类
│   ├── router.py            # 内容路由
│   ├── scaffold.py          # 脚手架生成
│   └── adapters/            # 15 平台实现
│
├── templates/               # 36 个 HTML 模板
│   └── accounts/            # 账号管理子模板 (v5.14)
├── static/                  # 静态资源
├── config/                  # 平台配置
├── platform_reports/        # 探索报告 (13 平台)
├── scripts/                 # 运维脚本
├── tests/                   # 测试文件
├── storage/                 # 本地存储
├── .github/workflows/       # CI/CD
└── .agents/                 # Agent 工作区
```

---

*报告由 AI 自动生成于 2026-07-08。数据来源: 代码文件分析 + SQLite 数据库查询 + 进程状态检查 + Git 日志。*