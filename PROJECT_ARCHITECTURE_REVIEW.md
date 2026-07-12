# FlashSloth — 完整软件架构审查报告

> 生成日期: 2026-07-07
> 扫描范围: `routes/` (24 个文件) + `core/` (29 个文件)
> 数据库: `flashsloth.db` (单文件 SQLite, WAL 模式)

---

## 目录

1. [项目概览](#1-项目概览)
2. [路由结构全景](#2-路由结构全景)
3. [路由模块详解](#3-路由模块详解)
4. [核心模块架构](#4-核心模块架构)
5. [抽象类 / 注册制模式总览](#5-抽象类--注册制模式总览)
6. [数据库表结构](#6-数据库表结构)
7. [模块依赖关系图](#7-模块依赖关系图)
8. [数据流架构](#8-数据流架构)
9. [架构评估与改进建议](#9-架构评估与改进建议)

---

## 1. 项目概览

**FlashSloth** 是一个统一的多平台内容发布与管理平台，核心定位为「个人数字资产中心 (Personal Asset Hub)」。它整合了：

- **内容采集**: 从 Markdown 文件、Notion 数据库等来源导入内容
- **内容编译**: 将统一的 Markdown 源文编译为各平台格式 (BBCode/HTML/纯文本)
- **多平台发布**: 发布到 Discuz 论坛、CSDN、OSHWHub、WordPress 等平台
- **账号管理**: 管理各平台 Cookie/密码凭证（Fernet AES-128 加密存储）
- **状态检测**: 三层降级检测账号登录状态 (API 轻量 → Playwright 快速 → Playwright 全量)
- **定时签到**: 多插件签到系统，支持随机化时间偏移
- **评论监控**: 论坛帖子回复监控 + AI 自动回复
- **通知网关**: 多终端消息推送 (飞书/企微/微信/Telegram/Discord/Slack/钉钉/WhatsApp)
- **审批流程**: 敏感操作审批 (通过网关回复 "通过 N" / "拒绝 N")
- **探索引擎**: Playwright 驱动的论坛版块自动探索与持久化
- **部署器**: 静态站点部署 (GitHub Pages 等)
- **存储后端**: 本地文件系统 + AList 远程存储
- **AI 能力**: 多供应商路由 (DeepSeek/OpenAI/自定义)，内容生成/余额查询
- **价格监控**: LCSC 商城元器件价格跟踪
- **闲鱼搜索**: 闲鱼商品搜索与详情获取
- **API**: RESTful API v1 + v2，支持 API Key + Session 双鉴权

### 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | Flask + Jinja2 |
| 认证 | flask-login + API Key (SHA256) |
| 数据库 | SQLite3 (WAL 模式) |
| 浏览器自动化 | Playwright (sync_api) |
| 浏览器引擎 | 常驻单例 BrowserEngine (10 分钟自动关闭) |
| 数据模型 | dataclass + ABC |
| 模板引擎 | Jinja2 (关闭热重载) |
| 加密 | cryptography.fernet (AES-128-CBC + HMAC-SHA256) |
| 容器服务 | s6-overlay (外部) |

---

## 2. 路由结构全景

### 2.1 路由注册方式

所有路由模块在 `routes/__init__.py` 的 `configure_app()` 中显式导入，触发 `@app.route` 装饰器注册。不使用 Flask Blueprint（避免 url_for 命名空间问题），共享同一个 `_app.py` 中的全局 `app` 实例。

### 2.2 完整路由列表

#### 页面路由 (返回 HTML)

| 路由 | 模块 | 说明 |
|------|------|------|
| `/` | `auth.py` | 首页仪表盘 |
| `/login` | `auth.py` | 登录页 |
| `/register` | `auth.py` | 注册页 |
| `/change_password` | `auth.py` | 改密页 |
| `/forgot_password` | `auth.py` | 找回密码 |
| `/logout` | `auth.py` | 登出 |
| `/settings` | `auth.py` | 设置页 |
| `/accounts` | `accounts.py` | 账号管理页 |
| `/workspace` | `workspace_ui.py` | 工作台 |
| `/pipeline` | `workspace_ui.py` | → 重定向至 /workspace |
| `/exploration` | `exploration.py` | 论坛探索数据管理页 |
| `/forum-reader` | `forum.py` | AI 逛论坛页 |
| `/post/new` | `posts.py` | 新建文章 |
| `/post/edit/<pid>` | `posts.py` | 编辑文章 |
| `/compile/<pid>` | `posts.py` | 编译预览页 |
| `/signin` | `signin.py` | 签到管理页 |
| `/storage/settings` | `storage_deploy.py` | 存储设置页 |
| `/deployers` | `storage_deploy.py` | 部署配置管理页 |
| `/gateway` | `gateway.py` | 通知网关配置页 |
| `/approval` | `approval.py` | 审批管理页 |
| `/notifications` | `notifications.py` | 通知中心页 |
| `/price-monitor` | `price_monitor.py` | 价格监控页 |
| `/comment-monitor` | `comment_monitor.py` | 评论监控页 |
| `/xianyu/search` | `xianyu_search.py` | 闲鱼搜索页 |
| `/ai/settings` | `ai.py` | AI 配置页 |
| `/playwright-settings` | `browser_engine.py` | 浏览器引擎配置页 |
| `/verify-2fa` | `auth.py` | 双因素验证页 |

#### API 路由

| 路由前缀 | 模块 | 说明 |
|----------|------|------|
| `/api/accounts/*` | `accounts.py` | 账号 CRUD + 状态检测 + 批量操作 |
| `/api/workspace/*` | `workspace_ui.py` | Provider 配置 + 流水线执行 |
| `/api/exploration/*` | `exploration.py` | 探索数据管理 + 自定义探索 |
| `/api/forum-reader/*` | `forum.py` | 论坛浏览/推荐/回复 |
| `/api/signin/*` | `signin.py` | 签到执行/配置/批量 |
| `/api/discuz/*` | `captcha_browser.py` | Discuz 验证码获取/登录 |
| `/api/captcha/*` | `captcha_browser.py` | 验证码状态/启动/提交/自动识别 |
| `/api/ai/*` | `ai.py` | AI Provider CRUD + 生成/测试/配置 |
| `/api/browser/*` | `browser_engine.py` | 浏览器引擎启动/停止/重启/状态 |
| `/api/amobbs/login/*` | `browser_login.py` | Amobbs Playwright 登录 |
| `/api/xianyu/login/*` | `browser_login.py` | 闲鱼 Playwright 登录 |
| `/api/oshwhub/login/*` | `browser_login.py` | OSHWHub Playwright 登录 |
| `/api/storage/*` | `storage_deploy.py` | 存储配置/上传/文件管理 |
| `/api/deploy/*` | `storage_deploy.py` | 部署执行/站点配置 |
| `/api/gateway/*` | `gateway.py` | 通知渠道 CRUD + 测试 |
| `/api/notifications/*` | `notifications.py` | 通知列表/已读 |
| `/api/approval/*` | `approval.py` | 审批 CRUD + webhook |
| `/api/price-monitor/*` | `price_monitor.py` | 价格监控 CRUD + 刷新 |
| `/api/comment-monitor/*` | `comment_monitor.py` | 评论检查/回复/AI 生成 |
| `/api/xianyu/*` | `xianyu_search.py` | 闲鱼搜索 + 商品详情 |
| `/api/platforms/presets` | `platforms.py` | 平台预设 |
| `/api/v1/*` | `api_v1.py` | 统一 API v1 (API Key) |
| `/api/v2/*` | `api_v2.py` | Gateway API v2 |
| `/api/external-services` | `external_services.py` | 外部服务注册表 |

---

## 3. 路由模块详解

### 3.1 `auth.py` — 认证与首页

- **功能**: 登录/注册/改密/短信验证码/2FA/首页仪表盘
- **依赖**: `core/database`, `core/publisher`, `core/deployer`, `core/config`, `core/storage`, `core/captcha_handler`, `core/ai_provider`
- **关键数据流**: 首页查询 `articles` + `publish_log` + `platform_accounts` + `provider_config` + `deployer_configs`

### 3.2 `accounts.py` — 账号管理 (1565 行，最大路由文件)

- **功能**: 平台账号 CRUD + 登录状态三层检测 + 批量操作 + Playwright 验证子进程
- **关键方法**:
  - `_do_playwright_verify()`: 通过独立子进程调用 `scripts/playwright_verify.py` 验证登录
  - `api_account_status()`: 三层检测 (缓存 → API 轻量 → Playwright)
  - `api_account_toggle()` / `api_accounts_batch_toggle()` / `api_accounts_batch_delete()`
- **依赖**: `core/publisher`, `core/credential_crypto`, `core/status_cache`, `core/status_detector`

### 3.3 `posts.py` — 文章 CRUD + 发布

- **功能**: 文章增删改 + 发布到平台 + 自动编译 + 编译缓存
- **关键流程**: 保存文章 → 自动编译所有平台 → 存入 CompiledCache → 发布时重编译 → 调用 Publisher → 记录 publish_log → 自动触发 Deployer
- **依赖**: `core/compiler`, `core/compiled_cache`, `core/renderers`, `core/publisher`, `core/deployer`

### 3.4 `workspace_ui.py` — 工作台/流水线

- **功能**: Provider 选择 + 内容列表 + 流水线执行 (采集→编译→预览→草稿→发布)
- **核心抽象**: `Pipeline` + `ContentObject` 流水线框架
- **依赖**: `core/pipeline`, `core/provider`, 各 Provider 插件 (`provider_markdown`, `provider_notion`, `provider_taobao`)

### 3.5 `exploration.py` — 论坛探索

- **功能**: 探索数据展示 + 平台能力配置 + 标签管理 + Playwright 自定义探索 + 自动发现未探索平台
- **关键路径**: 从 `platform_accounts` 提取 site_url → domain → 匹配 `forum_exploration` 数据
- **限流**: `core/explorer` 双缓存限流 (内存 + SQLite `explore_cooldown` 表，每域名每小时 1 次)

### 3.6 `forum.py` — AI 逛论坛

- **功能**: Discuz 论坛浏览 + 新帖推荐 + 回复检查
- **依赖**: `plugins/forum_reader` (DiscuzForumReader + InterestFilter)

### 3.7 `signin.py` — 签到管理

- **功能**: 签到页面 + 手动/批量签到 + 签到配置 + 统计
- **签到插件注册制**: `core/signin` 的 `@register` + `SigninBase`
- **关键**: 每个签到用 `ThreadPoolExecutor(timeout=30)` 避免卡死

### 3.8 `captcha_browser.py` — 验证码

- **功能**: Discuz 验证码获取 + 验证码登录 + 自动识别 (ttshitu/2captcha) + QR 码 (占位)
- **依赖**: `core/captcha_handler`

### 3.9 `browser_login.py` — Playwright 平台登录

- **功能**: Amobbs / 闲鱼 / OSHWHub 三平台的 Playwright 浏览器登录
- **模式**: 每个平台独立单例管理器 (锁 + session dict)，登录成功后加密保存 Cookie
- **依赖**: `plugins/amobbs_login`, `plugins/xianyu_login`, `plugins/oshwhub_login`

### 3.10 `browser_engine.py` — 浏览器引擎管理

- **功能**: 浏览器引擎启停 + 状态注入 (所有模板的 navbar 状态徽章) + 配置管理
- **上下文注入**: `@app.context_processor` 注入 `pw_status`, `pw_badge_class`, `pw_badge_text` 到全部模板
- **锁超时**: 所有 `self._lock.acquire()` 带 `timeout=0.5~3.0`，防止请求线程卡死

### 3.11 `api_v1.py` — 统一 API v1

- **功能**: API Key 鉴权 + 系统状态 + AI 生成 + 账号列表 + 签到 + 浏览器登录
- **鉴权**: `require_api_key` 装饰器 → API Key 验证 / Session 自动降级
- **API Key**: `sf_` + 48 字符 hex，SHA256 哈希存储，12 字符前缀索引

### 3.12 `api_v2.py` — Gateway API v2

- **功能**: 系统状态/重启/重载 + 日志 + API Key 管理
- **鉴权**: 支持 Session + API Key 两种方式

### 3.13 `price_monitor.py` / `comment_monitor.py` / `xianyu_search.py`

- 分别对应价格监控、评论监控和闲鱼搜索功能，均为较为独立的模块

---

## 4. 核心模块架构

### 4.1 `core/pipeline.py` — 统一内容流水线框架

核心抽象，定义了五种流水线阶段：

```
PipelineStage.COLLECT → COMPILE → PREVIEW → DRAFT → PUBLISH
```

**数据模型**:

- `ContentObject` (dataclass): 统一内容对象，支持 article/video/product 三种类型
- `StageHandler` (ABC): 阶段处理器的抽象基类（`execute(content, **kwargs) → ContentObject`）
- `Pipeline` (调度器): 管理处理器注册和阶段执行，支持 `run()` 完整流水线 / `run_until()` 到指定阶段

**备注**: `CollectHandler`、`CompileHandler`、`PreviewHandler`、`DraftHandler`、`PublishHandler` 目前为占位空壳，实际编译与发布通过 `core/compiler.py` 和 `core/publisher.py` 独立实现。

### 4.2 `core/publisher.py` — 发布器注册制

**抽象类** `Publisher(ABC)`:

| 方法 | 说明 |
|------|------|
| `publish(article, **kwargs)` | `@abstractmethod` — 发布文章 |
| `upload_image(local_path)` | 上传图片到平台图床 (可选) |
| `process_images(article)` | 统一图片上传管线 |
| `retract(article, publish_log)` | 撤回已发布文章 (可选) |
| `validate_config()` | 返回缺失的配置项 |

**注册机制**: 全局 `_registry: dict[str, type[Publisher]]`，通过 `@register` 装饰器注册。工厂方法 `get_publisher(name, config)` / `list_publishers()`。

**登录方法声明**: `login_methods` 类属性定义了每种平台的登录能力 (password/qrcode/phone/cookie 等)，优先级排序，前端据此渲染 Tab。

### 4.3 `core/provider.py` — 内容来源 Provider 注册制

**抽象类** `Provider(ABC)`:

| 方法 | 说明 |
|------|------|
| `list_items()` | `@abstractmethod` — 列出内容项 |
| `get_item(item_id)` | `@abstractmethod` — 获取元数据 |
| `get_item_content(item_id)` | `@abstractmethod` — 获取正文 (Markdown) |
| `validate_config()` | 验证配置完整性 |
| `to_dict()` | 供 API/UI 使用 |

**注册机制**: `_provider_registry` + `@register_provider` 装饰器，与 Publisher 使用相同模式。

### 4.4 `core/deployer.py` — 部署器注册制

**抽象类** `Deployer(ABC)`:

| 方法 | 说明 |
|------|------|
| `deploy()` | `@abstractmethod` — 执行完整部署 |
| `test_connection()` | 测试配置有效性 |
| `validate_config()` | 完整性验证 |

**注册机制**: `_registry` + `@register` 装饰器，平行于 Publisher 模式。

### 4.5 `core/signin.py` — 签到插件注册制

**抽象类** `SigninBase(ABC)`:

| 方法 | 说明 |
|------|------|
| `signin()` | `@abstractmethod` — 执行签到 |
| `can_handle(account)` | 判断能否处理该账号 (按 platform 匹配) |

**注册机制**: `_registry` + `@register`，比 Publisher/Deployer 额外提供 `get_signin_for_account(account)` 自动匹配。

### 4.6 `core/storage.py` — 统一存储抽象层

**抽象类** `StorageBackend(ABC)`:

| 方法 | 说明 |
|------|------|
| `test_connection()` | 测试连接 |
| `upload(local_path, remote_path)` | 文件上传 |
| `upload_bytes(data, remote_path)` | 字节上传 |
| `list(path)` | 列出目录 |
| `mkdir(path)` | 创建目录 |
| `delete(path)` | 删除 |
| `get_url(path)` | 获取访问 URL |

**实现**:

| 实现 | 说明 |
|------|------|
| `LocalStorage` | 本地文件系统 (路径安全检查) |
| `AlistStorage` | AList 远程网盘 (API 驱动，支持 Token 刷新) |

**注册机制**: `_storage_backends` + `@register_storage`

### 4.7 `core/gateway.py` — 通知网关

**抽象类** `GatewayProvider(ABC)`:

| 方法 | 说明 |
|------|------|
| `send(message, config)` | `@abstractmethod` — 发送消息 |

**Data Model**: `GatewayMessage(title, body, level, source, link, timestamp)`

**已实现 Provider**:

| Provider | 支持平台 |
|----------|---------|
| `WebhookProvider` | 通用 HTTP Webhook |
| `FeishuProvider` | 飞书/Lark 机器人 (卡片消息 + 签名) |
| `WeComProvider` | 企业微信机器人 (Markdown) |
| `WeChatProvider` | 微信 (企业微信应用/ILink Bot) |
| `TelegramProvider` | Telegram Bot |
| `DiscordProvider` | Discord Webhook (Embed) |
| `SlackProvider` | Slack Webhook |
| `WhatsAppProvider` | WhatsApp Business Cloud API |
| `DingTalkProvider` | 钉钉机器人 (加签) |

**注册制**: 实例注册模式 (`register_provider(provider_instance)`)，非装饰器模式。

### 4.8 `core/browser_engine.py` — 常驻 Playwright 浏览器引擎

**单例模式** `BrowserEngine`:

- 状态机: `stopped → starting → ready → [error | restarting]`
- 线程安全: `threading.Lock` + `acquire(timeout)`
- 自动关闭: 10 分钟无活动自动关闭 (通过 `check_activity_timeout()` 检查)
- 页面管理: `get_page()` / `close_tab()` / `create_isolated_context()`
- 配置: 默认配置 + 数据库持久化 `playwright_config` 表
- 反检测: 启动时自动注入 webdriver/plugins/languages/chrome/WebGL 覆盖脚本

### 4.9 `core/compiler.py` — 中央编译器

**三阶段流程**:

```
Markdown body → MarkdownParser.parse() → IRDocument
  → FormatConverter.to_bbcode/html/plain_text/markdown()
    → CompiledContent
```

- `IRDocument`: 中间表示 (blocks + images + metadata)
- `IRBlock`: 块级元素 (heading/paragraph/code_block/image/list/table/quote/hr)
- `CompiledContent`: 平台编译产物 (body + warnings + fields)
- `ImagePipeline`: 图片提取 + 本地路径解析 + 大小检查
- `Compiler.compile()`: 主入口，按 `compile_rule` 逐平台编译

### 4.10 `core/status_detector.py` — 三层状态检测

**第一层 API 轻量** (毫秒级，零浏览器):

| 检测器 | 目标平台 | 方法 |
|--------|---------|------|
| `detect_discuz()` | Discuz 论坛 | Cookie 访问 `/home.php?mod=space&do=profile` |
| `detect_csdn()` | CSDN | Cookie 访问 msg.csdn.net + 个人主页 |
| `detect_oshwhub()` | OSHWHub | Cookie 访问 oshwhub.com + 用户主页 |
| `detect_xianyu()` | 闲鱼 | Cookie 访问 goofish.com |

**第二层 / 第三层**: 通过 `routes/accounts.py` 的 `_do_playwright_verify()` 调用独立子进程执行。

### 4.11 `core/anti_detect.py` — 反检测中间件

**配置驱动** `AntiDetectConfig` (环境变量可覆盖):

- 随机 UA / Viewport / Locale 选择
- 鼠标移动模拟 (随机路径 + 偏移)
- 打字模拟 (逐字符随机间隔)
- 滚动模拟 (分段滚动)
- `BehaviorRecorder`: 行为模式记录与速度自适应
- `HumanPage`: Page 包装类，所有操作默认启用人类模拟

### 4.12 `core/credential_crypto.py` — 凭证加密

- 算法: Fernet (AES-128-CBC + HMAC-SHA256)
- 密钥: `~/.hermes/flashsloth/.fs_key` (自动生成，权限 600)，环境变量 `FS_ENCRYPTION_KEY` 可覆盖
- 敏感字段: password, cookie, token, app_secret, api_key, access_token, refresh_token
- 格式: `enc:base64_ciphertext` 前缀标记

### 4.13 `core/explorer.py` — 探索限流

- 双缓存: 内存 + SQLite `explore_cooldown` 表
- 限制: 每域名每小时 1 次 (`MIN_INTERVAL_SECONDS = 3600`)
- 分离设计: `can_explore()` 只检查，`mark_explored()` 只记录，避免失败浪费限流槽位

### 4.14 `core/status_cache.py` / `core/notifier.py` / `core/approval.py`

- **status_cache**: 内存 + SQLite 双缓存，TTL 5 分钟
- **notifier**: 统一通知接口，自动广播到网关终端
- **approval**: 审批流程 (`ApprovalRequest` dataclass + 状态机 PENDING/APPROVED/REJECTED/EXPIRED/CANCELLED)

### 4.15 `core/forum_registry.py` — 智能版块匹配

- 从 `platform_reports/*.json` 自动加载版块数据
- 关键词别名映射 (`alias_map`)
- `match_forum()`: 按标签+标题+正文加权匹配最佳 FID
- 支持 Discuz 论坛和 OSHWHub/CSDN 等非论坛平台

### 4.16 `core/article.py` — 统一数据模型

```python
@dataclass Article:
    title, body, summary, tags, cover, assets, slug, date, status, source, metadata
    to_markdown()      # → frontmatter Markdown
    to_html()          # → HTML
    from_markdown()    # ← frontmatter Markdown 解析
```

### 4.17 `core/database.py` — 数据库初始化

执行 `init_db()` 创建所有核心 DDL（幂等 `CREATE TABLE IF NOT EXISTS` + 迁移 `ALTER TABLE ADD COLUMN`）。

**核心表**: `users`, `articles`, `platform_accounts`, `publish_log`, `deployer_configs`, `deploy_log`, `ai_configs`, `provider_config`, `forum_exploration`, `forum_recommendations`, `notifications`, `verify_codes`, `platform_config`, `site_configs`, `gateway_channels`, `playwright_config`, `ai_call_log`, `api_keys`, `explore_cooldown`, `approval_requests`。

首次运行时自动创建随机管理员 `admin_xxxxxx`。

---

## 5. 抽象类 / 注册制模式总览

FlashSloth 大量使用**注册制模式**（装饰器 + 全局注册表 + 工厂方法），统一架构风格。

| 抽象类 | 注册装饰器 | 工厂方法 | 模块 |
|--------|-----------|----------|------|
| `Publisher(ABC)` | `@register` | `get_publisher()` | `core/publisher.py` |
| `Provider(ABC)` | `@register_provider` | `get_provider()` | `core/provider.py` |
| `Deployer(ABC)` | `@register` | `get_deployer()` | `core/deployer.py` |
| `SigninBase(ABC)` | `@register` | `get_signin()` / `get_signin_for_account()` | `core/signin.py` |
| `StorageBackend(ABC)` | `@register_storage` | `get_storage()` | `core/storage.py` |
| `StageHandler(ABC)` | 实例注册 `set_handler()` | 无 (手动构建) | `core/pipeline.py` |
| `GatewayProvider(ABC)` | `register_provider(inst)` | `get_provider()` | `core/gateway.py` |
| `CaptchaProvider` | (待查) | `get_handler()` | `core/captcha_handler.py` |

**注册制统一模式**:

```python
_registry: dict[str, type[BaseClass]] = {}

def register(cls):
    _registry[cls.name] = cls
    return cls

def get(name, config=None):
    cls = _registry.get(name)
    if not cls: raise KeyError(...)
    return cls(config)

def list_all() -> list[dict]:
    return [{"name": cls.name, ...} for cls in _registry.values()]
```

**需要注意的问题**:
- `core/signin.py` 的注册装饰器使用 `try/except` fallback import 防止注册器分裂（铁律 I1/I2）
- `core/gateway.py` 使用实例注册而非类注册，与其他模块不一致

---

## 6. 数据库表结构

| 表名 | 用途 | 核心字段 |
|------|------|---------|
| `users` | 用户 | id, username, password_hash, email, phone, is_admin, twofa_type/secret |
| `articles` | 文章 | id, user_id, title, body, summary, tags, source, status, created_at, updated_at |
| `platform_accounts` | 平台账号 | id, user_id, platform, account_name, config_json(加密), is_active, sort_order, status, keep_alive |
| `publish_log` | 发布记录 | id, article_id, account_id, platform, success, url, error, deploy_status, created_at |
| `deployer_configs` | 部署器配置 | id, user_id, deployer_name, display_name, config_json, is_active |
| `deploy_log` | 部署日志 | id, config_id, deployer_name, success, url, error, message |
| `provider_config` | Provider/存储配置 | id, user_id, provider_type, config_json (通用配置存储表) |
| `ai_configs` | AI 供应商 | id, user_id, provider, alias, api_key, api_base, api_format, models, balance, enabled |
| `ai_call_log` | AI 调用日志 | id, capability, provider, model, prompt_tokens, cost, success |
| `forum_exploration` | 论坛版块探索数据 | id, platform, platform_domain, section_id, section_name, can_post, keywords, extra_info, tags_of_interest |
| `forum_recommendations` | 论坛推荐帖子 | id, user_id, platform, title, url, tid, fid, score, summary, is_read, reply_*, source |
| `notifications` | 站内通知 | id, user_id, title, message, level, source, link, is_read |
| `gateway_channels` | 通知网关渠道 | id, name, platform, config_json, enabled, user_id |
| `verify_codes` | 验证码 | id, target, code, action, expires_at, used |
| `platform_config` | 平台能力配置 | id, platform, platform_domain, config_json |
| `site_configs` | 站点部署配置 | id, user_id, platform, comment_system, plugins_config, extra_config |
| `playwright_config` | 浏览器引擎配置 | id=1, config_json |
| `api_keys` | API Key | id, user_id, name, key_hash, key_prefix, is_active |
| `approval_requests` | 审批请求 | id, title, description, action, status, metadata, response_note |
| `explore_cooldown` | 探索限流 | domain, last_explore_at (独立 DB: status_cache.db 也使用) |
| `compiled_cache` (由编译器创建) | 编译缓存 | article_id, platform, source_hash, title, body, warnings |
| `price_monitors` | 价格监控 | id, user_id, name, lcsc_code, target_price |
| `price_history` | 价格历史 | id, monitor_id, price, fetched_at |
| `comment_replies` | 评论回复 | id, article_id, account_id, platform, thread_*, reply_*, is_read, is_auto_replied |
| `comment_monitor_config` | 评论监控配置 | id, account_id, enabled, slot_*, auto_reply, reply_style, max_replies_per_day |
| `signin_log` | 签到日志 | (由插件创建) account_id, platform, success, already_signed |

---

## 7. 模块依赖关系图

```
┌──────────────────────────────────────────────────────────────┐
│                        routes/                               │
│  (Web 层 — @app.route 注册, 请求/响应处理, 模板渲染)          │
├──────────────────────────────────────────────────────────────┤
│  auth.py ────────────────┬────────────────── accounts.py     │
│  posts.py ───────┬───────┼────────┬───────── browser_*.py    │
│  workspace_ui.py ┼───────┼────────┼───────── captcha_browser  │
│  exploration.py ─┼───────┼────────┼───────── signin.py       │
│  forum.py ───────┼───────┼────────┼───────── ai.py           │
│  price_monitor   ┼───────┼────────┼───────── comment_monitor │
│  storage_deploy  ┼───────┼────────┼───────── xianyu_search   │
│  gateway ────────┼───────┼────────┼───────── notifications   │
│  approval ───────┼───────┼────────┼───────── external_svc    │
│  api_v1 ─────────┼───────┼────────┼───────── api_v2          │
│  platforms ──────┼───────┤        │                           │
└──────┬───────────┼───────┼────────┼───────────────────────────┘
       │           │       │        │
       ▼           ▼       ▼        ▼
┌──────────────────────────────────────────────────────────────┐
│                    core/ (业务逻辑层)                          │
├──────────────────────────────────────────────────────────────┤
│  ┌───────────┐ ┌──────────┐ ┌─────────┐ ┌───────────────┐   │
│  │ publisher │ │ provider │ │deployer │ │   signin      │   │
│  │  (ABC)    │ │  (ABC)   │ │ (ABC)   │ │   (ABC)       │   │
│  │ @register │ │@register │ │@register│ │  @register    │   │
│  └─────┬─────┘ └────┬─────┘ └────┬────┘ └──────┬────────┘   │
│        │             │            │             │            │
│  ┌─────▼─────────────▼────────────▼─────────────▼────────┐   │
│  │              database.py (DDL + 迁移 + 种子)            │   │
│  │  ┌─────────────┐ ┌──────────┐ ┌──────────────────┐    │   │
│  │  │ article.py  │ │compiler  │ │ pipeline.py      │    │   │
│  │  │ (dataclass) │ │(IR→fmt)  │ │ (ContentObject)  │    │   │
│  │  └─────────────┘ └──────────┘ └──────────────────┘    │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────┐ ┌──────────────┐ ┌────────────────────┐        │
│  │ gateway  │ │browser_engine│ │ status_detector    │        │
│  │ (ABC)    │ │ (Singleton)  │ │ (3-tier API)      │        │
│  └──────────┘ └──────────────┘ └────────────────────┘        │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌───────────┐    │
│  │ explorer │ │anti_detect│ │ status_    │ │ credential│    │
│  │(限流+探索)│ │(HumanPage)│ │ cache     │ │ _crypto   │    │
│  └──────────┘ └──────────┘ └────────────┘ └───────────┘    │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌───────────┐    │
│  │ notifier │ │ approval │ │ storage    │ │ config    │    │
│  │(通知统发)│ │(审批流程) │ │ (ABC+impl) │ │ (YAML)   │    │
│  └──────────┘ └──────────┘ └────────────┘ └───────────┘    │
│                                                               │
│  ┌──────────────┐ ┌──────────┐ ┌───────────────┐            │
│  │forum_registry│ │ ai_      │ │ provider_     │            │
│  │(智能匹配)    │ │ provider │ │ registry      │            │
│  └──────────────┘ └──────────┘ └───────────────┘            │
│                                                               │
└──────────────────────────────────────────────────────────────┘
       │              │             │              │
       ▼              ▼             ▼              ▼
┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
│ plugins/  │ │ scripts/ │ │ sdk/     │ │ platform_reports/ │
│ (发布器)  │ │(验证脚本) │ │(API适配) │ │ (JSON探索数据)    │
│ (签到器)  │ │(探索脚本) │ │          │ │ (JSON登录能力)    │
│ (登录)    │ │          │ │          │ │                   │
└───────────┘ └──────────┘ └──────────┘ └──────────────────┘
```

---

## 8. 数据流架构

### 8.1 完整内容发布流水线

```
┌──────┐   ┌──────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│Provider│ → │ Compiler │ → │Publisher│ → │Deployer │ → │ Gateway │
│(采集)  │   │(编译)    │   │(发布)   │   │(部署)   │   │(通知)   │
└──────┘   └──────────┘   └─────────┘   └─────────┘   └─────────┘
    │           │              │             │              │
    ▼           ▼              ▼             ▼              ▼
  Notion/    Markdown→    发布到各      GitHub       飞书/企微/
  Markdown   BBCode/HTML  平台论坛     Pages        微信等
```

### 8.2 多平台账号生命周期

```
添加账号 → 配置凭证(加密) → 状态检测(三级) → 签到(定时) → 用于发布
                                                              ↓
                             Cookie过期 ← 状态检测 → 通知管理员刷新Cookie
```

### 8.3 探索数据流

```
用户添加账号(site_url) → 探索检测(有无数据?) → 自动探索(Playwright)
                                                          ↓
                                                    forum_exploration 表
                                                          ↓
    发布时 → forum_registry.match_forum() → 按文章内容匹配版块FID
```

---

## 9. 架构评估与改进建议

### 9.1 优势

1. **统一注册制架构**: 5 个核心抽象类 (Publisher/Provider/Deployer/Signin/StorageBackend) 使用相同注册模式，插件扩展只需继承 + `@register`
2. **三层状态检测**: 缓存 → API 轻量 → Playwright，性能与精度兼顾
3. **线程安全设计**: 所有锁带超时，引擎状态读取不阻塞请求线程
4. **防错模式**: `try/except fallback import` 避免注册器分裂
5. **模块化好**: 24 个路由文件按功能拆分，每个文件职责明确
6. **加密安全**: Fernet AES-128 + 文件权限 600 + 脱敏显示

### 9.2 改进建议

| 问题 | 建议 |
|------|------|
| **文件过大**: `accounts.py` 1565 行，`gateway.py` 1181 行 | 拆分为多个子模块 (accounts 可拆为 crud/status/test) |
| **注册器不一致**: `gateway.py` 用实例注册，其他用类注册 | 统一为类注册模式 |
| **Pipeline 空壳**: 5 个 StageHandler 均为空壳子类 | 移除空壳类或将 Compiler/Publisher 适配为 StageHandler |
| **混合 import 路径**: `from core.*` 和 `from flashsloth.core.*` 混用 | 全项目统一为 `flashsloth.core.*` |
| **Signin 注册铁律复杂**: 防分裂的 fallback import | 统一 PYTHONPATH 或使用可执行包 |
| **Controller 层缺失**: 路由中混合了大量的业务逻辑 | 抽取 Service/Controller 层分离 Web 和业务逻辑 |
| **数据库连接管理**: 每请求多次 `get_db() + close()` | 考虑 Flask `g` 上下文管理或连接池 |
| **编译缓存 SQLite 表**: 在 routes/posts.py 中隐式创建 | 在 `database.py` 中统一管理 DDL |
| **子进程验证**: `scripts/playwright_verify.py` 通过 subprocess 调用 | 可用 asyncio subprocess 或共享 BrowserEngine 替代 |

### 9.3 安全概况

| 措施 | 状态 |
|------|------|
| 密码哈希 | ✅ werkzeug `generate_password_hash` |
| 凭证加密 | ✅ Fernet AES-128 (`.fs_key` 600) |
| 脱敏显示 | ✅ `••••••••` |
| API Key 鉴权 | ✅ SHA256 + prefix 索引 |
| 路径遍历防护 | ✅ StorageBackend 安全检查 |
| SQL 注入 | ✅ 参数化查询 |
| 跨站请求 | 需确认 CSRF 保护状态 |

---

*本报告基于对 `routes/` (24 文件) 和 `core/` (29 文件) 的完整源代码分析生成。*
