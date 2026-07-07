# 🦥 FlashSloth 开发说明书

**版本**: v4.56 | **最后更新**: 2026-07-07 (每小时自动更新)
**架构对照**: ✅ 已核对 ARCHITECTURE.md

---

## 一、项目概述

**定位**：个人数字资产全聚合平台 — 一个后台管理你在互联网上的所有数字资产：文章、视频、商品、账号。

**目标用户**：技术创作者 / 多平台运营者 / 数码爱好者，需要一个统一后台完成账号管理、内容采集、AI 编译、多平台分发和签到巡检。

**核心能力**：
- 多平台账号统一管理（Discuz/CSDN/知乎/掘金/B站/闲鱼/OSHWHub/GitHub Pages）
- 文章发布流水线：采集 → AI 编译 → 预览 → 存草稿 → 发布
- 自动签到调度（Discuz/CSDN/OSHWHub）
- 闲鱼商品搜索 + 价格监控（LCSC 元器件）
- 通知网关多终端推送（Webhook/飞书/企微/个人微信）
- 论坛探索引擎（Playwright 自动爬取版块结构）
- AI 能力路由（写作/翻译/图像生成等多供应商切换）
- API v2 网关（RESTful 对外接口，支持 API Key + Session 认证）
- 评论监控引擎（定时检查帖子回复 + AI 自动回帖）
- 工作台流水线（Provider → 编译 → 预览 → 发布统一调度）

---

## 二、系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    用户界面层 (Flask Web UI)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ 仪表盘   │ │ 文章管理  │ │ 签到管理  │ │ 闲鱼搜索/价格监控  │   │
│  │ 总览     │ │ 发布/预览 │ │ 状态/统计 │ │ 搜索/比价/报警    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ 账号管理  │ │ 配置中心  │ │ 探索数据  │ │ 通知网关 + 审批  │   │
│  │ 多平台   │ │ AI/存储  │ │ 版块/关键词│ │ 飞书/企微/微信  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ 工作台   │ │ 评论监控  │ │ 论坛阅读  │ │ AI 调用日志      │   │
│  │ Provider │ │ 收件箱/  │ │ AI逛论坛  │ │ 分页/筛选/统计   │   │
│  │ +流水线  │ │ 自动回复  │ │ 推荐      │ │                  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   Gateway API 层 (routes/)                        │
│  routes/__init__.py — 路由中心（应用工厂，注册所有 Blueprint）    │
│  routes/_app.py      — 共享 Flask 实例 (app, login_manager, User) │
│  routes/auth.py      — 登录/注册/改密/设置/首页                  │
│  routes/accounts.py  — 账号 CRUD + 配置 + 状态检测               │
│  routes/gateway.py   — 通知网关渠道管理                          │
│  routes/ai.py        — AI 供应商管理 + 余额查询 + 生成 + 日志    │
│  routes/signin.py    — 签到状态/手动签到/API                     │
│  routes/exploration.py — 论坛探索数据管理                        │
│  routes/price_monitor.py — 价格监控管理                          │
│  routes/approval.py  — 审批流程管理                              │
│  routes/browser_login.py — Playwright 浏览器登录路由             │
│  routes/xianyu_search.py — 闲鱼搜索 API                          │
│  routes/api_v1.py    — 原始 API v1 + API Key 鉴权               │
│  routes/api_v2.py    — RESTful Gateway API v2                   │
│  routes/platforms.py — 平台预设配置                              │
│  routes/posts.py     — 文章 CRUD + 发布路由                      │
│  routes/notifications.py — 通知系统轮询 API                      │
│  routes/pipeline_ui.py — 内容流水线 UI                          │
│  routes/forum.py     — 论坛文章阅读器                            │
│  routes/storage_deploy.py — 存储/部署器配置                      │
│  routes/captcha_browser.py — 验证码浏览器路由                    │
│  routes/comment_monitor.py — 评论监控路由(收件箱+AutoReply)      │
│  routes/workspace_ui.py — 工作台路由(Provider+流水线+日志API)    │
│  routes/browser_engine.py — Playwright 浏览器引擎启停控制+API   │
│  routes/external_services.py — 外部服务注册表+管理入口           │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   统一工作流引擎 (core/)                           │
│  core/publisher.py       — Publisher 基类 + 注册机制              │
│  core/gateway.py         — 通知网关核心（Provider 注册表）        │
│  core/scheduler.py       — 签到调度器（守护线程定时签到）          │
│  core/database.py        — 数据库初始化 + 连接 + 种子数据         │
│  core/credential_crypto.py — Fernet AES-128-CBC 凭证加密          │
│  core/anti_detect.py     — Playwright 反检测/人类行为模拟         │
│  core/explorer.py        — Playwright 论坛探索引擎               │
│  core/price_monitor.py   — LCSC 元器件价格监控                   │
│  core/approval.py        — 审批流程系统                          │
│  core/ai_provider.py     — AI Provider 统一框架 + 路由           │
│  core/notifier.py        — 统一通知系统                          │
│  core/article.py         — 文章数据模型                           │
│  core/deployer.py        — 部署器基类                            │
│  core/config.py          — 全局配置加载                           │
│  core/storage.py         — 存储抽象层 (LocalStorage, AlistStorage)│
│  core/image_pipeline.py  — 图片处理流水线                        │
│  core/captcha_handler.py — 验证码处理器                          │
│  core/compiler.py        — 文章编译器 (MD→IR→输出)               │
│  core/pipeline.py        — 内容流水线调度器(采集→编译→预览→发布)  │
│  core/provider.py        — Provider 统一内容来源基类 + 注册机制   │
│  core/signin.py          — SigninBase 签到基类 + 注册机制        │
│  core/status_detector.py — 三层登录状态检测器                    │
│  core/status_cache.py    — 账号状态缓存系统(内存+SQLite持久化)    │
│  core/forum_registry.py  — 统一智能版块匹配系统                   │
│  core/compiled_cache.py  — 编译产物数据库缓存                    │
│  core/renderers.py       — 各平台编译产物渲染器(预览HTML)         │
│  core/compile_rule.py    — 每平台编译规则定义(图片/正文/BBCode)   │
│  core/provider_registry.py — 动态AI供应商注册表                   │
│  core/browser_engine.py  — 常驻Playwright浏览器引擎(全局单例)     │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                    发布器 + 适配器层 (plugins/ + sdk/)            │
│  plugins/publisher_*.py      — 各平台发布器实现                  │
│  plugins/signin_*.py         — 各平台签到插件                    │
│  plugins/generic_login.py    — 通用 Playwright 登录              │
│  plugins/browser_session.py  — 人机浏览器模拟（已废弃，参考用）  │
│  plugins/forum_signin.py     — 论坛签到 Orchestrator            │
│  plugins/forum_reader.py     — AI逛论坛(Discuz帖子读取+AI筛选)   │
│  plugins/reply_monitor.py    — 评论监控引擎(采集+去重+AI回帖)    │
│  plugins/xianyu_login.py     — 闲鱼 Playwright 登录器           │
│  plugins/amobbs_login.py     — 阿莫论坛特殊验证码登录器          │
│  plugins/xianyu_client/      — 闲鱼 MTOP API 签名客户端包        │
│  plugins/xianyu/             — 闲鱼核心 API 层(旧版)            │
│  plugins/storage_alist.py    — AList 网盘存储插件               │
│  plugins/provider_markdown.py — Markdown 文件 Provider          │
│  plugins/provider_notion.py  — Notion API Provider              │
│  plugins/deployer_github_pages.py — GitHub Pages 部署器          │
│  sdk/adapter.py              — PlatformAdapter 统一基类          │
│  sdk/router.py               — 内容路由引擎                     │
│  sdk/scaffold.py             — 适配器脚手架生成器                │
│  sdk/adapters/*.py           — 各平台适配器实现(15个)           │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   公共基础设施层                                   │
│  SQLite (flashsloth.db) + status_cache.db / .fs_key 加密密钥     │
│  config/ 配置文件 + platform_reports/ 探索报告                    │
│  static/ 静态资源 + templates/ HTML 模板(30个)                   │
│  scripts/ — 定时/运维脚本(论坛探索/关键词同步/数据合并)           │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 用户界面层
| 页面 | 路由 | 模板 | 功能 |
|------|------|------|------|
| 仪表盘 | `GET /` | index.html | 文章/账号概览、发布日志 |
| 账号管理 | `GET /accounts` | accounts.html | 多平台账号 CRUD + 登录 |
| 签到管理 | `GET /signin` | signin.html | 签到状态/手动签到/统计 |
| 通知网关 | `GET /gateway` | gateway.html | 通知渠道配置/测试 |
| 探索数据 | `GET /exploration` | exploration.html | 论坛板块/发布能力/标签 |
| AI 配置 | `GET /ai-settings` | ai_settings.html | AI 供应商/模型管理 |
| 价格监控 | `GET /price-monitor` | price_monitor.html | LCSC 价格追踪/报警 |
| 审批管理 | `GET /approval` | approval.html | 发布审批/历史 |
| 闲鱼搜索 | `GET /xianyu/search` | xianyu_search.html | 闲鱼商品搜索 |
| 工作台 | `GET /workspace` | workspace.html | Provider选择+流水线+日志 |
| 评论监控 | `GET /comment-monitor` | comment_monitor.html | 帖子回复收件箱+AutoReply |
| 文章管理 | — | publish_manage/compile_preview/editor | 发布/编辑/预览 |
| 设置 | — | settings.html/storage_settings.html | 存储/部署器配置 |
| 通知 | — | notifications.html | 站内通知列表 |
| AI日志 | `GET /ai/logs` | ai_logs.html | AI调用日志查询 |
| 论坛阅读器 | `GET /forum/reader/<id>` | forum_reader.html | 论坛帖子阅读 |

### 2.2 业务逻辑层
| 模块 | 位置 | 说明 |
|------|------|------|
| 发布器调度 | core/publisher.py | Publisher 注册表 + 调度 |
| 通知网关 | core/gateway.py | 多终端消息广播 |
| AI 路由 | core/ai_provider.py | 多供应商 AI 能力框架 |
| 签到调度 | core/scheduler.py | 定时签到执行器 |
| 探索引擎 | core/explorer.py | Playwright 论坛探索+限流 |
| 凭证加密 | core/credential_crypto.py | Fernet AES 加密 |
| 反检测 | core/anti_detect.py | 人类行为模拟中间件 |
| 价格监控 | core/price_monitor.py | LCSC 元器件价格查询 |
| 审批系统 | core/approval.py | 敏感操作审批流程 |
| 统一通知 | core/notifier.py | 站内信+网关广播 |
| Provider 基类 | core/provider.py | 统一内容来源接口(@register_provider) |
| 签到基类 | core/signin.py | SigninBase + @register 注册机制 |
| 登录状态检测 | core/status_detector.py | 三层检测(API轻量→Playwright快速→全量) |
| 账号状态缓存 | core/status_cache.py | 内存缓存(5min TTL)+SQLite持久化 |
| 版块注册中心 | core/forum_registry.py | 统一智能版块匹配(从platform_reports加载) |
| 编译缓存 | core/compiled_cache.py | 编译产物DB缓存+source_hash变更检测 |
| 渲染器 | core/renderers.py | BBCode/MD/HTML/Richtext→预览HTML |
| 编译规则 | core/compile_rule.py | ImageRule/BodyFormat/BBCode限制 |
| AI供应商注册表 | core/provider_registry.py | 动态加载provider_registry.json |
| 流水线调度器 | core/pipeline.py | 5阶段流水线(Collect→Compile→Preview→Draft→Publish) |
| 浏览器引擎 | core/browser_engine.py | 常驻Playwright浏览器进程(全局单例,10min自动关闭)|

### 2.3 数据层
- **数据库**: SQLite (`flashsloth.db`) — WAL 模式 + 外键约束
- **状态缓存**: `status_cache.db` — 独立 SQLite 缓存数据库
- **加密凭证**: `.fs_key` — Fernet 密钥文件，权限 600
- **平台配置**: `config/platform_*.json` — 平台预设
- **探索报告**: `platform_reports/*.json` — 论坛板块结构
- **AI 能力**: `config/ai_capabilities.json` — AI 供应商能力配置
- **AI供应商注册表**: `core/provider_registry.json` — 动态供应商预设
- **平台预设**: `core/platform_presets.json` — 全局平台配置

---

## 三、模块详细说明

### 3.1 账号管理模块 (`routes/accounts.py` + `templates/accounts.html`)

- **功能说明**: 多平台账号的统一管理界面，支持添加、编辑、删除、启用/禁用、配置查看、登录状态检测
- **API 端点**:
  - `GET /accounts` — 账号管理页面（按平台分组展示）
  - `POST /accounts/add` — 新增/更新账号（含加密配置存储）
  - `DELETE /accounts/delete/<aid>` — 删除账号
  - `GET /api/accounts/config/<aid>` — 获取脱敏配置
  - `POST /api/accounts/<aid>/toggle` — 切换启用/禁用
  - `GET /api/accounts/<aid>/status` — 三层登录状态检测(API轻量→Playwright快速→全量)
- **登录方式**: 密码 / 二维码扫码 / Cookie 粘贴（由各 Publisher 定义 `login_methods`）
- **数据流**: 用户表单提交 → `encrypt_config()` 加密敏感字段 → 存入 `platform_accounts.config_json`
- **关键逻辑**:
  - 配置脱敏（password/cookie/token 等显示为 `••••••••`）
  - 编辑时掩码字段保留原值
  - 自动生成不重名默认别名（`<platform>01`, `<platform>02` 等）
  - 状态检测使用 `core/status_detector.py` 三层引擎 + `core/status_cache.py` 缓存(5min TTL)

### 3.2 发布器模块 (`plugins/publisher_*.py`)

所有 Publisher 继承 `core/publisher.py` 的 `Publisher` 基类，通过 `@register` 装饰器注册。

| 发布器 | 类名 | 登录方式 | 特点 |
|--------|------|----------|------|
| `Discuz! 论坛` | `DiscuzPublisher` | 密码+验证码 / QR扫码 / Cookie | 多域名限制(`amobbs.com`/`mydigit.cn`)，图片/附件限制 |
| `CSDN` | `CSDNPublisher` | 密码登录 | Playwright 浏览器自动化，Markdown 编辑器 |
| `知乎` | `ZhihuPublisher` | Cookie 登录 | Playwright 自动化，专栏编辑 |
| `掘金` | `JuejinPublisher` | 密码/QR/Cookie | 模拟浏览器请求 (requests) |
| `Bilibili 专栏` | `BilibiliPublisher` | 密码/QR/Cookie | Bilibili API + Cookie 认证 |
| `OSHWHub` | `OshwhubPublisher` | JLC 统一登录 | Playwright + 即时代理登录 |
| `闲鱼 (v1)` | `XianyuPublisher` | 密码/QR/Cookie | 基于 XianyuAutoAgent API |
| `闲鱼 V2 (MTOP)` | `XianyuV2Publisher` | Cookie 导入 | MTOP 签名 API + AI 类目 |
| `闲鱼商品发布(预留)` | `XianyuProductsPublisher` | 密码/Cookie | 框架预留(商品图片/价格/分类/成色) |
| `GitHub Pages` | `GitHubPagesBlogPublisher` | 无需登录 | 本地 Markdown 文件写入 + git push |
| `Twitter` | `TwitterPublisher` | — | — |
| `微信公众号` | `WechatPublisher` | — | — |
| `WordPress` | `WordPressPublisher` | — | — |
| `RSS` | `RSSPublisher` | — | — |

**通用发布流程**: `publish(Article)` → `process_images(Article)` → 平台特定 HTTP/Playwright → 返回 `{success, url, id, error}`

### 3.3 网关通知模块 (`routes/gateway.py` + `core/gateway.py`)

- **功能说明**: 统一消息通知网关，将系统事件通过多终端推送
- **GatewayMessage**: title / body / level / source / link / timestamp
- **支持的 Provider**:
  - `webhook` — 通用 HTTP Webhook
  - `feishu` — 飞书/Lark 机器人
  - `wecom` — 企业微信机器人
  - `wechat` — 个人微信 (iLink Bot API)
  - `discord`, `slack`, `telegram`, `email` (通过 Hermes Gateway 移植)
- **API 端点**:
  - `GET /gateway` — 网关配置页面
  - `POST /api/gateway/channels` — 添加渠道
  - `PUT /api/gateway/channels/<id>` — 更新渠道
  - `DELETE /api/gateway/channels/<id>` — 删除渠道
  - `POST /api/gateway/channels/<id>/test` — 测试发送
  - `GET /api/gateway/channels` — 渠道列表
- **消息流**: `notify()` → `Gateway.dispatch()` → `[Provider1.send(), Provider2.send(), ...]`

### 3.4 签到模块 (`core/scheduler.py` + `core/signin.py` + `plugins/signin_*.py` + `plugins/forum_signin.py`)

- **功能说明**: 定时自动签到，守护线程每分钟检查
- **架构**: `core/signin.py` 定义 SigninBase 基类 + 注册中心 → `plugins/signin_*.py` 各平台实现 → `plugins/forum_signin.py` Orchestrator 遍历账号匹配插件
- **签到窗口**: 配置时间（默认 08:00）起 1 小时窗口内随机执行
- **已今日签过判断**: 查询 `signin_log` 表
- **签到插件**:
  | 插件 | 文件 | 平台 | 实现方式 |
  |------|------|------|----------|
  | `signin_discuz` | `plugins/signin_discuz.py` | Discuz! (k_misign) | Playwright |
  | `signin_csdn` | `plugins/signin_csdn.py` | CSDN | Playwright (注: 已迁移至微信小程序) |
  | `signin_oshwhub` | `plugins/signin_oshwhub.py` | OSHWHub | Playwright |
- `forum_signin.py` 动态导入所有 `signin_*.py` 插件，自动调用 `get_signin_for_account()` 匹配
- **API 端点**:
  - `GET /signin` — 签到页面（状态/统计）
  - `POST /api/signin/run/<account_id>` — 手动签到
  - `POST /api/signin/run_all` — 全部签到
  - `POST /api/signin/schedule` — 设置签到时间
  - `GET /api/signin/status` — 调度器状态
  - `GET /api/signin/stats` — 签到统计

### 3.5 探索模块 (`core/explorer.py` + `core/forum_registry.py` + `scripts/`)

- **功能说明**: Playwright 自动爬取论坛版块结构存入 `forum_exploration` 表
- **限流规则**: 每域名每小时最多探索一次（`explore_cooldown` 表持久化）
- **核心流程**: 检测论坛类型 → 爬取版块列表 → 对比差异 → 保存到 DB
- **版块注册中心** (`core/forum_registry.py`): 从 `platform_reports/*.json` 自动加载论坛版块数据，支持版块关键词匹配，自动跳过 www 前缀去重
- **支持平台**: Discuz! (amobbs.com, mydigit.cn 等)
- **种子数据**: 从 `platform_reports/*.json` 加载
- **定时脚本**: `scripts/hourly_forum_check.py` — 每小时增量检查 Discuz 论坛版块变更
- **辅助脚本**:
  | 脚本 | 功能 |
  |------|------|
  | `scripts/hourly_forum_check.py` | 每小时增量检查论坛版块变更 |
  | `scripts/sync_registry_keywords.py` | 将 forum_registry 关键词同步到 forum_exploration DB |
  | `scripts/consolidate_forum_data.py` | 合并 www 前缀数据到非 www 域名，去重 |
  | `scripts/compare_forum_data.py` | 对比新旧论坛数据差异 |
- **API 端点**:
  - `GET /exploration` — 探索数据管理页面
  - `GET /api/exploration/platforms` — 平台列表
  - `GET /api/exploration/platform/<domain>` — 平台详情（版块/能力/标签）
  - `POST /api/exploration/explore` — 启动探索
  - `POST /api/exploration/tags` — 更新关心标签/关键词
  - `GET /api/exploration/section/<sid>` — 板块详情

### 3.6 凭证安全模块 (`core/credential_crypto.py`)

- **加密方式**: Fernet (AES-128-CBC + HMAC-SHA256) 对称加密
- **密钥来源**: `~/.hermes/flashsloth/.fs_key`（自动生成）或环境变量 `FS_ENCRYPTION_KEY`
- **敏感字段**: password, cookie, token, app_secret, api_key, access_token, refresh_token
- **加密标记**: 加密后值以 `enc:` 前缀标记
- **向下兼容**: 非 `enc:` 前缀的值原样返回（兼容旧数据）

### 3.7 反检测模块 (`core/anti_detect.py`)

- **核心原则**: 像真人一样操作，不触发平台反爬机制
- **能力清单**:
  - Viewport 随机选择（5 种分辨率）
  - UA 随机选择（Chrome/Edge/Firefox）
  - 鼠标随机移动（像素+间隔）
  - 键盘随机打字延迟
  - 操作间随机等待
  - 滚动距离随机
  - 时间偏移设置（Asia/Shanghai）
- **使用方式**: `create_human_context(browser)` → 返回配置好的人类模拟浏览器上下文
- **环境变量可覆盖**: AD_MOUSE_MIN/MAX, AD_TYPE_DELAY_MIN/MAX, AD_OP_WAIT_MIN/MAX, AD_SCROLL_MIN/MAX

### 3.8 AI 路由模块 (`core/ai_provider.py`)

- **功能说明**: 统一 AI 能力框架，每个服务商写一个 Provider 注册到全局注册表
- **支持能力类型**: writing / image_gen / audio_gen / video_gen / translate
- **AIRequest 模型**: capability / prompt / model / provider / images / context / temperature / max_tokens
- **路由配置**: 存储在 `provider_config` 表，支持多供应商并行/自动切换
- **余额查询**: DeepSeek/OpenAI 余额 API
- **AI 调用日志**: 自动记录每次调用的元数据到 `ai_call_log` 表，包含 token 数/费用/成功失败
- **Provider 注册表** (`core/provider_registry.py`): 从 `core/provider_registry.json` 动态加载供应商预设，支持运行时添加自定义供应商，统一 OpenAI 兼容格式调用
- **API 端点**:
  - `GET /api/ai/providers` — 列出所有 Provider 及能力
  - `GET /api/ai/config` — AI 路由配置
  - `POST /api/ai/config` — 更新配置
  - `POST /api/ai/generate` — AI 生成
  - `GET /api/ai/balances` — 余额查询
  - `GET /api/ai/logs` — AI调用日志分页查询
  - `POST /api/ai/logs/clear` — 清空AI调用日志

### 3.9 闲鱼集成模块

| 子模块 | 位置 | 功能 |
|--------|------|------|
| 搜索路由 | `routes/xianyu_search.py` | 闲鱼关键词搜索 API |
| 商品搜索 API | `POST /api/xianyu/search` | 关键词/价格范围/排序/分页 |
| 发布器 v1 | `plugins/publisher_xianyu.py` | 基于 XianyuAutoAgent API |
| 发布器 v2 | `plugins/publisher_xianyu_v2.py` | MTOP 签名 API + AI 类目 + CDN 图片 |
| 发布器(商品预留) | `plugins/publisher_xianyu_products.py` | 框架预留(商品图片/价格/分类/成色) |
| SDK v2 适配器 | `sdk/adapters/xianyu_v2.py` | 搜索/详情/比价/Token 管理 |
| MTOP 客户端 | `plugins/xianyu_client/` | 纯 Python MTOP 签名包 |
| 旧 API 兼容 | `plugins/xianyu/XianyuApis.py` | 闲鱼核心 API 层 |
| Playwright 登录器 | `plugins/xianyu_login.py` | 淘宝 SSO 登录(扫码/验证码/密码) |

**MTOP 客户端 (`plugins/xianyu_client/`) 子模块**:
| 文件 | 功能 |
|------|------|
| `mtop.py` | MTOP API 调用 |
| `sign.py` | 签名生成 |
| `session.py` | Cookie 会话管理 |
| `media.py` | 图片上传到闲鱼 CDN |
| `category.py` | AI 类目推荐 |
| `location.py` | 默认地址获取 |
| `guard.py` | 风控监控 |
| `limiter.py` | 频率限制(3次/分钟) |
| `errors.py` | 错误类型定义 |

### 3.10 价格监控模块 (`core/price_monitor.py` + `routes/price_monitor.py`)

- **功能说明**: LCSC（立创商城）元器件价格追踪
- **API 端点**:
  - `GET /price-monitor` — 监控管理页面
  - `GET /api/price-monitor/accounts` — 支持监控的平台账号
  - `POST /api/price-monitor/add` — 添加监控
  - `DELETE /api/price-monitor/<id>` — 删除监控
  - `POST /api/price-monitor/<id>/refresh` — 刷新价格
- **数据表**: `price_monitors` + `price_history`

### 3.11 审批系统 (`core/approval.py` + `routes/approval.py`)

- **功能说明**: AI 发起的敏感操作审批流程（发布/删除/修改）
- **流程**: `create_approval()` → 通知网关推送 → 管理员回复 → `process_approval()`
- **状态机**: pending → approved/rejected/expired/cancelled
- **API 端点**:
  - `GET /approval` — 审批页面
  - `GET /api/approval/pending` — 待审批列表
  - `GET /api/approval/history` — 审批历史
  - `POST /api/approval/<id>/respond` — 通过/拒绝

### 3.12 通知系统 (`core/notifier.py` + `routes/notifications.py`)

- **统一通知接口**: `notify()`, `notify_info()`, `notify_warn()`, `notify_error()`
- **自动广播**: 当网关有已启用终端时，自动通过网关广播
- **数据表**: `notifications`

### 3.13 SDK 平台适配器层 (`sdk/`)

| 文件 | 功能 |
|------|------|
| `sdk/adapter.py` | PlatformAdapter 基类 + Article/Comment/AdapterCapability 数据模型 |
| `sdk/router.py` | 内容路由引擎（RouteRule → source→target） |
| `sdk/scaffold.py` | 适配器脚手架生成器(一键生成新平台适配器模板) |
| `sdk/adapters/xianyu_v2.py` | 闲鱼 API v2 适配器（搜索/详情/比价） |
| `sdk/adapters/xianyu.py` | 闲鱼 PlatformAdapter（Playwright浏览器自动化） |
| `sdk/adapters/bilibili.py` | B站适配器 |
| `sdk/adapters/csdn.py` | CSDN 适配器 |
| `sdk/adapters/zhihu.py` | 知乎适配器 |
| `sdk/adapters/juejin.py` | 掘金适配器 |
| `sdk/adapters/oshwhub.py` | OSHWHub 适配器 |
| `sdk/adapters/amobbs.py` | 阿莫论坛适配器 |
| `sdk/adapters/mydigit.py` | 数码之家适配器 |
| `sdk/adapters/wordpress.py` | WordPress 适配器 |
| `sdk/adapters/wechat.py` | 微信适配器 |
| `sdk/adapters/notion.py` | Notion 适配器 |
| `sdk/adapters/github_pages.py` | GitHub Pages 适配器 |
| `sdk/adapters/giscus.py` | Giscus 适配器 |

### 3.14 部署管理模块 (`routes/storage_deploy.py` + `core/deployer.py`)

部署管理负责将静态站点发布到托管平台（GitHub Pages 等）。支持插件化注册机制：
- `core/deployer.py` — Deployer 抽象基类 + `@register` 注册器
- `plugins/deployer_github_pages.py` — GitHub Pages 部署实现
- `routes/storage_deploy.py` — 部署配置管理页面 + API
- 数据库 `deployer_configs` 表保存用户部署配置

### 3.15 工作台模块 (`routes/workspace_ui.py` + `core/provider.py` + `core/pipeline.py`)

工作台整合 Provider 选择 + 流水线 + 内容日志：
- `core/provider.py` — Provider 抽象基类（ContentItem 模型 + `@register_provider` 装饰器）
- `core/pipeline.py` — 统一内容流水线调度器，5 阶段 PipelineStage (Collect→Compile→Preview→Draft→Publish)
- `plugins/provider_markdown.py` — 扫描 posts/ 目录的 Markdown 文件
- `plugins/provider_notion.py` — 通过 Notion API 读取数据库
- `routes/workspace_ui.py` — 工作台页面 + API 端点
- **API 端点**:
  - `GET /workspace` — 工作台主页（Provider 列表 + 内容类型）
  - `GET /pipeline` — 向后兼容重定向到 `/workspace`
  - `GET /api/workspace/providers` — 列出所有 Provider
  - `GET /api/workspace/provider/<name>/items` — 获取 Provider 内容列表
  - `GET /api/workspace/provider/<name>/item/<item_id>` — 获取内容详情
  - `POST /api/workspace/run` — 执行流水线(采集→编译→发布)
  - `GET /api/workspace/history` — 流水线运行历史
  - `GET /api/workspace/logs/publish` — 发布记录
  - `GET /api/workspace/logs/collect` — 采集记录

### 3.16 AI 调用日志模块 (`core/ai_provider.py` + `routes/ai.py`)

自动记录每一次 AI 调用的元数据（模型、token数、费用、成功/失败）：
- `ai_call_log` 表：id/capability/provider/model/prompt_tokens/response_tokens/cost/success/error/response_summary/prompt_preview/created_at
- `log_ai_call()` — 导出日志函数，在 `AIRouter.call()` 的双路径中自动调用
- `/ai/logs` — 日志查看页面（分页、按能力筛选、按状态筛选）
- `/api/ai/logs` — 分页查询 API
- `/api/ai/logs/clear` — 清空日志 API

### 3.17 评论监控模块 (`plugins/reply_monitor.py` + `routes/comment_monitor.py`)

- **功能说明**: 定时检查各论坛已发表帖子的新回复，AI 生成智能回帖
- **核心组件**:
  - `plugins/reply_monitor.py` — DiscuzReplyExtractor 采集引擎(使用 HumanSession)
  - `routes/comment_monitor.py` — 收件箱 UI + API 端点 + 定时调度
- **数据表**: `comment_replies` (回复记录) + `comment_monitor_config` (监控配置)
- **能力**:
  - 多论坛统一管理 (mydigit/amobbs/csdn 等)
  - 新回复识别去重
  - 定时分段检查 (早/中/晚 三个时间段)
  - AI 自动回帖
  - 账号配置绑定
- **API 端点**:
  - `GET /comment-monitor` — 监控页面
  - `GET /api/comment-monitor/replies` — 回复列表
  - `GET /api/comment-monitor/accounts` — 支持监控的账号
  - `POST /api/comment-monitor/run/<account_id>` — 手动运行检查
  - `POST /api/comment-monitor/reply/<reply_id>` — AI 自动回复
  - `PUT /api/comment-monitor/config/<account_id>` — 更新监控配置

### 3.18 登录状态检测 (`core/status_detector.py` + `core/status_cache.py`)

- **三层检测架构**:
  | 层级 | 方法 | 开销 | 说明 |
  |------|------|------|------|
  | 第一层 | API 轻量检测 | 毫秒级 | 用 Cookie 调平台 API/页面提取用户信息 |
  | 第二层 | Playwright 快速检测 | 秒级 | 打开个人主页，单页面加载 |
  | 第三层 | 全量 Playwright | 数秒 | 完整打开网站，注入 Cookie 模拟登录 |
- **检测结果结构**: logged_in/username/display_name/points/level/avatar_url/method/status/success
- **缓存系统**: 内存缓存(5分钟 TTL) + SQLite `status_cache.db` 持久化
- **缓存键**: `status:{account_id}`
- **支持平台**: Discuz!/CSDN/OSHWHub 等通过 `_detect_*` 函数实现

### 3.19 编译规则与渲染 (`core/compile_rule.py` + `core/renderers.py` + `core/compiled_cache.py`)

- **编译规则** (`compile_rule.py`):
  - `ImageRule` — 图片限制(max_width/max_height/max_size_mb/upload_method/auto_compress)
  - `BodyFormat` — 正文格式(markdown/bbcode/html/richtext + allow_html/code_block/table)
  - BBCode 特有设置(bbcode_max_font_size)
  - 内置各平台预设规则实例
- **渲染器** (`renderers.py`):
  - BBCode→HTML (Discuz!)
  - Markdown→HTML (CSDN/掘金/OSHWHub/GitHub Pages)
  - HTML 直接展示 (WordPress)
  - Richtext→HTML (知乎/B站)
  - 纯文本包装 (Twitter)
- **编译缓存** (`compiled_cache.py`):
  - 表 `compiled_cache`: article_id/platform/title/body/rendered_html/warnings/source_hash
  - 通过 source_hash 检测是否需要重新编译
  - 支持多平台缓存共享

### 3.20 AI逛论坛 (`plugins/forum_reader.py`)

- **功能说明**: 自动登录配置的论坛账号，抓取新帖子，AI 筛选推荐
- **DiscuzForumReader**: 读取 Discuz! 论坛帖子列表和详情
- **使用 HumanSession** 人机浏览器模拟，避免反爬
- **能力**: 登录检测 / 帖子列表 / 帖子详情 / 新帖识别

### 3.21 登录器插件 (`plugins/xianyu_login.py` + `plugins/amobbs_login.py`)

- **闲鱼登录器** (`xianyu_login.py`):
  - Playwright 打开 goofish.com → 跳转淘宝 SSO → 填入账号密码
  - 处理验证码/扫码(滑块验证/二维码/短信验证)
  - 频率控制: 单账号不超过 3次/分钟
  - 支持截图返回前端交互
- **阿莫论坛登录器** (`amobbs_login.py`):
  - "我不是机器人" 点击式复选框验证码处理
  - ✓ → 提交登录 → 保存 Cookie
  - ✗ → 重试
  - 验证码图片以 base64 返回给前端

---

## 四、工作流说明

### 4.1 账号添加工作流
```
选择平台 → 弹窗 → 选择登录方式(密码/QR/Cookie) → 
QR扫码/密码验证 → Playwright 浏览器自动登录 → 
Cookie 自动捕获 → 配置加密 → 保存到 platform_accounts
```

### 4.2 文章发布工作流
```
采集(论坛/手动/AI/Provider) → 编译(MD→IR→平台格式) → 
预览(HTML渲染) → 存草稿 → 发布(调用 Publisher.publish()) → 
记录到 publish_log → 通知推送
```

### 4.3 签到工作流
```
调度器每分钟检查 → 获取启用的签到配置 → 
forum_signin 动态导入 signin_*.py 插件 →
检查今日签到窗口 → 检测是否已签到 → 
匹配 SigninBase 插件 → Playwright 执行签到 → 
记录到 signin_log → 通知结果
```

### 4.4 通知推送工作流
```
系统事件(发布/签到/价格变化) → notify() → 
写入 notifications 表 → Gateway.dispatch() → 
各 Provider.send() → 终端(飞书/企微/微信/Webhook)
```

### 4.5 审批工作流
```
AI 发起敏感操作 → create_approval() → 
通知网关推送审批请求 → 管理员回复 → 
process_approval() → 执行/拒绝操作
```

### 4.6 论坛探索工作流
```
定时脚本/手动触发 → 读取 forum_exploration 表 → 
检查 explore_cooldown(每小时限流) → 
Playwright 访问论坛 → 爬取版块列表 → 
对比差异(内容哈希) → 更新 forum_exploration 表
```

### 4.7 工作台流水线工作流
```
用户选择 Provider + 内容类型 → 工作台列出内容项 →
选择内容 → 采集(Collect) → 编译(Compile) → 
预览(Preview) → 存草稿(Draft) → 发布(Publish) →
记录运行历史 + 通知结果
```

### 4.8 评论监控工作流
```
定时调度/手动触发 → 读取 comment_monitor_config →
遍历账号 → DiscuzReplyExtractor 采集回复 → 
去重(对比 comment_replies) → 新回复标记 is_new=1 →
用户查看 → AI 生成回帖(可选) → 自动回复
```

### 4.9 登录状态检测工作流
```
页面请求 /api/accounts/<id>/status → status_cache 检查缓存 →
缓存命中(5min内) → 返回缓存数据
缓存未命中 → 第一层 API 轻量检测 → 成功→写缓存→返回
失败 → 第二层 Playwright 快速检测 → 成功→写缓存→返回
失败 → 第三层 Playwright 全量检测 → 写缓存→返回
```

---

## 五、数据流

### 5.1 账号数据流
```
用户输入 → Flask 表单 → routes/accounts.py → 
encrypt_config() 加密敏感字段 → 
写入 platform_accounts.config_json (SQLite) → 
读取时 decrypt_config() 解密 → 脱敏展示
```

### 5.2 发布数据流
```
routes/posts.py → core/publisher.py → 
查找对应平台 Publisher → decrypt_config() → 
Publisher.publish(Article) → process_images() → 
平台 HTTP/Playwright API → 记录 publish_log → 
notify() 通知结果
```

### 5.3 通知数据流
```
core/notifier.notify() → INSERT INTO notifications → 
Gateway.dispatch() → 遍历已启用 channels → 
Provider.send() → 终端平台 API → 
记录发送日志
```

### 5.4 探索数据流
```
scripts/hourly_forum_check.py / core/explorer.py → 
playwright 访问论坛 → 解析版块 HTML → 
对比 DB 已有数据 → INSERT/UPDATE forum_exploration
```

### 5.5 工作台流水线数据流
```
routes/workspace_ui.py → Provider.get_item_content() → 
Pipeline.create() → set_handler(collect/compile/preview/draft/publish) → 
Pipeline.run_stage() 逐阶段 → ContentObject 传递 →
发布时通过 get_publisher() 查找 Publisher → publish()
```

### 5.6 评论监控数据流
```
routes/comment_monitor.py → plugins/reply_monitor.py (DiscuzReplyExtractor) →
HumanSession 浏览器模拟 → 采集帖子回复 HTML → 
解析/去重/插入 comment_replies → 
用户查看 → AI 生成回帖 → 自动发布回复
```

### 5.7 登录状态检测数据流
```
routes/accounts.py → core/status_cache.py (内存+SQLite) →
缓存未命中 → core/status_detector.py (三层降级) →
返回检测结果 → 缓存写入(5min TTL)
```

---

## 六、API 接口文档

### 6.1 账号管理 API
| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/accounts` | GET | 账号管理页面 | login_required |
| `/accounts/add` | POST | 新增/更新账号 | login_required |
| `/accounts/edit/<id>` | GET/POST | 编辑账号(重定向) | login_required |
| `/accounts/delete/<id>` | GET | 删除账号 | login_required |
| `/api/accounts/config/<id>` | GET | 获取脱敏配置 | login_required |
| `/api/accounts/<id>/toggle` | POST | 切换启用/禁用 | login_required |
| `/api/accounts/<id>/status` | GET | 三层登录状态检测 | login_required |

### 6.2 登录 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/generic/login/start` | POST | 启动通用 Playwright 登录 |
| `/api/generic/login/captcha` | POST | 提交验证码 |
| `/api/generic/login/status` | GET | 登录状态查询 |
| `/api/amobbs/login/start` | POST | 阿莫论坛登录启动 |
| `/api/amobbs/login/captcha/click` | POST | 阿莫验证码点击 |
| `/api/amobbs/login/captcha/solve` | POST | 阿莫验证码求解 |
| `/api/amobbs/login/submit` | POST | 阿莫登录提交 |

### 6.3 网关 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/gateway` | GET | 网关配置页面 |
| `/api/gateway/channels` | GET | 渠道列表 |
| `/api/gateway/channels` | POST | 添加渠道 |
| `/api/gateway/channels/<id>` | PUT | 更新渠道 |
| `/api/gateway/channels/<id>` | DELETE | 删除渠道 |
| `/api/gateway/channels/<id>/test` | POST | 测试发送 |

### 6.4 签到 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/signin` | GET | 签到页面 |
| `/api/signin/run/<account_id>` | POST | 手动签到 |
| `/api/signin/run_all` | POST | 全部签到 |
| `/api/signin/schedule` | POST | 设置签到时间 |
| `/api/signin/status` | GET | 调度器状态 |
| `/api/signin/stats` | GET | 签到统计 |

### 6.5 AI API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ai/providers` | GET | 列出所有 Provider |
| `/api/ai/config` | GET | AI 路由配置 |
| `/api/ai/config` | POST | 更新配置 |
| `/api/ai/generate` | POST | AI 生成 |
| `/api/ai/balances` | GET | 余额查询 |
| `/api/ai/logs` | GET | AI调用日志分页 |
| `/api/ai/logs/clear` | POST | 清空AI调用日志 |

### 6.6 探索 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/exploration` | GET | 探索数据页面 |
| `/api/exploration/platforms` | GET | 平台列表 |
| `/api/exploration/platform/<domain>` | GET | 平台详情 |
| `/api/exploration/explore` | POST | 启动探索 |
| `/api/exploration/tags` | POST | 更新关心标签 |
| `/api/exploration/section/<sid>` | GET | 板块详情 |

### 6.7 价格监控 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/price-monitor` | GET | 监控页面 |
| `/api/price-monitor/accounts` | GET | 支持监控的平台账号 |
| `/api/price-monitor/add` | POST | 添加监控 |
| `/api/price-monitor/<id>` | DELETE | 删除监控 |
| `/api/price-monitor/<id>/refresh` | POST | 刷新价格 |

### 6.8 审批 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/approval` | GET | 审批页面 |
| `/api/approval/pending` | GET | 待审批列表 |
| `/api/approval/history` | GET | 审批历史 |
| `/api/approval/<id>/respond` | POST | 通过/拒绝 |

### 6.9 工作台 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/workspace` | GET | 工作台主页 |
| `/pipeline` | GET | 重定向到 `/workspace` |
| `/api/workspace/providers` | GET | 列出所有 Provider |
| `/api/workspace/provider/<name>/items` | GET | Provider 内容列表 |
| `/api/workspace/provider/<name>/item/<item_id>` | GET | 内容详情 |
| `/api/workspace/run` | POST | 执行流水线 |
| `/api/workspace/history` | GET | 运行历史 |
| `/api/workspace/logs/publish` | GET | 发布记录 |
| `/api/workspace/logs/collect` | GET | 采集记录 |

### 6.10 评论监控 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/comment-monitor` | GET | 评论监控页面 |
| `/api/comment-monitor/replies` | GET | 回复列表(支持分页/筛选/时间范围) |
| `/api/comment-monitor/accounts` | GET | 支持监控的账号列表 |
| `/api/comment-monitor/run/<account_id>` | POST | 手动运行检查 |
| `/api/comment-monitor/reply/<reply_id>` | POST | AI 自动回复 |
| `/api/comment-monitor/config/<account_id>` | PUT | 更新监控配置 |
| `/api/comment-monitor/reply/regen/<reply_id>` | POST | 重新生成回复 |
| `/api/comment-monitor/reply/<reply_id>/mark-read` | PUT | 标记已读 |

### 6.11 Gateway API v2 (外部接口)
| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/api/v2/system/status` | GET | 系统状态 | 无需 |
| `/api/v2/system/restart` | POST | 重启服务 | login_required |
| `/api/v2/system/reload` | POST | 重载配置 | login_required |

### 6.12 其他 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/xianyu/search` | POST | 闲鱼商品搜索 |
| `/api/platforms/presets` | GET | 平台预设配置 |

---

## 七、数据库结构

### 7.1 `users`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 用户 ID |
| username | TEXT | 用户名 |
| password_hash | TEXT | bcrypt 密码哈希 |
| email | TEXT | 邮箱 |
| phone | TEXT | 手机号 |
| is_admin | INTEGER | 是否管理员 |
| api_key | TEXT | API 密钥 |
| twofa_type | TEXT | 二步验证类型 |
| last_login | TEXT | 最后登录时间 |
| created_at | TEXT | 创建时间 |

### 7.2 `platform_accounts`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 账号 ID |
| user_id | INTEGER FK | 所属用户 |
| platform | TEXT | 平台标识 (discuz/csdn/zhihu/...) |
| account_name | TEXT | 账号别名 |
| config_json | TEXT | 加密后的 JSON 配置 |
| is_active | INTEGER | 是否启用 (0/1) |
| price_capable | INTEGER | 是否支持价格监控 |
| sort_order | INTEGER | 排序权重 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### 7.3 `articles`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 文章 ID |
| user_id | INTEGER FK | 所属用户 |
| title | TEXT | 标题 |
| content | TEXT | Markdown 正文 |
| summary | TEXT | 摘要 |
| tags | TEXT | JSON 标签数组 |
| cover | TEXT | 封面图片路径 |
| status | TEXT | draft/published/archived |
| source | TEXT | 来源平台 |
| source_url | TEXT | 原文链接 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### 7.4 `publish_log`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 日志 ID |
| article_id | INTEGER FK | 文章 ID |
| account_id | INTEGER FK | 目标账号 ID |
| platform | TEXT | 平台 |
| success | INTEGER | 是否成功 |
| url | TEXT | 发布链接 |
| message | TEXT | 响应消息 |
| status | TEXT | pending/success/failed/draft |
| deploy_status | TEXT | 部署状态 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### 7.5 `signin_log`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 日志 ID |
| account_id | INTEGER FK | 账号 ID |
| account_name | TEXT | 账号名 |
| platform | TEXT | 平台 |
| success | INTEGER | 是否成功 (0/1) |
| already_signed | INTEGER | 今日是否已签到 |
| message | TEXT | 响应消息 |
| points_earned | INTEGER | 获得积分 |
| created_at | TEXT | 时间 |

### 7.6 `gateway_channels`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 渠道 ID |
| user_id | INTEGER FK | 所属用户 |
| name | TEXT | 渠道名称 |
| platform | TEXT | 平台 (webhook/feishu/wecom/wechat) |
| config_json | TEXT | 配置 JSON |
| enabled | INTEGER | 是否启用 |
| created_at | TEXT | 创建时间 |

### 7.7 `forum_exploration`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 记录 ID |
| platform | TEXT | 平台标识 |
| platform_domain | TEXT | 域名 |
| section_id | TEXT | 版块 ID |
| section_name | TEXT | 版块名称 |
| can_post | INTEGER | 可发帖 |
| keywords | TEXT | JSON 关键词数组 |
| extra_info | TEXT | 额外信息 JSON |
| last_checked | TEXT | 最后检查时间 |
| hash | TEXT | 内容哈希(变更检测) |
| created_at | TEXT | 创建时间 |

### 7.8 `explore_cooldown`
| 字段 | 类型 | 说明 |
|------|------|------|
| domain | TEXT PK | 域名 |
| last_explore_at | REAL | 最后探索时间戳 |
| updated_at | TEXT | 更新时间 |

### 7.9 `price_monitors`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 监控 ID |
| user_id | INTEGER FK | 所属用户 |
| account_id | INTEGER | 关联账号 |
| name | TEXT | 元件名称 |
| lcsc_code | TEXT | LCSC 料号 |
| datasheet_url | TEXT | 数据手册链接 |
| min_price | REAL | 最低价(报警阈值) |
| max_price | REAL | 最高价(报警阈值) |
| enabled | INTEGER | 是否启用 |
| created_at | TEXT | 创建时间 |

### 7.10 `price_history`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 记录 ID |
| monitor_id | INTEGER FK | 监控 ID |
| price_min | REAL | 最低价 |
| price_max | REAL | 最高价 |
| stock | INTEGER | 库存 |
| fetched_at | TEXT | 获取时间 |

### 7.11 `approval_requests`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 请求 ID |
| title | TEXT | 审批标题 |
| description | TEXT | 审批描述 |
| action | TEXT | 操作类型 (publish/delete/modify/custom) |
| target_platform | TEXT | 目标平台 |
| target_url | TEXT | 目标链接 |
| requested_by | TEXT | 请求来源 |
| status | TEXT | pending/approved/rejected/expired/cancelled |
| metadata | TEXT | JSON 额外数据 |
| response_note | TEXT | 管理员备注 |
| created_at | TEXT | 创建时间 |
| responded_at | TEXT | 回复时间 |

### 7.12 `notifications`
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER | 用户ID |
| title | TEXT | 标题 |
| message | TEXT | 内容 |
| level | TEXT | 级别 (info/warning/error) |
| source | TEXT | 来源 |
| read | INTEGER | 是否已读 0/1 |
| created_at | TEXT | 创建时间 |

### 7.13 `ai_call_log`
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER PK | 自增主键 |
| capability | TEXT | 能力类型 (writing/translate/image_gen等) |
| provider | TEXT | AI Provider 名称 (deepseek/openai等) |
| model | TEXT | 使用的模型名 |
| prompt_tokens | INTEGER | 输入token数 |
| response_tokens | INTEGER | 输出token数 |
| cost | REAL | 费用（元） |
| success | INTEGER | 是否成功 0/1 |
| error | TEXT | 错误信息 |
| response_summary | TEXT | 响应摘要（前200字） |
| prompt_preview | TEXT | 提示词预览（前200字） |
| created_at | TEXT | 创建时间 |

### 7.14 `deployer_configs`
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER | 用户ID |
| deployer_name | TEXT | 部署器类型 (github_pages等) |
| display_name | TEXT | 显示名称 |
| config_json | TEXT | JSON配置 |
| is_active | INTEGER | 是否启用 0/1 |
| created_at | TEXT | 创建时间 |

### 7.15 `comment_replies`
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER PK | 自增主键 |
| article_id | INTEGER FK | 文章ID |
| account_id | INTEGER FK | 账号ID |
| platform | TEXT | 平台 |
| forum_name | TEXT | 论坛名 |
| thread_tid | TEXT | 帖子TID |
| thread_title | TEXT | 帖子标题 |
| thread_url | TEXT | 帖子链接 |
| reply_author | TEXT | 回复作者 |
| reply_content | TEXT | 回复内容 |
| reply_time | TEXT | 回复时间 |
| reply_pid | TEXT | 回复PID |
| is_new | INTEGER | 是否新回复 |
| is_read | INTEGER | 是否已读 |
| is_auto_replied | INTEGER | 是否已自动回复 |
| source | TEXT | 来源(auto/manual) |
| created_at | TEXT | 创建时间 |

### 7.16 `comment_monitor_config`
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER PK | |
| account_id | INTEGER FK UNIQUE | 账号ID |
| enabled | INTEGER | 是否启用 |
| slot_morning | TEXT | 早间时段 |
| slot_afternoon | TEXT | 下午时段 |
| slot_evening | TEXT | 晚间时段 |
| auto_reply | INTEGER | 是否自动回复 |

### 其他表
- `provider_config` — Provider 全局配置
- `ai_configs` — AI 供应商配置/模型
- `route_rules` — SDK 路由规则
- `user_sessions` — 用户会话
- `compiled_cache` — 编译产物缓存(article_id/platform/title/body/rendered_html/source_hash)

---

## 八、配置说明

### 8.1 环境变量
| 变量 | 说明 |
|------|------|
| `FS_ENCRYPTION_KEY` | 覆盖 .fs_key 加密密钥 |
| `FS_SECRET_KEY` | Flask session secret |
| `FLASHSLOTH_SECRET` | Flask app secret key |
| `FS_BOOT_USERNAME` | 首次启动默认用户名 |
| `FS_BOOT_PASSWORD` | 首次启动默认密码 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `OPENAI_API_KEY` | OpenAI API 密钥 |

### 8.2 密钥文件
- `~/.hermes/flashsloth/.fs_key` — Fernet 加密密钥（权限 600，自动生成）
- `flashsloth.db` — SQLite 主数据库
- `status_cache.db` — 状态缓存数据库

### 8.3 平台配置文件
| 文件 | 说明 |
|------|------|
| `config/platform_csdn.json` | CSDN 平台预设 |
| `config/platform_mydigit.json` | 数码之家预设 |
| `config/platform_amobbs.json` | 阿莫论坛预设 |
| `config/ai_capabilities.json` | AI 供应商能力配置 |
| `core/platform_presets.json` | 全局平台预设 |
| `core/provider_registry.json` | AI 供应商注册表预设 |

### 8.4 反检测配置（环境变量可覆盖）
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AD_MOUSE_MIN` | 3 | 鼠标最小移动像素 |
| `AD_MOUSE_MAX` | 50 | 鼠标最大移动像素 |
| `AD_MOUSE_DELAY_MIN` | 30ms | 鼠标移动最小间隔 |
| `AD_MOUSE_DELAY_MAX` | 120ms | 鼠标移动最大间隔 |
| `AD_TYPE_DELAY_MIN` | 50ms | 打字最小间隔 |
| `AD_TYPE_DELAY_MAX` | 200ms | 打字最大间隔 |
| `AD_OP_WAIT_MIN` | 1.5s | 操作最小等待 |
| `AD_OP_WAIT_MAX` | 4.0s | 操作最大等待 |
| `AD_SCROLL_MIN` | 100px | 滚动最小距离 |
| `AD_SCROLL_MAX` | 600px | 滚动最大距离 |

---

## 九、定时任务

| 任务 | 脚本/模块 | 频率 | 说明 |
|------|-----------|------|------|
| 论坛探索 | `scripts/hourly_forum_check.py` | 每小时 | 增量检查 Discuz 论坛版块变更 |
| 自动签到 | `core/scheduler.py` | 每分钟检查 | 在签到窗口内执行签到(forum_signin调度) |
| 价格刷新 | `core/price_monitor.py` | 手动触发 | LCSC 价格更新 |
| 评论监控 | `routes/comment_monitor.py` 定时器 | 按配置时段 | 检查帖子新回复+AI自动回帖 |

**注意**: 签到调度器为守护线程（`fs-scheduler`），随 Flask 应用启动。探索任务通过外部 cron 触发。评论监控检查在应用内按配置时间段定时运行。

---

## 十、开发铁律

1. **所有存在操作必须使用 Playwright** — 禁止 requests/curl/wget/httpx 登录或发布
2. **凭证加密** — 所有敏感字段（password/cookie/token/api_key）必须经过 `encrypt_config()` 加密存储
3. **配置脱敏** — 页面显示敏感字段为 `••••••••`，只读 API 返回脱敏值
4. **反检测统一** — 所有 Playwright 交互必须使用 `core/anti_detect.py` 的人类行为模拟
5. **探索限流** — 每域名每小时最多探索一次（`explore_cooldown` 表持久化）
6. **通知静默** — 网关不可用时静默跳过，不阻塞主流程
7. **审批先过** — AI 发起的敏感操作必须先过审批流程
8. **Publisher 注册制** — 新平台发布器必须 `@register` + 继承 `Publisher` 基类
9. **签到 Plugin 注册制** — 新签到插件必须 `@register` + 继承 `SigninBase`
10. **变更检测** — 论坛探索使用内容哈希检测版块变更，避免暴力覆盖
11. **兼容性优先** — 新增功能不破坏现有 URL 路由和数据表结构
12. **登录状态三层检测** — 优先使用 API 轻量检测(无浏览器)，失败降级到 Playwright
13. **状态缓存** — 登录状态使用 status_cache 内存+SQLite 缓存(5min TTL)，避免高频检测
14. **工作台流水线可配置** — Pipeline 支持按需设置处理阶段，非全部阶段必须注册

---

## 十一、版本历史

| 版本 | 日期 | 主要改动 |
|------|------|----------|
| v4.56 | 2026-07-07 | 常驻Playwright浏览器引擎(core/browser_engine.py+路由)、外部服务集成(routes/external_services.py)、闲鱼PlatformAdapter Playwright版(sdk/adapters/xianyu.py)、Playwright子进程验证脚本(scripts/playwright_verify.py)。文件统计已更新(core:30, routes:24, sdk/adapters:16, scripts:5) |
| v4.55 | 2026-07-07 | 新增15个文件到开发说明书：状态检测器/缓存/版块注册中心/编译缓存/渲染器/编译规则/AI供应商注册表/签到基类/Provider基类/论坛签到调度/论坛读取器/评论监控/闲鱼登录器/阿莫登录器/AList存储/闲鱼商品发布框架/SDK脚手架/4个论坛脚本/工作台API/评论监控API/应用工厂 |
| v4.54 | 2026-07-07 | AI调用日志系统(ai_call_log表+自动记录+/ai/logs页面)，全站移动端CSS增强(768px+480px双断点)，publish_log updated_at列修复 |
| v4.53 | 2026-07-07 | 手机验证码登录(phone_login+SMS验证码+前端支持)，OSHWHub登录修复(passport.jlc.com) |
| v4.52 | 2026-07-07 | 统一登录能力探索+动态渲染(7平台登录方式JSON+API+前端动态Tab) |
| v4.51 | 2026-07-07 | 签到asyncio修复+探索数据DB持久化，编辑页密码掩码覆盖bug修复 |
| v4.50 | 2026-07-07 | 闲鱼V2 MTOP发布器，审批系统上线，通知网关扩展至22Provider |
| v4.39 | — | 通知网关 22 Provider、反检测中央模块、闲鱼 V2 MTOP 发布器、闲鱼客户端 SDK |
| v4.0  | — | Gateway API 网关、统一流水线调度器、AI 路由框架 |
| v3.x  | — | Discuz/CSDN/知乎/掘金/B站/OSHWHub 发布器、签到系统 |
| v2.x  | — | 基础账号管理、文章 CRUD、多平台发布 |
| v1.0  | — | 初始化 Flask 应用、单平台发布 |

---

## 附录：文件完整清单

### core/ (30 个 Python 文件)
| 文件 | 说明 |
|------|------|
| `__init__.py` | 空包标记 |
| `ai_provider.py` | AI Provider 统一框架 + 路由 + 日志 |
| `anti_detect.py` | Playwright 反检测/人类行为模拟 |
| `approval.py` | 审批流程系统 |
| `article.py` | 文章数据模型 |
| `browser_engine.py` | 常驻 Playwright 浏览器引擎(全局单例) |
| `captcha_handler.py` | 验证码处理器 |
| `compile_rule.py` | 每平台编译规则定义(图片/正文/BBCode) |
| `compiled_cache.py` | 编译产物数据库缓存 |
| `compiler.py` | 文章编译器 (MD→IR→输出) |
| `config.py` | 全局配置加载 |
| `credential_crypto.py` | Fernet AES-128-CBC 凭证加密 |
| `database.py` | 数据库初始化 + 连接 + 种子数据 |
| `deployer.py` | 部署器基类 |
| `explorer.py` | Playwright 论坛探索引擎 |
| `forum_registry.py` | 统一智能版块匹配系统 |
| `gateway.py` | 通知网关核心（Provider 注册表） |
| `image_pipeline.py` | 图片处理流水线 |
| `notifier.py` | 统一通知系统 |
| `pipeline.py` | 内容流水线调度器(5阶段) |
| `platform_presets.json` | 全局平台预设 |
| `price_monitor.py` | LCSC 元器件价格监控 |
| `provider.py` | Provider 统一内容来源基类 + 注册机制 |
| `provider_registry.json` | AI 供应商注册表预设 |
| `provider_registry.py` | 动态AI供应商注册表加载 |
| `publisher.py` | Publisher 基类 + 注册机制 |
| `renderers.py` | 各平台编译产物渲染器(预览HTML) |
| `scheduler.py` | 签到调度器（守护线程定时签到） |
| `signin.py` | SigninBase 签到基类 + 注册机制 |
| `status_cache.py` | 账号状态缓存系统(内存+SQLite) |
| `status_detector.py` | 三层登录状态检测器 |
| `storage.py` | 存储抽象层 (LocalStorage, AlistStorage) |

### routes/ (24个 Python 文件)
参见系统架构图中 routes/ 层完整清单。

### plugins/ (30+ 个 Python 文件)
参见各模块说明中的发布器/签到/登录/Provider/工具插件清单。

### sdk/adapters/ (16个 Python 文件)
参见 SDK 平台适配器层清单。

### templates/ (30个 HTML 模板)
| 模板 | 说明 |
|------|------|
| `index.html` | 仪表盘 |
| `login.html` | 登录页 |
| `register.html` | 注册页 |
| `accounts.html` | 账号管理 |
| `account_edit.html` | 账号编辑弹窗 |
| `signin.html` | 签到管理 |
| `gateway.html` | 通知网关 |
| `exploration.html` | 论坛探索 |
| `approval.html` | 审批管理 |
| `price_monitor.html` | 价格监控 |
| `ai_settings.html` | AI 设置 |
| `ai_logs.html` | AI 调用日志 |
| `publish_manage.html` | 发布管理 |
| `publish_select.html` | 发布目标选择 |
| `compile_preview.html` | 编译预览 |
| `preview.html` | 文章预览 |
| `edit.html` | 文章编辑 |
| `forum_reader.html` | 论坛阅读器 |
| `xianyu_search.html` | 闲鱼搜索 |
| `notifications.html` | 通知列表 |
| `pipeline.html` | 内容流水线 |
| `workspace.html` | 工作台 |
| `settings.html` | 设置 |
| `storage_settings.html` | 存储设置 |
| `deployers.html` | 部署器配置 |
| `change_password.html` | 修改密码 |
| `forgot_password.html` | 忘记密码 |
| `verify_2fa.html` | 二步验证 |
| `comment_monitor.html` | 评论监控 |
| `base.html` | 基础布局模板 |

### scripts/ (5个 Python 脚本)
| 脚本 | 说明 |
|------|------|
| `hourly_forum_check.py` | 每小时增量检查论坛版块变更 |
| `sync_registry_keywords.py` | 同步 forum_registry 关键词到 DB |
| `consolidate_forum_data.py` | 合并 www 前缀数据到非 www 域名 |
| `playwright_verify.py` | 子进程 Playwright 账号登录验证 |
| `compare_forum_data.py` | 对比新旧论坛数据差异 |

---

*本文档由 AI 自动维护，每小时增量更新。代码是实际运行状态 — 当聊天记录与代码冲突时以代码为准。*
