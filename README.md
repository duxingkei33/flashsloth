[🇨🇳 中文](README.md) | [🇬🇧 English](README_EN.md)

---

# 🦥 FlashSloth — 个人数字资产全聚合平台

> 树懒的速度，闪电的发布
> 一个后台管理你在互联网上的所有数字资产

---

## ✨ 功能特性

### 🔐 账号管理
- [x] 多平台账号统一管理（添加/编辑/删除/启用禁用）
- [x] 🔑 密码+验证码登录 — Playwright 浏览器自动处理
- [x] 📱 QR码扫码登录 — 远程浏览器截图+10秒轮询自动捕获Cookie
- [x] 📱 手机验证码登录 — phone_login + SMS验证码流程+前端支持
- [x] 🪪 统一登录能力探索 — 7平台Playwright真实检测(密码/QR/手机验证码)+JSON报告+动态Tab渲染
- [x] 🍪 Cookie粘贴（调试模式）
- [x] 🖼️ 登录方式演示说明卡（小程序风格步骤指引）
- [x] 🔒 凭证加密存储（Fernet AES-128-CBC + HMAC-SHA256）
- [x] 🔐 统一凭证体系 — ScanLoginEngine 统一扫码引擎 + save/get/verify_credential 三合一凭证操作
- [x] 🧪 统一Cookie验证器 — 消除4处散落cookie验证代码，统一 verify_cookie / verify_cookie_for_adapter 接口
- [x] 📊 三层状态检测系统 — 常驻BrowserEngine+API轻量检测+Playwright真实验证+三层缓存(内存/SQLite/实时)+批量刷新+深度用户信息
- [x] 🧩 统一浏览器登录按钮 — 所有平台共用统一编辑弹窗登录流程
- [x] 📱 手机验证码登录扩展到 CSDN/Bilibili 发布器
- [x] 🏗️ BrowserEngine 持久化重构 — 共享引擎+子进程Playwright验证（避免WSGI死锁）
- [x] 🪟 账号弹窗归一化深化 — 补齐 amobbs/discuz/mydigit/wordpress + 验证码输入+5步进度条+Amobbs边框核验
- [x] 🔍 登录状态深度验证 — 真实提取用户名/积分/等级 + 前端展示增强
- [x] 🎨 账号页UI增强 — 搜索优化/平台颜色标签/快捷添加/时间标签/批量进度条
- [x] 🛡️ Cookie验证严格模式 — DiscuzPublisher严格登录态检测(退出按钮+2指示器) + test-connection Playwright子进程降级消除假阳性

### 📝 多平台发布
- [x] Discuz! 论坛（amobbs/mydigit 等）— 发帖+存草稿+签到
- [x] WordPress — REST API 发布（App Password 认证）
- [x] 微信公众号 — 官方API存草稿（AppID + AppSecret）+ 探索+图片上传/封面/摘要
- [x] CSDN — Playwright 发布+签到
- [x] 知乎 — Playwright 全面重写（密码/QR/Cookie）+ 平台探索报告
- [x] OSHWHub 立创开源硬件 — Playwright 发布+签到
- [x] 掘金 — Cookie模拟发布（密码/QR/Cookie）
- [x] Bilibili 专栏 — Playwright 发布+存草稿+图片上传+登录插件+探索报告（密码/QR/Cookie）
- [x] Twitter/X — tweepy API v2 OAuth1.0a + 完善登录能力描述/平台预设/图片提取优化 + 草稿隔离
- [x] 闲鱼商品发布 — MTOP签名V2 + AI类目推荐 + xianyu_client SDK
- [x] 闲鱼自动回复系统集成 — Docker 服务对接（商品发布/订单查询）
- [x] 闲鱼自动回复 Sidecar 适配器 — xianyu-auto-reply REST API 对接+健康监控
- [x] Gallery 抽按商品发布（预留）
- [x] RSS订阅 — 纯Python生成
- [x] GitHub Pages — git push 部署
- [x] 🕐 发布前Cookie过期预检 — Publisher基类check_cookie() + publish_select前端Cookie状态展示（✅/❌指标）
- [x] 📋 文章列表多选批量删除/发布

### 🔔 通知网关
- [x] 22 通知渠道（Telegram/Discord/Slack/WhatsApp/钉钉/企微/飞书/微信/邮件/Matrix/Teams/LINE 等）
- [x] QR扫码自动配置 — /callback 端点
- [x] 消息队列+Provider注册表
- [x] 批量测试/单渠道测试

### 🔍 平台探索
- [x] Discuz 版块自动探索（Playwright）
- [x] 登录能力探索 — 7平台密码/QR/手机验证码自动检测+JSON报告
- [x] 每小时增量轮询 + 防风限流（双缓存内存+DB持久化跨进程共享）
- [x] 版块关键词匹配 + 探索数据管理页面
- [x] 平台发布能力展示 + 标签栏目管理
- [x] Bilibili 完整探索报告+登录插件+平台能力入库
- [x] 知乎平台探索 — login/editor/capability 数据
- [x] 微信公众号探索 — 图片上传/封面/摘要能力
- [x] WeChat 公众号完整探索 + 发布器增强
- [x] 🤖 知乎/掘金 API轻量登录状态检测器
- [x] 📡 探索雷达 v2 — 得物/什么值得买/小红书完整探索报告 + category分类字段
- [x] 🆕 新平台探索: 51CTO（WAF检测+SMS-only登录评估）+ 豆瓣探索报告
- [x] 📚 论坛注册表双轨读取 — JSON+DB双轨支撑，FORUM_REGISTRY_MODE=auto/db/json三模式

### 👨‍👩‍👧‍👦 自动签到
- [x] OSHWHub 签到（含Cookie过期自动重登+asyncio隔离修复）
- [x] CSDN 签到
- [x] amobbs / Discuz! 签到
- [x] 签到统计（成功/失败分解，去重修复）
- [x] 签到时间批量设置 + 随机偏移（±30分钟）配置
- [x] 签到时间随机化（1小时窗口内随机执行，基于account_id偏移避免同时签到）

### 🛒 闲鱼集成
- [x] 商品搜索（关键词/价格范围/排序/分页）
- [x] 价格监控与比价（LCSC 元器件）
- [x] MTOP签名V2发布器 + AI类目识别
- [x] xianyu_client SDK（mtop/sign/session/media/category/limiter/guard）
- [x] 闲鱼自动回复系统 — Docker 服务集成+API代理+健康状态监控

### 🧠 智能匹配
- [x] AI版块匹配（支持多平台）
- [x] 关键词库同步
- [x] AI 供应商动态管理（21+ 供应商，余额查询，测试连接）

### 📋 审批流程
- [x] 审批请求创建/通过/拒绝/取消
- [x] Webhook 端点（文本命令如「通过 123」）
- [x] 网关通知广播 + 审批历史查询

### 📚 统一流水线
- [x] 三大模块共享工作流引擎（Collect→Compile→Preview→Draft→Publish）
- [x] 可视化流水线流程图
- [x] 运行历史列表

### 🧰 工作台 & Provider 框架
- [x] 统一内容管理工作台 — Provider选择+流水线+内容日志
- [x] Provider 抽象框架 — base→workspace, 3 Providers (Markdown/Notion/淘宝), 配置管理
- [x] AI 调用日志系统 — 自动记录+可视化日志页面+分页筛选
- [x] 📋 统一日志管理 — 发布/签到/AI/部署日志统一查看+分页+实时筛选
- [x] 🖥️ Playwright 浏览器引擎设置页面
- [x] 🖥️ BrowserEngine 空闲自动关闭 — 60秒轮询监控线程，闲置超时自动回收浏览器实例
- [x] 外部服务注册表 — 统一管理 xianyu-auto-reply 等服务
- [x] 部署配置增强 — 账号页嵌入部署区块+deployers增强版

### 💬 评论监控
- [x] 多论坛评论监控 — 未读/回复/统计数据看板
- [x] 评论通知推送

### 📱 移动端支持
- [x] 📱 全页面响应式增强 — 375px iPhone 视口零水平溢出，触摸友好按钮/弹窗/导航/卡片网格
- [x] 移动端 CSS 增强 — 响应式布局适配手机/平板

---

## 🏗️ 项目架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    用户界面层 (Flask Web UI)                       │
│  仪表盘 · 文章管理 · 签到管理 · 闲鱼搜索 · 账号管理               │
│  配置中心 · 探索数据 · 通知网关 · 审批管理 · AI 配置              │
│  工作台 · AI调用日志 · Playwright设置 · 评论监控                  │
│  部署配置 · 外部服务 · 存储设置                                   │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                   Gateway API 层 (routes/)                        │
│  routes/accounts.py · gateway.py · ai.py · signin.py             │
│  exploration.py · posts.py · api_v2.py · browser_login.py        │
│  approval.py · notifications.py · price_monitor.py               │
│  workspace_ui.py · browser_engine.py · external_services.py      │
│  storage_deploy.py · auth.py                                      │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                   统一工作流引擎 (core/)                            │
│  publisher · gateway · scheduler · database · credential_crypto   │
│  anti_detect · explorer · price_monitor · approval · notifier     │
│  ai_provider · article · deployer · compiler · pipeline           │
│  signin · image_pipeline · captcha_handler                        │
│  browser_engine · status_detector · status_cache · provider       │
│  provider_registry · storage · cookie_validator · forum_registry   │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                    发布器 + 适配器层 (plugins/ + sdk/)             │
│  publisher_*.py — 16 个平台发布器                                 │
│  signin_*.py   — 3 个签到插件                                    │
│  provider_*.py — 3 个 Provider 插件 (Markdown/Notion/淘宝)       │
│  generic_login.py · bilibili_login.py · xianyu_client/           │
│  sdk/adapters/ (14 平台适配器)                                   │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                   公共基础设施层                                    │
│  SQLite (flashsloth.db + status_cache.db)                        │
│  .fs_key 加密密钥 · config/ · templates/ · static/               │
│  platform_reports/ (51+ 登录能力/探索报告)                         │
│  scripts/ · DEVELOPMENT_SPECIFICATION.md · ARCHITECTURE.md       │
└──────────────────────────────────────────────────────────────────┘
```

> 详细架构请参阅 [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Git
- （可选）Playwright（浏览器自动化登录需要）
- （可选）Cloudflare Tunnel / frpc 用于外网访问

### 安装与启动

```bash
# 1. 克隆仓库
git clone https://github.com/duxingkei33/flashsloth.git
cd flashsloth

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright（用于浏览器自动登录）
pip install playwright
python -m playwright install chromium

# 4. 启动（会自动初始化数据库和随机管理员账号）
python admin.py

# 5. 看到终端输出类似以下内容，即表示启动成功：
# ======================================================
#   🦥 FlashSloth — 树懒的速度，闪电的发布
#   🌐 http://0.0.0.0:5000
#   👤 首次启动，自动生成了管理员账号：
#      用户名: admin_a1b2c3
#      密码:   Xy7kPq9mR2vL4nW8
#   ⚠️  请尽快登录后台修改密码！
# ======================================================

# 6. 打开浏览器访问 http://localhost:5000 即可管理
```

> **⚠️ 生产环境建议：**
> - 设置环境变量 `FLASHSLOTH_SECRET` 固定 Secret Key
> - 设置 `FS_ENCRYPTION_KEY` 固定加密密钥
> - 使用 Nginx + Gunicorn 反向代理

### 外网访问

```bash
# 使用 frpc 或 Cloudflare Tunnel 将本地 5000 端口映射到外网
frpc -c frpc.toml
```

---

## ⚙️ 配置

### 环境变量

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `FLASHSLOTH_SECRET` | 自动生成 | 建议 | Flask 密钥，生产环境建议固定 |
| `FS_ENCRYPTION_KEY` | 自动生成 | 建议 | Fernet 加密密钥，缺失时从 .fs_key 读取 |
| `FLASHSLOTH_HOST` | `0.0.0.0` | 否 | 监听地址 |
| `FLASHSLOTH_PORT` | `5000` | 否 | 监听端口 |

### 密钥文件

- `.fs_key` — Fernet 凭证加密密钥（权限 600），首次启动自动生成

---

## 📊 定时任务

| 任务 | 周期 | 说明 |
|------|------|------|
| 自动签到 | 每分钟检查 | 守护线程在签到时间窗口内随机执行，基于account_id偏移避免同时签到 |
| 论坛探索 | 每小时 | `scripts/hourly_forum_check.py` 增量检查 Discuz 版块变更 |
| 价格刷新 | 按配置 | LCSC 元器件价格定时刷新 |

---

## 📋 版本历史

| 版本 | 日期 | 主要改动 |
|------|------|----------|
| v5.07 | 2026-07-08 | Cookie验证严格模式 — Discuz login假阳性修复 + test-connection Playwright子进程降级 + 版块注册表双轨验证 + 探索报告更新 |
| v5.05 | 2026-07-08 | 51CTO平台探索 — WAF+SMS-only评估 + 探索雷达v2（得物/什么值得买/小红书）+ category分类字段 |
| v5.04 | 2026-07-08 | 发布前Cookie过期预检 — Publisher基类check_cookie() + publish_select前端状态展示 |
| v5.03 | 2026-07-08 | 账号弹窗归一化收尾 — 移除旧版平台专属登录弹窗(amobbs/xianyu/oshwhub) |
| v5.02 | 2026-07-08 | Cookie验证器统一 — verify_credential/get/save三合一 + OSHWHub迁移 + 关键词假阳性修复 |
| v4.93 | 2026-07-08 | 扫码登录全流程优化 — 多方式选择+超时机制+账号弹窗QR优化 |
| v4.92 | 2026-07-08 | 统一凭证体系 — ScanLoginEngine + save/get/verify_credential + QR引擎重构 |
| v4.91 | 2026-07-07 | QR码登录全平台优先级#1 + site_url传透修复 + BrowserEngine自动回收 + 统一日志管理页面 |
| v4.90 | 2026-07-07 | 统一日志管理（发布/签到/AI/部署）+ 适配器架构修复 + 复合搜索下拉框 |
| v4.80 | 2026-07-07 | 手机端排版优化 — 全页面响应式增强（375px零溢出、触摸友好按钮/弹窗/导航/卡片网格） |
| v4.79 | 2026-07-07 | 登录状态深度验证 — 真实提取用户名/积分/等级 + 前端展示增强 |
| v4.78 | 2026-07-07 | 账号页UI增强（搜索优化/平台颜色/快捷添加/时间标签/批量进度条）+ 文章列表多选批量操作 + 知乎/掘金API轻量状态检测 + 闲鱼Sidecar适配器 |
| v4.77 | 2026-07-07 | 账号弹窗验证码输入+5步进度条+Amobbs边框核验 + Twitter/X登录能力完善 + ai_call_log修复 |
| v4.76 | 2026-07-07 | BrowserEngine线程安全修复 + QR码后台线程 + signin注册器分裂修复 |
| v4.75 | 2026-07-07 | 账号弹窗归一化深化 — 补齐 amobbs/discuz/mydigit/wordpress 登录能力 |
| v4.74 | 2026-07-07 | Provider抽象框架整合到工作台 — base→workspace, 3 Providers, 配置管理 + 移动端CSS优化 |
| v4.70 | 2026-07-07 | 签到统计修复 — 手动签到计入+重复签到去重+状态持久化 |
| v4.67 | 2026-07-07 | Twitter Publisher 完善 — 图片上传管道/Article兼容/草稿隔离/错误处理 |
| v4.66 | 2026-07-07 | 知乎平台探索 — login/editor/capability 数据 |
| v4.65 | 2026-07-07 | Playwright验证迁移子进程(避免WSGI死锁) + 签到时间批量设置+随机偏移 |
| v4.64 | 2026-07-07 | BrowserEngine 自死锁修复 — context_processor 超时锁解耦 |
| v4.63 | 2026-07-07 | Cookie数量判据反模式清除 |
| v4.62 | 2026-07-07 | OSHWHub签到Cookie过期自动fallback密码登录 + CSDN签到修复 |
| v4.60 | 2026-07-07 | BrowserEngine持久化 + accounts.py重构 + Phone login线程修复 |
| v4.59 | 2026-07-07 | 手机验证码登录扩展到 CSDN/Bilibili 发布器 |
| v4.58 | 2026-07-07 | 生产环境性能优化 — 模板热重载关闭 + BrowserEngine 2秒缓存 |
| v4.57 | 2026-07-07 | 三层状态检测系统 — BrowserEngine常驻+API轻量+Playwright验证+缓存+深度用户信息 |
| v4.56 | 2026-07-07 | Bilibili完整探索报告+登录插件+平台能力入库 + 微信公众号探索/发布器增强 |
| v4.55 | 2026-07-07 | AI调用日志系统+工作台+手机验证码+统一登录能力探索+Playwright设置+移动端CSS |

---

## 📄 许可

请参阅 [LICENSE](LICENSE) 文件。

FlashSloth 采用 **双许可模式**：

| 使用场景 | 许可类型 |
|---------|---------|
| 🆓 个人学习、教育、研究 | AGPL-3.0（免费） |
| 🆓 非营利组织、开源项目 | AGPL-3.0（免费） |
| 💼 企业商业使用 | **需要商业许可**（请联系作者） |

商业许可请联系：**277563381@qq.com**
