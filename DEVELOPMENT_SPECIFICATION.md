# 🦥 FlashSloth 开发说明书
**版本**: v4.80 | **最后更新**: 2026-07-07 (每小时自动更新)
**架构对照**: ✅ 已核对 ARCHITECTURE.md

---

## 一、项目概述

**定位**: 个人数字资产全聚合平台
**目标用户**: 个人站长/创作者/开发者，需要在多平台统一管理内容发布、账号、签到、评论
**核心能力**:
- 多平台内容统一发布（Discuz!/CSDN/知乎/掘金/B站/OSHWHub/GitHub Pages/Twitter/微信公众号/WordPress/闲鱼）
- 定时自动签到（论坛/CSDN/OSHWHub）
- 统一通知网关（22+ Provider，推送到飞书/企微/微信/Telegram/Discord/Slack/邮件/Webhook）
- 账号三层登录状态检测（API轻量→Playwright快速→Playwright全量）
- 论坛探索与版块监控（Discuz 系的自动版块结构采集）
- 评论监控与 AI 自动回帖
- 价格监控（LCSC 立创商城元器件）
- 闲鱼集成（搜索/发布/MTOP 签名 API/自动回复 Sidecar）
- AI 统一路由（多供应商自动切换/余额查询/调用日志）
- 工作台流水线（Provider→采集→编译→预览→草稿→发布）
- 审批流程系统（AI 发起敏感操作的人工审批）
- Gateway REST API（对外暴露系统/账号/文章/签到/AI 接口）
- 凭证安全加密（Fernet AES-128-CBC）
- Playwright 反检测人类行为模拟

**技术栈**: Python 3.11 + Flask + SQLite (WAL 模式) + Playwright + Hermes Agent 部署
**编码规则**: `routes/accounts.py` 使用 Tab 缩进，其他文件使用 4 空格缩进

---

## 二、系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    用户界面层 (Flask Web UI)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ 仪表盘   │ │ 文章管理  │ │ 账号管理  │ │ 工作台/流水线     │   │
│  │ 总览     │ │ 发布/签  │ │ 多平台   │ │ Provider→采集→   │   │
│  │          │ │ 到/探索  │ │ 管理     │ │ 编译→发布        │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ 通知中心  │ │ 配置中心  │ │ AI管理   │ │  Gateway API     │   │
│  │ 网关/审  │ │ 规则/AI  │ │ 路由/日  │ │  (REST v1+v2)     │   │
│  │ 批/通知  │ │ 部署     │ │ 志/余额  │ │                   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   统一工作流引擎                                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  core/ 模块层                                             │   │
│  │  ├── pipeline.py      统一流水线调度器                     │   │
│  │  ├── compiler.py      文章编译器 (MD→IR→输出)              │   │
│  │  ├── ai_provider.py   AI 路由框架                         │   │
│  │  ├── publisher.py     Publisher（发布器）基类+注册中心      │   │
│  │  ├── deployer.py      部署器基类                           │   │
│  │  ├── scheduler.py     签到调度器（守护线程）                │   │
│  │  ├── image_pipeline.py 图片处理流水线                      │   │
│  │  ├── gateway.py       通知网关核心（22+ Provider）          │   │
│  │  ├── notifier.py      统一通知系统                          │   │
│  │  ├── approval.py      审批流程系统                          │   │
│  │  ├── browser_engine.py 常驻 Playwright 浏览器引擎           │   │
│  │  ├── anti_detect.py   反检测/人类行为模拟                   │   │
│  │  ├── status_detector.py 三层登录状态检测器                  │   │
│  │  ├── status_cache.py  状态缓存系统（内存+SQLite）           │   │
│  │  ├── explorer.py      Playwright 论坛探索引擎              │   │
│  │  ├── forum_registry.py 统一智能版块匹配系统                 │   │
│  │  ├── price_monitor.py  LCSC 元器件价格监控                 │   │
│  │  ├── credential_crypto.py Fernet AES-128-CBC 凭证加密      │   │
│  │  ├── compile_rule.py  每平台编译规则定义                    │   │
│  │  ├── compiled_cache.py 编译产物数据库缓存                  │   │
│  │  ├── renderers.py     各平台编译产物渲染器                  │   │
│  │  ├── provider.py      Provider 统一内容来源基类             │   │
│  │  ├── provider_registry.py 动态 AI 供应商注册表加载          │   │
│  │  ├── signin.py        SigninBase 签到基类+注册机制         │   │
│  │  ├── captcha_handler.py 验证码处理器                       │   │
│  │  ├── storage.py       存储抽象层                           │   │
│  │  ├── config.py        全局配置加载                          │   │
│  │  ├── article.py       文章数据模型                          │   │
│  │  └── database.py      数据库初始化+迁移+种子数据            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  sdk/ 统一平台适配器层                                      │   │
│  │  ├── adapter.py      PlatformAdapter 基类+数据模型       │   │
│  │  ├── router.py       内容路由引擎                        │   │
│  │  ├── scaffold.py     适配器脚手架生成器                  │   │
│  │  └── adapters/       各平台实现（16个文件）               │   │
│  │      ├── xianyu_v2.py  闲鱼 API v2（搜索/详情/比价）    │   │
│  │      ├── xianyu.py     闲鱼 PlatformAdapter（Playwright）│   │
│  │      ├── bilibili.py  B站适配器                         │   │
│  │      ├── csdn.py      CSDN 适配器                       │   │
│  │      ├── zhihu.py     知乎适配器                        │   │
│  │      ├── juejin.py    掘金适配器                        │   │
│  │      ├── oshwhub.py   OSHWHub 适配器                   │   │
│  │      ├── amobbs.py    阿莫论坛适配器                     │   │
│  │      ├── mydigit.py   数码之家适配器                     │   │
│  │      ├── wordpress.py WordPress 适配器                  │   │
│  │      ├── wechat.py    微信适配器                        │   │
│  │      ├── notion.py    Notion 适配器                     │   │
│  │      ├── github_pages.py GitHub Pages 适配器            │   │
│  │      └── giscus.py    Giscus 适配器                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   基础设施层                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ ┌──────────┐  │
│  │ 统一登录  │ │ 配置中心  │ │ 通知系统  │ │ 数据库│ │  存储    │  │
│  │ Cookie   │ │ config/  │ │ 邮件/钉  │ │SQLite│ │ 本地/    │  │
│  │ 管理     │ │ JSON/DB  │ │ 钉/微信  │ │WAL   │ │ AList    │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐                │
│  │ AI路由    │ │ 反检测   │ │ 定时任务  │ │ 凭证  │                │
│  │ 多供应商  │ │ 人类模拟  │ │ 调度器   │ │ 加密  │                │
│  │ 自动切换  │ │          │ │ cron     │ │Fernet│                │
│  └──────────┘ └──────────┘ └──────────┘ └──────┘                │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 用户界面层（页面/路由）

| 页面 | 路由 | 模板 | 功能 |
|------|------|------|------|
| 仪表盘 | `GET /` | `index.html` | 总览仪表盘（文章数/账号数/发布记录/部署状态） |
| 登录 | `GET/POST /login` | `login.html` | 用户登录 |
| 注册 | `GET/POST /register` | `register.html` | 用户注册 |
| 账号管理 | `GET /accounts` | `accounts.html` | 多平台账号统一管理（分组展示/登新增/编辑/删除/状态检测） |
| 文章编辑 | `GET/POST /post/new` | `edit.html` | 新建文章 |
| 文章编辑 | `GET/POST /post/edit/<id>` | `edit.html` | 编辑文章（含自动编译） |
| 发布管理 | `GET /publish/manage/<id>` | `publish_manage.html` | 发布管理页面 |
| 发布选择 | `POST /publish/<id>` | `publish_select.html` | 选择发布平台和目标 |
| 编译预览 | `GET /preview/<id>` | `preview.html` | 文章预览 |
| 编译预览 | `GET /compile/preview/<id>` | `compile_preview.html` | 编译预览（含各平台对比） |
| 签到管理 | `GET /signin` | `signin.html` | 签到状态/统计/手动签到 |
| AI 设置 | `GET /ai` | `ai_settings.html` | AI 供应商配置 |
| AI 日志 | `GET /ai/logs` | `ai_logs.html` | AI 调用日志查看 |
| 网关管理 | `GET /gateway` | `gateway.html` | 通知网关配置 |
| 探索管理 | `GET /exploration` | `exploration.html` | 论坛探索数据管理 |
| 审批管理 | `GET /approval` | `approval.html` | 审批列表/历史 |
| 价格监控 | `GET /price-monitor` | `price_monitor.html` | LCSC 价格监控 |
| 通知中心 | `GET /notifications` | `notifications.html` | 通知列表 |
| 闲鱼搜索 | `GET /xianyu/search` | `xianyu_search.html` | 闲鱼商品搜索 |
| 工作台 | `GET /workspace` | `workspace.html` | 内容流水线工作台 |
| 论坛阅读器 | `GET /forum-reader` | `forum_reader.html` | AI 逛论坛推荐 |
| 评论监控 | `GET /comment-monitor` | `comment_monitor.html` | 评论收件箱 |
| 存储设置 | `GET /storage/settings` | `storage_settings.html` | 存储后端配置 |
| 部署管理 | `GET /deployers` | `deployers.html` | 部署器配置 |
| 设置 | `GET /settings` | `settings.html` | 用户设置 |
| 改密 | `GET/POST /change_password` | `change_password.html` | 修改密码 |
| 忘记密码 | `GET/POST /forgot_password` | `forgot_password.html` | 密码重置 |
| 2FA 验证 | `GET /verify-2fa` | `verify_2fa.html` | 两步验证 |

### 2.2 业务逻辑层（模块）

| 模块 | 文件 | 说明 |
|------|------|------|
| routes/auth.py | 认证路由 | 登录/注册/改密/2FA/短信验证码/首页仪表盘 |
| routes/accounts.py | 账号路由 | 账号 CRUD/状态检测/加密解密/批量操作(1484行) |
| routes/posts.py | 文章路由 | 文章 CRUD/发布流程/编译/自动编译(849行) |
| routes/ai.py | AI 路由 | AI 供应商管理/配置/生成/余额查询/日志(658行) |
| routes/signin.py | 签到路由 | 签到页面/手动签到/统计/调度器控制(374行) |
| routes/browser_engine.py | 浏览器引擎路由 | Playwright 启停控制/状态查询/心跳(187行) |
| routes/browser_login.py | 浏览器登录路由 | Discuz/Amobbs 通用 Playwright 登录(299行) |
| routes/captcha_browser.py | 验证码路由 | Discuz 验证码获取/QR 扫码/登录流程(329行) |
| routes/comment_monitor.py | 评论监控路由 | 回复收件箱/配置/AI 自动回复(600行) |
| routes/exploration.py | 探索路由 | 论坛版块数据管理/平台能力展示(589行) |
| routes/forum.py | 论坛阅读路由 | AI 逛论坛/推荐列表/浏览/回复(253行) |
| routes/workspace_ui.py | 工作台路由 | Provider 选择/流水线执行/日志(374行) |
| routes/gateway.py | 网关路由 | 通知渠道 CRUD/测试发送(270行) |
| routes/notifications.py | 通知路由 | 通知列表/标记已读/未读计数(67行) |
| routes/approval.py | 审批路由 | 待审批/历史/通过/拒绝(144行) |
| routes/price_monitor.py | 价格监控路由 | 监控管理/刷新历史(122行) |
| routes/storage_deploy.py | 存储部署路由 | 存储后端配置/部署器管理(505行) |
| routes/xianyu_search.py | 闲鱼搜索路由 | 闲鱼关键词搜索(142行) |
| routes/platforms.py | 平台预设路由 | 平台预设配置(19行) |
| routes/api_v1.py | API v1 | 统一 REST API v1(532行) |
| routes/api_v2.py | API v2 | Gateway REST API v2(205行) |
| routes/external_services.py | 外部服务路由 | 外部服务注册/健康检查(89行) |

### 2.3 数据层

- **主数据库**: `flashsloth.db` (SQLite WAL 模式)
- **缓存数据库**: `status_cache.db` (账号登录状态缓存)
- **凭证加密**: Fernet AES-128-CBC（密钥：`~/.hermes/flashsloth/.fs_key` 或环境变量 `FS_ENCRYPTION_KEY`）

---

## 三、模块详细说明

### 3.1 账号管理模块 (`routes/accounts.py` + `templates/accounts.html`)

- **功能说明**: 多平台账号的统一管理界面，支持添加、编辑、删除、启用/禁用、配置查看、登录状态检测
- **页面端点**:
  - `GET /accounts` — 账号管理页面（按平台分组展示，含缓存状态）
  - `POST /accounts/add` — 新增/更新账号（含加密配置存储）
  - `GET /accounts/edit/<id>` — 编辑账号（重定向到 `/accounts` 模态框）
  - `DELETE /accounts/delete/<id>` — 删除账号
- **API 端点**:
  - `GET /api/accounts/config/<id>` — 获取脱敏配置
  - `POST /api/accounts/<id>/toggle` — 切换启用/禁用
  - `GET /api/accounts/<id>/status` — 三层登录状态检测(API轻量→Playwright快速→全量)
  - `POST /api/accounts/batch/status` — 批量刷新状态
  - `POST /api/accounts/batch/publish` — 批量发布
  - `POST /api/accounts/batch/delete` — 批量删除
- **登录方式**: 密码 / QR 扫码 / Cookie 粘贴（由各 Publisher 定义 `login_methods`）
- **Discuz 系平台集合**: `DISCUZ_PLATFORMS = {"amobbs", "discuz", "mydigit"}`
- **数据流**: 用户表单提交 → `encrypt_config()` 加密敏感字段 → 存入 `platform_accounts.config_json`
- **关键逻辑**: 配置脱敏、编辑时掩码字段保留原值、自动生成不重名默认别名、状态检测三级降级

### 3.2 发布器模块 (`plugins/publisher_*.py`)

所有 Publisher 继承 `core/publisher.py` 的 `Publisher` 基类，通过 `@register` 装饰器注册。

| 发布器 | 类名 | 登录方式 | 特点 |
|--------|------|----------|------|
| `Discuz! 论坛` | `DiscuzPublisher` | 密码+验证码 / QR扫码 / Cookie / 手机 | 多域名限制(amobbs/mydigit)，图片/附件限制 |
| `CSDN` | `CSDNPublisher` | 密码 / 手机 | Playwright 浏览器自动化，Markdown 编辑器 |
| `知乎` | `ZhihuPublisher` | Cookie | Playwright 自动化，专栏编辑 |
| `掘金` | `JuejinPublisher` | 密码/QR/Cookie | 模拟浏览器请求 (requests) |
| `Bilibili 专栏` | `BilibiliPublisher` | 密码/QR/Cookie/手机 | Bilibili API + Cookie 认证 |
| `OSHWHub` | `OshwhubPublisher` | JLC 统一登录/手机 | Playwright + 即时代理登录 |
| `闲鱼 (v1)` | `XianyuPublisher` | 密码/QR/Cookie | 基于 XianyuAutoAgent API |
| `闲鱼 V2 (MTOP)` | `XianyuV2Publisher` | Cookie 导入 | MTOP 签名 API + AI 类目 |
| `闲鱼商品(预留)` | `XianyuProductsPublisher` | 密码/Cookie | 商品图片/价格/分类/成色 |
| `闲鱼自动回复Sidecar` | `XianyuAutoReplySidecar` | — | 对接 xianyu-auto-reply Docker |
| `闲鱼 Sidecar 适配器` | `XianyuSidecarAdapter` | — | 统一 Sidecar 协议 |
| `Twitter/X` | `TwitterPublisher` | — | 图片上传管道/Article兼容/草稿隔离 |
| `微信公众号` | `WechatPublisher` | — | 图片上传/封面/摘要 |
| `WordPress` | `WordPressPublisher` | — | REST API 发布 |
| `RSS` | `RSSPublisher` | — | RSS 源生成 |
| `GitHub Pages` | `GitHubPagesBlogPublisher` | 无需登录 | 本地 Markdown 写入 + git push |

**通用发布流程**: `publish(Article)` → `process_images(Article)` → 平台特定 HTTP/Playwright → 返回 `{success, url, id, error}`

### 3.3 网关通知模块 (`routes/gateway.py` + `core/gateway.py`)

- **功能说明**: 统一消息通知网关，将系统事件通过多终端推送
- **GatewayMessage**: title / body / level / source / link / timestamp
- **支持的 Provider (22+)**: webhook, feishu, wecom, wechat (iLink Bot), discord, slack, telegram, email
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
- **签到窗口**: 配置时间（默认 08:00）起 1 小时窗口内随机执行，支持 ±30min 随机偏移
- **已今日签过判断**: 查询 `signin_log` 表（date 去重）
- **签到插件**:

| 插件 | 文件 | 平台 | 实现方式 |
|------|------|------|----------|
| `signin_discuz` | `plugins/signin_discuz.py` | Discuz! (k_misign) | Playwright |
| `signin_csdn` | `plugins/signin_csdn.py` | CSDN (已迁移至微信小程序) | Playwright |
| `signin_oshwhub` | `plugins/signin_oshwhub.py` | OSHWHub | Playwright (Cookie过期自动fallback密码登录) |

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
- **限流规则**: 每域名每小时最多探索一次（`explore_cooldown` 表持久化，双缓存策略 内存+DB）
- **核心流程**: 检测论坛类型 → 爬取版块列表 → 对比差异(内容哈希) → 保存到 DB
- **版块注册中心** (`core/forum_registry.py`): 从 `platform_reports/*.json` 自动加载论坛版块数据
- **支持平台**: Discuz! (amobbs.com, mydigit.cn 等)
- **定时脚本**:
  - `scripts/hourly_forum_check.py` — 每小时增量检查 Discuz 论坛版块变更
  - `scripts/sync_registry_keywords.py` — 将 forum_registry 关键词同步到 forum_exploration DB
  - `scripts/consolidate_forum_data.py` — 合并 www 前缀数据到非 www 域名，去重
  - `scripts/compare_forum_data.py` — 对比新旧论坛数据差异
  - `scripts/playwright_verify.py` — 子进程 Playwright 账号登录验证
- **API 端点**:
  - `GET /exploration` — 探索数据管理页面
  - `GET /api/exploration/platforms` — 平台列表
  - `GET /api/exploration/platform/<domain>` — 平台详情（版块/能力/标签）
  - `POST /api/exploration/explore` — 启动探索
  - `POST /api/exploration/tags` — 更新关心标签/关键词
  - `GET /api/exploration/section/<sid>` — 板块详情
  - `POST /api/exploration/explore/<domain>` — 探索指定域名

### 3.6 凭证安全模块 (`core/credential_crypto.py`)

- **加密方式**: Fernet (AES-128-CBC + HMAC-SHA256) 对称加密
- **密钥来源**: `~/.hermes/flashsloth/.fs_key`（权限 600，自动生成）或环境变量 `FS_ENCRYPTION_KEY`
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
- **余额查询 API**: DeepSeek/OpenAI 余额（零 token 消耗）
- **AI 调用日志**: 自动记录每次调用的元数据到 `ai_call_log` 表
- **Provider 注册表** (`core/provider_registry.py`): 从 `core/provider_registry.json` 动态加载供应商预设
- **API 端点**:
  - `GET /ai` — AI 设置页面
  - `GET /ai/logs` — AI 调用日志页面
  - `GET /api/ai/providers` — 列出所有 Provider 及能力
  - `GET /api/ai/config` — AI 路由配置
  - `POST /api/ai/config` — 更新配置
  - `POST /api/ai/generate` — AI 生成
  - `POST /api/ai/models` — 获取模型列表（API Key 探针）
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
| 自动回复 Sidecar | `plugins/publisher_xianyu_auto_reply.py` | 对接 Docker xianyu-auto-reply |
| Sidecar 适配器 | `plugins/publisher_xianyu_sidecar.py` | 统一 Sidecar 协议 |
| SDK v2 适配器 | `sdk/adapters/xianyu_v2.py` | 搜索/详情/比价/Token 管理 |
| SDK Playwright | `sdk/adapters/xianyu.py` | Playwright 浏览器自动化 |
| MTOP 客户端包 | `plugins/xianyu_client/` | 纯 Python MTOP 签名包 |
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
- **API 端点**:
  - `GET /notifications` — 通知中心页面
  - `GET /api/notifications` — 通知列表（支持分页/筛选/未读过滤）
  - `POST /api/notifications/<nid>/read` — 标记已读
  - `POST /api/notifications/read-all` — 全部标记已读
  - `GET /api/notifications/unread-count` — 未读计数

### 3.13 SDK 平台适配器层 (`sdk/`)

| 文件 | 功能 |
|------|------|
| `sdk/adapter.py` | PlatformAdapter 基类 + Article/Comment/AdapterCapability 数据模型 |
| `sdk/router.py` | 内容路由引擎（RouteRule → source→target） |
| `sdk/scaffold.py` | 适配器脚手架生成器（一键生成新平台适配器模板） |
| `sdk/adapters/xianyu_v2.py` | 闲鱼 API v2 适配器（搜索/详情/比价） |
| `sdk/adapters/xianyu.py` | 闲鱼 PlatformAdapter（Playwright 浏览器自动化） |
| `sdk/adapters/bilibili.py` | B站适配器（save_as_draft + upload_image） |
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

- 部署管理负责将静态站点发布到托管平台（GitHub Pages 等）
- `core/deployer.py` — Deployer 抽象基类 + `@register` 注册器
- `plugins/deployer_github_pages.py` — GitHub Pages 部署实现
- `routes/storage_deploy.py` — 存储后端配置 + 部署配置管理页面 + API
- 数据库 `deployer_configs` + `deploy_log` 表保存用户部署配置和日志
- `core/storage.py` — 存储抽象层（LocalStorage, AlistStorage）
- `plugins/storage_alist.py` — AList 存储后端实现
- **API 端点**:
  - `GET /storage/settings` — 存储设置页面
  - `POST /api/storage/config` — 更新存储后端配置
  - `POST /api/storage/test` — 测试存储连接
  - `GET /deployers` — 部署配置页面
  - `POST /api/deployer/add` — 添加部署配置
  - `POST /api/deployer/<id>/run` — 执行部署
  - `GET /api/deployer/logs` — 部署日志

### 3.15 工作台模块 (`routes/workspace_ui.py` + `core/provider.py` + `core/pipeline.py`)

- `core/provider.py` — Provider 抽象基类（ContentItem 模型 + `@register_provider` 装饰器）
- `core/pipeline.py` — 统一内容流水线调度器，5 阶段 PipelineStage (Collect→Compile→Preview→Draft→Publish)
- `plugins/provider_markdown.py` — 扫描 `posts/` 目录的 Markdown 文件
- `plugins/provider_notion.py` — 通过 Notion API 读取数据库
- `plugins/provider_taobao.py` — 淘宝商品 Provider
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

- 自动记录每一次 AI 调用的元数据（模型、token数、费用、成功/失败）
- `ai_call_log` 表：id/capability/provider/model/prompt_tokens/response_tokens/cost/success/error/response_summary/prompt_preview/created_at
- `log_ai_call()` — 导出日志函数，在 `AIRouter.call()` 的双路径中自动调用
- `/ai/logs` — 日志查看页面（分页、按能力筛选、按状态筛选）

### 3.17 评论监控模块 (`plugins/reply_monitor.py` + `routes/comment_monitor.py`)

- **功能说明**: 定时检查各论坛已发表帖子的新回复，AI 生成智能回帖
- **核心组件**:
  - `plugins/reply_monitor.py` — DiscuzReplyExtractor 采集引擎（使用 HumanSession）
  - `routes/comment_monitor.py` — 收件箱 UI + API 端点 + 定时调度
- **数据表**: `comment_replies` + `comment_monitor_config`
- **能力**: 多论坛统一管理 / 新回复识别去重 / 定时分段检查(早/中/晚) / AI 自动回帖 / 账号配置绑定
- **API 端点**:
  - `GET /comment-monitor` — 监控页面
  - `GET /api/comment-monitor/replies` — 回复列表（分页/筛选/时间范围）
  - `GET /api/comment-monitor/accounts` — 支持监控的账号
  - `POST /api/comment-monitor/run/<account_id>` — 手动运行检查
  - `POST /api/comment-monitor/reply/<reply_id>` — AI 自动回复
  - `POST /api/comment-monitor/reply/regen/<reply_id>` — 重新生成回复
  - `PUT /api/comment-monitor/config/<account_id>` — 更新监控配置
  - `PUT /api/comment-monitor/reply/<reply_id>/mark-read` — 标记已读

### 3.18 登录状态检测 (`core/status_detector.py` + `core/status_cache.py`)

- **三层检测架构**:

| 层级 | 方法 | 开销 | 说明 |
|------|------|------|------|
| 第一层 | API 轻量检测 | 毫秒级 | 用 Cookie 调平台 API/页面提取用户信息 |
| 第二层 | Playwright 快速检测 | 秒级 | 打开个人主页，单页面加载 |
| 第三层 | 全量 Playwright | 数秒 | 完整打开网站，注入 Cookie 模拟登录 |

- **检测结果结构**: logged_in/username/display_name/points/level/avatar_url/method/status/success
- **支持平台**: Discuz!/CSDN/OSHWHub/知乎/掘金 等通过 `_detect_*` 函数实现
- **缓存系统**: 内存缓存(5分钟 TTL) + SQLite `status_cache.db` 持久化，缓存键 `status:{account_id}`

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

### 3.20 AI 逛论坛 (`plugins/forum_reader.py`)

- **功能说明**: 自动登录配置的论坛账号，抓取新帖子，AI 筛选推荐
- **DiscuzForumReader** + InterestFilter: 读取 Discuz! 论坛帖子列表和详情，关键字兴趣匹配
- 使用 HumanSession 人机浏览器模拟，避免反爬
- **API 端点**:
  - `GET /forum-reader` — 论坛推荐页面
  - `POST /api/forum-reader/browse` — 浏览指定论坛并抓取新帖
  - `POST /api/forum-reader/browse-all` — 浏览所有已配置论坛
  - `POST /api/forum-reader/recommend` — AI 推荐筛选
  - `PATCH /api/forum-reader/read/<rid>` — 标记已读
  - `POST /api/forum-reader/refresh-content/<rid>` — 刷新推荐内容

### 3.21 登录器插件

| 登录器 | 文件 | 平台 | 说明 |
|--------|------|------|------|
| 闲鱼登录器 | `plugins/xianyu_login.py` | 淘宝 SSO | Playwright → goofish.com → 淘宝 SSO，频率控制 3次/分钟 |
| 阿莫论坛登录器 | `plugins/amobbs_login.py` | Discuz! amobbs | "我不是机器人"复选框验证码处理 |
| 通用 Discuz 登录器 | `plugins/generic_login.py` | Discuz! 系列 | 通用密码/QR/Cookie 登录 |
| OSHWHub 登录器 | `plugins/oshwhub_login.py` | OSHWHub | passport.jlc.com 统一登录 |
| Bilibili 登录器 | `plugins/bilibili_login.py` | Bilibili | B站 Cookie/QR 登录 |
| 通用浏览器登录 | `routes/browser_login.py` | 多平台 | 通用 Discuz 系 + Amobbs Playwright 登录(299行) |
| 验证码浏览器登录 | `routes/captcha_browser.py` | Discuz! | 验证码获取/QR 扫码/登录流程(329行) |
| 通用 Playwright 登录 | `routes/captcha_browser.py` | 通用 | 通用通用登录/QR/验证码/密码/进度条/5步流程 |

### 3.22 浏览器引擎 (`core/browser_engine.py` + `routes/browser_engine.py`)

- **常驻 Playwright 浏览器引擎**: 全局单例 BrowserEngine，不反复 launch/close
- **线程安全**: 通过 `threading.Lock` 保护状态读写，10 分钟无活动自动关闭
- **状态常量**: stopped / starting / ready / restarting / error
- **默认配置**: chromium / headless / 1280×800 / locale zh-CN / 10min auto-close
- **关键方法**: `get_instance()`, `start()`, `stop()`, `restart()`, `get_page()`, `close_tab()`
- **API 端点**:
  - `POST /api/browser/start` — 启动浏览器
  - `POST /api/browser/stop` — 停止浏览器
  - `POST /api/browser/restart` — 重启浏览器
  - `GET /api/browser/status` — 获取状态
  - `POST /api/browser/keepalive` — 标记活动（心跳）
  - `GET /api/browser/config` — 获取配置
  - `POST /api/browser/config` — 更新配置
- **全局上下文注入**: 所有模板自动获取 `pw_status` / `pw_badge_class` / `pw_badge_text` / `pw_tabs_count`

### 3.23 外部服务模块 (`routes/external_services.py`)

- **功能说明**: 管理外部服务（如 xianyu-auto-reply）的管理入口链接和状态监控
- **注册机制**: `register_service()` 动态注册
- **已注册服务**:
  - xianyu-auto-reply（闲鱼自动回复 Docker 容器）：`XY_AUTO_REPLY_URL` / `XY_AUTO_REPLY_FRONTEND`
- **API 端点**:
  - `GET /api/external-services` — 获取所有已注册服务及其健康状态

---

## 四、工作流说明

### 4.1 账号添加工作流
```
选择平台 → 弹窗 → 选择登录方式(密码/QR/Cookie/手机验证码) →
QR扫码/密码验证 → Playwright 浏览器自动登录 →
Cookie 自动捕获 → 配置加密(encrypt_config) → 保存到 platform_accounts
```

### 4.2 文章发布工作流
```
采集(论坛/手动/AI/Provider) → 编译(MD→IR→平台格式) →
预览(HTML渲染) → 存草稿 → 发布(调用 Publisher.publish()) →
记录到 publish_log → 通知推送(notify)
```

### 4.3 签到工作流
```
调度器每分钟检查 → 获取启用的签到配置 →
forum_signin 动态导入 signin_*.py 插件 →
检查今日签到窗口(±30min随机化) → 检测是否已签到 →
匹配 SigninBase 插件 → Playwright 执行签到 →
记录到 signin_log → 通知结果
```

### 4.4 通知推送工作流
```
系统事件(发布/签到/价格变化/审批) → notify() →
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
检查 explore_cooldown(每小时限流，双缓存内存+DB) →
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
| `/api/accounts/batch/status` | POST | 批量刷新状态 | login_required |
| `/api/accounts/batch/publish` | POST | 批量发布 | login_required |
| `/api/accounts/batch/delete` | POST | 批量删除 | login_required |

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
| `/api/discuz/captcha` | POST | 获取 Discuz! 验证码 |
| `/api/discuz/login` | POST | Discuz! 登录提交 |
| `/api/universal/login/start` | POST | 通用登录启动(5步进度条) |
| `/api/universal/login/captcha` | POST | 通用验证码输入 |
| `/api/universal/login/status` | GET | 通用登录状态 |

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
| `/ai` | GET | AI 设置页面 |
| `/ai/logs` | GET | AI 调用日志页面 |
| `/api/ai/providers` | GET | 列出所有 Provider |
| `/api/ai/config` | GET | AI 路由配置 |
| `/api/ai/config` | POST | 更新配置 |
| `/api/ai/generate` | POST | AI 生成 |
| `/api/ai/models` | POST | 获取模型列表（API Key 探针） |
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
| `/api/exploration/explore/<domain>` | POST | 探索指定域名 |
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
| `/api/comment-monitor/reply/regen/<reply_id>` | POST | 重新生成回复 |
| `/api/comment-monitor/config/<account_id>` | PUT | 更新监控配置 |
| `/api/comment-monitor/reply/<reply_id>/mark-read` | PUT | 标记已读 |

### 6.11 浏览器引擎 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/browser/start` | POST | 启动浏览器引擎 |
| `/api/browser/stop` | POST | 停止浏览器引擎 |
| `/api/browser/restart` | POST | 重启浏览器引擎 |
| `/api/browser/status` | GET | 浏览器引擎状态 |
| `/api/browser/keepalive` | POST | 浏览器心跳保活 |
| `/api/browser/config` | GET | 获取浏览器配置 |
| `/api/browser/config` | POST | 更新浏览器配置 |

### 6.12 Gateway API v2 (外部接口)
| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/api/v2/system/status` | GET | 系统状态 | 无需 |
| `/api/v2/system/restart` | POST | 重启服务 | login_required |
| `/api/v2/system/reload` | POST | 重载配置 | login_required |

### 6.13 其他 API
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/xianyu/search` | POST | 闲鱼商品搜索 |
| `/api/platforms/presets` | GET | 平台预设配置 |
| `/api/external-services` | GET | 外部服务列表及状态 |
| `/api/storage/config` | POST | 更新存储后端配置 |
| `/api/storage/test` | POST | 测试存储连接 |
| `/api/deployer/add` | POST | 添加部署配置 |
| `/api/deployer/<id>/run` | POST | 执行部署 |
| `/api/deployer/logs` | GET | 部署日志 |
| `/api/forum-reader/browse` | POST | 浏览论坛抓取新帖 |
| `/api/forum-reader/browse-all` | POST | 浏览所有已配置论坛 |
| `/api/forum-reader/recommend` | POST | AI 推荐筛选 |
| `/api/forum-reader/read/<rid>` | PATCH | 标记推荐已读 |

---

## 七、数据库结构

### 7.1 `users`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 用户 ID |
| username | TEXT UNIQUE | 用户名 |
| password_hash | TEXT | bcrypt 密码哈希 |
| email | TEXT | 邮箱 |
| phone | TEXT | 手机号 |
| is_admin | INTEGER | 是否管理员 |
| twofa_type | TEXT | 二步验证类型 |
| twofa_secret | TEXT | 二步验证密钥 |
| created_at | TEXT | 创建时间 |
| last_login | TEXT | 最后登录时间 |

### 7.2 `platform_accounts`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 账号 ID |
| user_id | INTEGER FK | 所属用户 |
| platform | TEXT | 平台标识 (discuz/csdn/zhihu/...) |
| account_name | TEXT | 账号别名 |
| config_json | TEXT | 加密后的 JSON 配置 |
| is_active | INTEGER | 是否启用 (0/1) |
| status | TEXT | 登录状态 |
| keep_alive | INTEGER | 保持在线 |
| last_status_check | TEXT | 最后状态检测时间 |
| sort_order | INTEGER | 排序权重（探索页用） |
| created_at | TEXT | 创建时间 |

### 7.3 `articles`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 文章 ID |
| user_id | INTEGER FK | 所属用户 |
| title | TEXT | 标题 |
| body | TEXT | Markdown 正文 |
| summary | TEXT | 摘要 |
| tags | TEXT | JSON 标签数组 |
| source | TEXT | 来源 ('manual' 等) |
| status | TEXT | draft/published/archived |
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
| error | TEXT | 错误信息 |
| created_at | TEXT | 创建时间 |

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
| updated_at | TEXT | 更新时间 |

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
| tags_of_interest | TEXT | JSON 关心标签数组 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |
| UNIQUE | (platform_domain, section_id) | |

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
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 用户ID |
| title | TEXT | 标题 |
| message | TEXT | 内容 |
| level | TEXT | 级别 (info/warning/error) |
| source | TEXT | 来源 |
| link | TEXT | 点击跳转链接 |
| is_read | INTEGER | 是否已读 0/1 |
| created_at | TEXT | 创建时间 |

### 7.13 `ai_call_log`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| capability | TEXT | 能力类型 (writing/translate/image_gen等) |
| provider | TEXT | AI Provider 名称 |
| model | TEXT | 使用的模型名 |
| prompt_tokens | INTEGER | 输入token数 |
| response_tokens | INTEGER | 输出token数 |
| cost | REAL | 费用 |
| success | INTEGER | 是否成功 0/1 |
| error | TEXT | 错误信息 |
| response_summary | TEXT | 响应摘要（前200字） |
| prompt_preview | TEXT | 提示词预览（前200字） |
| created_at | TEXT | 创建时间 |

### 7.14 `deployer_configs`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 用户ID |
| deployer_name | TEXT | 部署器类型 (github_pages等) |
| display_name | TEXT | 显示名称 |
| config_json | TEXT | JSON配置 |
| is_active | INTEGER | 是否启用 0/1 |
| created_at | TEXT | 创建时间 |

### 7.15 `deploy_log`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| config_id | INTEGER FK | 部署配置ID |
| deployer_name | TEXT | 部署器类型 |
| success | INTEGER | 是否成功 |
| url | TEXT | 部署URL |
| error | TEXT | 错误信息 |
| message | TEXT | 额外消息 |
| created_at | TEXT | 创建时间 |

### 7.16 `comment_replies`
| 字段 | 类型 | 说明 |
|------|------|------|
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

### 7.17 `comment_monitor_config`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| account_id | INTEGER FK UNIQUE | 账号ID |
| enabled | INTEGER | 是否启用 |
| slot_morning | TEXT | 早间时段 (默认 12:00-12:30) |
| slot_afternoon | TEXT | 下午时段 (默认 15:00-15:30) |
| slot_evening | TEXT | 晚间时段 (默认 20:00-20:30) |
| auto_reply | INTEGER | 是否自动回复 |

### 7.18 `ai_configs`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 用户ID |
| provider | TEXT | AI 供应商 (deepseek/openai等) |
| alias | TEXT | 别名 |
| api_key | TEXT | API 密钥 |
| api_base | TEXT | API 地址 |
| api_format | TEXT | API 格式 (openai) |
| models | TEXT | JSON 模型列表 |
| status | TEXT | untested/valid/invalid |
| balance | TEXT | 余额缓存 |
| enabled | INTEGER | 是否启用 0/1 |
| created_at | TEXT | 创建时间 |
| UNIQUE | (user_id, provider, alias) | |

### 7.19 `site_configs`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 用户ID |
| deployer_id | INTEGER FK | 部署器ID |
| platform | TEXT | 平台 (github_pages) |
| comment_system | TEXT | 评论系统 |
| comment_config | TEXT | 评论配置 JSON |
| plugins_config | TEXT | 插件配置 JSON |
| extra_config | TEXT | 额外配置 JSON |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### 7.20 `provider_config`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 用户ID |
| provider_type | TEXT | Provider 类型 (markdown/notion) |
| config_json | TEXT | JSON配置 |
| updated_at | TEXT | 更新时间 |

### 7.21 `platform_config`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| platform | TEXT | 平台标识 |
| platform_domain | TEXT | 域名 |
| config_json | TEXT | JSON配置（平台能力等） |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |
| UNIQUE | (platform, platform_domain) | |

### 7.22 `playwright_config`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 固定为 1 |
| config_json | TEXT | JSON配置（浏览器引擎参数） |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### 7.23 `compiled_cache`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| article_id | INTEGER FK | 文章ID |
| platform | TEXT | 平台标识 |
| title | TEXT | 编译后标题 |
| body | TEXT | 编译后正文 |
| rendered_html | TEXT | 渲染后的 HTML |
| warnings | TEXT | 编译警告 |
| source_hash | TEXT | 源文章哈希（变更检测） |
| created_at | TEXT | 创建时间 |

### 7.24 `forum_recommendations`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 用户ID |
| platform | TEXT | 平台 |
| forum_name | TEXT | 论坛名 |
| title | TEXT | 帖子标题 |
| url | TEXT | 帖子链接 |
| tid | TEXT | 帖子TID |
| fid | TEXT | 版块ID |
| author | TEXT | 作者 |
| content | TEXT | 内容 |
| tags | TEXT | JSON标签 |
| score | INTEGER | AI推荐分数 |
| summary | TEXT | AI摘要 |
| source | TEXT | 来源 (keyword/browse) |
| is_read | INTEGER | 是否已读 |
| is_my_thread | INTEGER | 是否自己的帖子 |
| reply_author | TEXT | 回复作者 |
| reply_content | TEXT | 回复内容 |
| created_at | TEXT | 创建时间 |

### 其他表
- `verify_codes` — 短信验证码 / 找回密码
- `api_keys` — API Key 管理 (user_id/name/key_hash/key_prefix/is_active)
- `user_sessions` — 用户会话

---

## 八、配置说明

### 8.1 环境变量
| 变量 | 说明 |
|------|------|
| `FS_ENCRYPTION_KEY` | 覆盖 `.fs_key` 加密密钥 |
| `FS_SECRET_KEY` | Flask session secret |
| `FLASHSLOTH_SECRET` | Flask app secret key |
| `FLASHSLOTH_HOST` | 监听地址 (默认 0.0.0.0) |
| `FLASHSLOTH_PORT` | 监听端口 (默认 5000) |
| `FS_BOOT_USERNAME` | 首次启动默认用户名 |
| `FS_BOOT_PASSWORD` | 首次启动默认密码 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `XY_AUTO_REPLY_URL` | 闲鱼自动回复后端地址 |
| `XY_AUTO_REPLY_FRONTEND` | 闲鱼自动回复前端地址 |

### 8.2 密钥文件
- `~/.hermes/flashsloth/.fs_key` — Fernet 加密密钥（权限 600，自动生成）
- `flashsloth.db` — SQLite 主数据库（WAL 模式）
- `status_cache.db` — 状态缓存数据库

### 8.3 配置文件目录 (`config/`)
| 文件 | 说明 |
|------|------|
| `config/platform_csdn.json` | CSDN 平台预设 |
| `config/platform_mydigit.json` | 数码之家预设 |
| `config/platform_amobbs.json` | 阿莫论坛预设 |
| `config/platform_zhihu.json` | 知乎平台预设 |
| `config/ai_capabilities.json` | AI 供应商能力配置 |

### 8.4 内置配置文件
| 文件 | 说明 |
|------|------|
| `core/platform_presets.json` | 全局平台预设 |
| `core/provider_registry.json` | AI 供应商注册表预设 |

### 8.5 反检测配置（环境变量可覆盖）
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
| 评论监控 | `routes/comment_monitor.py` 定时器 | 按配置时段(早/中/晚) | 检查帖子新回复+AI自动回帖 |
| 外部服务健康检查 | `routes/external_services.py` | 按需调用 | 检查 Sidecar 等外部服务状态 |

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
15. **Cookie 数量判据禁止** — 不再以 Cookie 数量 >3 作为已登录判据，必须使用 Playwright 真实验证
16. **BrowserEngine 线程安全** — 所有引擎状态读取使用超时锁(3s)，避免引擎卡死阻塞所有页面

---

## 十一、版本历史

| 版本 | 日期 | 主要改动 |
|------|------|----------|
| **v4.80** | 2026-07-07 | **当前版本**。手机端排版优化：全页面响应式增强(768px+480px双断点)。ai_call_log 表 DDL 正式集成到 init_db()。Twitter/X Publisher 完善：登录能力描述文件/平台预设/图片提取优化。BrowserEngine threading double-release 修复。知乎/掘金 API 轻量登录状态检测器。文章列表批量删除/发布。 |
| v4.79 | 2026-07-07 | 闲鱼自动回复 Sidecar 适配器 + 状态检查脚本重写。Phone 登录方法为 discuz/oshwhub publisher 添加。平台硬编码全面修复 — DISCUZ_PLATFORMS 集合 + site_url 传透。账号弹窗增加验证码输入+5步进度条+Amobbs边框核验。 |
| v4.78 | 2026-07-07 | 登录状态深度验证 — 真实提取用户名/积分/等级 + 前端展示增强。GitHub Pages Deployer 默认路径改为 ~/.hermes/github-pages。账号页 UI 增强 — 搜索优化/平台颜色/快捷添加/时间标签/批量进度条。 |
| v4.77 | 2026-07-07 | Phone login 跨线程 bug 修复 — 每个请求创建独立 Playwright 实例。Provider 抽象框架整合到工作台 — base→workspace, 3 Providers, 配置管理。账号弹窗归一化深化 — 补齐 amobbs/discuz/mydigit/wordpress 登录能力。Signin time batch set + random offset (±30min) 配置。 |
| v4.76 | 2026-07-07 | 签到统计修复 — Bug A(手动签到计入统计) + Bug B(重复签到去重) + Bug C(状态持久化)。Twitter Publisher 完善 — 图片上传管道/Article兼容/草稿隔离/错误处理。知乎平台探索 — login/editor/capability data。 |
| v4.75 | 2026-07-07 | Playwright 验证迁移到子进程(避免WSGI死锁)。BrowserEngine 死锁修复 — Lock自死锁/超时锁/context_processor绕过。Cookie 数量判据反模式清除 — 严格执行铁律。OSHWHub签到Cookie过期自动fallback密码登录。 |
| v4.74 | 2026-07-07 | BrowserEngine 持久化 + accounts.py 重构为共享引擎。部署配置增强—账号页嵌入部署区块。签到统计去重+手动签到实时刷新+看门狗增强。Phone login 方法扩展到 CSDN/Bilibili。 |
| v4.73 | 2026-07-07 | BrowserEngine锁死导致已登录页面全部超时 — context_processor跳过get_status()。清理孤立pipeline_ui.py/pipeline.html。生产环境关闭模板热重载+BrowserEngine状态2秒缓存。登录页卡死修复。 |
| v4.72 | 2026-07-07 | WeChat Official Account 完整探索 + publisher image upload/cover/summary 增强。Playwright 作为唯一验证方式 + 强化检测逻辑。签到调度随机化—基于account_id确定偏移避免7账号同时签到。Bilibili 完整探索报告+登录插件+能力入库。 |
| v4.71 | 2026-07-07 | 账号状态检测强制Playwright真实验证，移除伪造cookie数量>3假已登录逻辑。AI调用日志系统完善。OSHWHub登录能力修复—passport.jlc.com正确URL。手机验证码登录—phone_login+SMS验证码。 |
| v4.70 | 2026-07-07 | 统一登录能力探索+动态渲染—7平台登录能力JSON+API+前端动态Tab。B站Publisher/Adapter增强—save_as_draft+upload_image。统一登录Cookie加密存储—三处加密补全。 |
| v4.69 | 2026-07-07 | 统一浏览器登录按钮—所有平台共用统一编辑弹窗登录流程。探索限流DB持久化—双缓存策略(内存+DB)。OSHWHub签到asyncio冲突修复。CSDN/wechat等通用登录适配。 |
| v4.68 | 2026-07-07 | 账号弹窗全面升级—QR扫码登录+演示说明卡+验证码交互优化。编辑弹窗统一改造—旧edit页面重定向到/accounts模态框。凭证加密存储—Fernet(AES-128)对称加密。 |
| v4.67 | 2026-07-07 | 网关QR扫码自动配置—新增/callback/start-callback/callback-result三个端点。GitHub Pages posts_dir更新为WSL路径。OSHWHub签到Playwright线程隔离+账号状态检测加强。 |
| v4.66 | 2026-07-07 | OSHWHub签到Cookie过期自动重新登录 + E2E存草稿验证通过。登录状态检测改用Playwright验证Cookie。 |
| v4.65 | 2026-07-07 | 签到统计修复(成功/失败分解)。OSHWHub封面ant-modal遮罩bug修复。 |
| v4.64 | 2026-07-07 | 通知网关20+Provider + 反检测中央模块 + 闲鱼V2 MTOP发布器 + Explorer防风重构 + 探索页UI大改。 |
| v4.63 | 2026-07-07 | AI路由管理页面 + 价格监控 + explorer重构 + 闲鱼导航条件显示 + 全局模板上下文。CSDN预设种子修复。探索管理AJAX分页加载板块。 |
| v4.62 | 2026-07-07 | 通知系统+Gateway通知网关+统一流水线+闲鱼搜索UI+探索页增强+数据库迁移。 |
| v4.0 | — | Gateway API 网关、统一流水线调度器、AI 路由框架 |
| v3.x | — | Discuz/CSDN/知乎/掘金/B站/OSHWHub 发布器、签到系统 |
| v2.x | — | 基础账号管理、文章 CRUD、多平台发布 |
| v1.0 | — | 初始化 Flask 应用、单平台发布 |

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
| `gateway.py` | 通知网关核心（Provider 注册表，1181行） |
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

### routes/ (24 个 Python 文件)
| 文件 | 行数 | 说明 |
|------|------|------|
| `__init__.py` | 93 | 路由中心 — 应用工厂，导入所有路由模块 |
| `_app.py` | 86 | Flask 共享实例 + Jinja2 过滤器 + 全局模板上下文 |
| `accounts.py` | 1484 | 账号管理 — CRUD/状态检测/加密/批量操作 |
| `ai.py` | 658 | AI 供应商管理/配置/生成/余额查询/日志 |
| `api_v1.py` | 532 | 统一 REST API v1（API Key 鉴权） |
| `api_v2.py` | 205 | Gateway REST API v2（系统/重启/重载） |
| `approval.py` | 144 | 审批流程管理 |
| `auth.py` | 309 | 认证 — 登录/注册/改密/2FA/短信/首页 |
| `browser_engine.py` | 187 | Playwright 浏览器引擎启停/状态/配置 |
| `browser_login.py` | 299 | 通用 Discuz 系 + Amobbs Playwright 登录 |
| `captcha_browser.py` | 329 | 验证码获取/QR扫码/通用全流程登录 |
| `comment_monitor.py` | 600 | 评论监控收件箱/AI自动回复/配置 |
| `exploration.py` | 589 | 论坛探索数据管理/平台能力展示 |
| `external_services.py` | 89 | 外部服务注册/健康检查 |
| `forum.py` | 253 | AI 逛论坛/推荐/浏览/回复 |
| `gateway.py` | 270 | 通知渠道 CRUD/测试发送 |
| `notifications.py` | 67 | 通知中心/列表/标记已读 |
| `platforms.py` | 19 | 平台预设配置 |
| `posts.py` | 849 | 文章 CRUD/发布/编译/自动编译 |
| `price_monitor.py` | 122 | 价格监控管理/刷新 |
| `signin.py` | 374 | 签到管理/手动签到/统计 |
| `storage_deploy.py` | 505 | 存储后端配置/部署器管理 |
| `workspace_ui.py` | 374 | 工作台/Provider选择/流水线/日志 |
| `xianyu_search.py` | 142 | 闲鱼商品搜索 |

### plugins/ (48 个 Python 文件)
**发布器 (15个)**:
| 文件 | 说明 |
|------|------|
| `publisher_discuz.py` | Discuz! 论坛发布器 |
| `publisher_csdn.py` | CSDN 发布器 |
| `publisher_zhihu.py` | 知乎发布器 |
| `publisher_juejin.py` | 掘金发布器 |
| `publisher_bilibili.py` | Bilibili 专栏发布器 |
| `publisher_oshwhub.py` | OSHWHub 发布器 |
| `publisher_xianyu.py` | 闲鱼 v1 发布器 |
| `publisher_xianyu_v2.py` | 闲鱼 V2 MTOP 发布器 |
| `publisher_xianyu_products.py` | 闲鱼商品发布(预留) |
| `publisher_xianyu_auto_reply.py` | 闲鱼自动回复 Sidecar |
| `publisher_xianyu_sidecar.py` | 闲鱼 Sidecar 适配器 |
| `publisher_twitter.py` | Twitter/X 发布器 |
| `publisher_wechat.py` | 微信公众号发布器 |
| `publisher_wordpress.py` | WordPress 发布器 |
| `publisher_rss.py` | RSS 发布器 |
| `publisher_github_pages.py` | GitHub Pages 博客发布器 |

**签到 (3个)**:
| 文件 | 说明 |
|------|------|
| `signin_discuz.py` | Discuz! 签到插件 |
| `signin_csdn.py` | CSDN 签到插件 |
| `signin_oshwhub.py` | OSHWHub 签到插件 |
| `forum_signin.py` | 论坛签到 Orchestrator |

**登录器 (5个)**:
| 文件 | 说明 |
|------|------|
| `xianyu_login.py` | 闲鱼淘宝 SSO 登录 |
| `amobbs_login.py` | 阿莫论坛登录器(复选框验证码) |
| `generic_login.py` | 通用 Discuz 系登录器 |
| `oshwhub_login.py` | OSHWHub 登录器 |
| `bilibili_login.py` | Bilibili 登录器 |

**Provider (3个)**:
| 文件 | 说明 |
|------|------|
| `provider_markdown.py` | Markdown 文件扫描 |
| `provider_notion.py` | Notion API 读取 |
| `provider_taobao.py` | 淘宝商品 Provider |

**工具 (5个)**:
| 文件 | 说明 |
|------|------|
| `deployer_github_pages.py` | GitHub Pages 部署器 |
| `storage_alist.py` | AList 存储后端 |
| `forum_reader.py` | AI 逛论坛读取器 |
| `reply_monitor.py` | 评论回复采集引擎 |
| `browser_session.py` | 浏览器会话管理 |

**MTOP 客户端包 (9个)**:
| 文件 | 说明 |
|------|------|
| `xianyu_client/__init__.py` | 包标记 |
| `xianyu_client/mtop.py` | MTOP API 调用 |
| `xianyu_client/sign.py` | 签名生成 |
| `xianyu_client/session.py` | Cookie 会话管理 |
| `xianyu_client/media.py` | 图片上传到闲鱼 CDN |
| `xianyu_client/category.py` | AI 类目推荐 |
| `xianyu_client/location.py` | 默认地址获取 |
| `xianyu_client/guard.py` | 风控监控 |
| `xianyu_client/limiter.py` | 频率限制(3次/分钟) |
| `xianyu_client/errors.py` | 错误类型定义 |

**旧 API 兼容 (4个)**:
| 文件 | 说明 |
|------|------|
| `xianyu/XianyuApis.py` | 闲鱼核心 API 层 |
| `xianyu/context_manager.py` | 闲鱼上下文管理 |
| `xianyu/utils/xianyu_utils.py` | 闲鱼工具函数 |
| `xianyu/utils/__init__.py` | 包标记 |

### sdk/adapters/ (16 个 Python 文件)
| 文件 | 说明 |
|------|------|
| `xianyu_v2.py` | 闲鱼 API v2 适配器（搜索/详情/比价） |
| `xianyu.py` | 闲鱼 PlatformAdapter（Playwright） |
| `bilibili.py` | B站适配器 |
| `csdn.py` | CSDN 适配器 |
| `zhihu.py` | 知乎适配器 |
| `juejin.py` | 掘金适配器 |
| `oshwhub.py` | OSHWHub 适配器 |
| `amobbs.py` | 阿莫论坛适配器 |
| `mydigit.py` | 数码之家适配器 |
| `wordpress.py` | WordPress 适配器 |
| `wechat.py` | 微信适配器 |
| `notion.py` | Notion 适配器 |
| `github_pages.py` | GitHub Pages 适配器 |
| `giscus.py` | Giscus 适配器 |

### templates/ (30 个 HTML 模板)
| 模板 | 说明 |
|------|------|
| `index.html` | 仪表盘总览 |
| `login.html` | 登录页 |
| `register.html` | 注册页 |
| `base.html` | 基础布局模板 |
| `accounts.html` | 账号管理 |
| `account_edit.html` | 账号编辑弹窗 |
| `signin.html` | 签到管理 |
| `gateway.html` | 通知网关配置 |
| `exploration.html` | 论坛探索管理 |
| `approval.html` | 审批管理 |
| `price_monitor.html` | 价格监控 |
| `ai_settings.html` | AI 设置 |
| `ai_logs.html` | AI 调用日志 |
| `publish_manage.html` | 发布管理 |
| `publish_select.html` | 发布目标选择 |
| `compile_preview.html` | 编译预览 |
| `preview.html` | 文章预览 |
| `edit.html` | 文章编辑 |
| `forum_reader.html` | 论坛阅读器(AI逛论坛) |
| `xianyu_search.html` | 闲鱼搜索 |
| `notifications.html` | 通知列表 |
| `workspace.html` | 工作台 |
| `settings.html` | 设置 |
| `storage_settings.html` | 存储设置 |
| `deployers.html` | 部署器配置 |
| `playwright_settings.html` | Playwright 浏览器设置 |
| `comment_monitor.html` | 评论监控 |
| `change_password.html` | 修改密码 |
| `forgot_password.html` | 忘记密码 |
| `verify_2fa.html` | 二步验证 |

### scripts/ (5 个 Python 脚本)
| 脚本 | 说明 |
|------|------|
| `hourly_forum_check.py` | 每小时增量检查论坛版块变更 |
| `sync_registry_keywords.py` | 同步 forum_registry 关键词到 DB |
| `consolidate_forum_data.py` | 合并 www 前缀数据到非 www 域名 |
| `playwright_verify.py` | 子进程 Playwright 账号登录验证 |
| `compare_forum_data.py` | 对比新旧论坛数据差异 |

---

*本文件由 AI 自动生成，以代码实际内容为准。*
*版本: v4.80 | 文件行数: 1421 行 | 最后更新: 2026-07-07*
