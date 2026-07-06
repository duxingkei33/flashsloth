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
- [x] 🍪 Cookie粘贴（调试模式）
- [x] 🖼️ 登录方式演示说明卡（小程序风格步骤指引）
- [x] 🔒 凭证加密存储（Fernet AES-128-CBC + HMAC-SHA256）
- [x] 📊 账号状态实时检测（Playwright验证登录态）

### 📝 多平台发布
- [x] Discuz! 论坛（amobbs/mydigit 等）— 发帖+存草稿+签到
- [x] WordPress — REST API 发布（App Password 认证）
- [x] 微信公众号 — 官方API存草稿（AppID + AppSecret）
- [x] CSDN — Playwright 发布+签到
- [x] 知乎 — Playwright 全面重写（密码/QR/Cookie）
- [x] OSHWHub 立创开源硬件 — Playwright 发布+签到
- [x] 掘金 — Cookie模拟发布（密码/QR/Cookie）
- [x] Bilibili 专栏 — Playwright 发布（密码/QR/Cookie）
- [x] Twitter/X — tweepy API v2 OAuth1.0a
- [x] 闲鱼商品发布 — MTOP签名V2 + AI类目推荐
- [x] 闲鱼商品发布（预留）
- [x] RSS订阅 — 纯Python生成
- [x] GitHub Pages — git push 部署

### 🔔 通知网关
- [x] 23 通知渠道（飞书/钉钉/企微/微信/Telegram/Discord/Slack 等）
- [x] QR扫码自动配置 — /callback 端点
- [x] 消息队列+Provider注册表
- [x] 批量测试/单渠道测试

### 🔍 平台探索
- [x] Discuz 版块自动探索（Playwright）
- [x] 每小时增量轮询
- [x] 防风限流（每域名1次/小时，双缓存持久化）
- [x] 版块关键词匹配
- [x] 探索数据管理页面

### 👨‍👩‍👧‍👦 自动签到
- [x] OSHWHub 签到（含Cookie过期自动重登）
- [x] CSDN 签到
- [x] amobbs / Discuz! 签到
- [x] 签到统计（成功/失败分解）
- [x] 签到时间随机化（1小时窗口内随机执行）

### 🛒 闲鱼集成
- [x] 商品搜索（关键词/价格范围/排序/分页）
- [x] 价格监控与比价（LCSC 元器件）
- [x] MTOP签名V2发布器
- [x] xianyu_client SDK（mtop/sign/session/media/category/limiter/guard）

### 🧠 智能匹配
- [x] AI版块匹配（支持多平台）
- [x] 关键词库同步
- [x] AI 供应商动态管理（21+ 供应商，余额查询，测试连接）

---

## 🏗️ 项目架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    用户界面层 (Flask Web UI)                       │
│  仪表盘 · 文章管理 · 签到管理 · 闲鱼搜索 · 账号管理               │
│  配置中心 · 探索数据 · 通知网关 · 审批管理 · AI 配置              │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   Gateway API 层 (routes/)                        │
│  routes/accounts.py · gateway.py · ai.py · signin.py             │
│  exploration.py · posts.py · api_v2.py · browser_login.py        │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   统一工作流引擎 (core/)                            │
│  publisher · gateway · scheduler · database · credential_crypto   │
│  anti_detect · explorer · price_monitor · approval · notifier     │
│  ai_provider · article · deployer · compiler · pipeline           │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                    发布器 + 适配器层 (plugins/ + sdk/)             │
│  publisher_*.py — 14 个平台发布器                                 │
│  signin_*.py   — 3 个签到插件                                    │
│  generic_login.py · xianyu_client/ · sdk/adapters/               │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                   公共基础设施层                                    │
│  SQLite (flashsloth.db) · .fs_key 加密密钥 · config/ · templates/│
│  static/ · platform_reports/ · scripts/hourly_forum_check.py      │
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
| 自动签到 | 每分钟检查 | 守护线程在签到时间窗口（默认 08:00-09:00）内随机执行 |
| 论坛探索 | 每小时 | `scripts/hourly_forum_check.py` 增量检查 Discuz 版块变更 |
| 价格刷新 | 按配置 | LCSC 元器件价格定时刷新 |

---

## 📋 版本历史

| 版本 | 日期 | 主要改动 |
|------|------|----------|
| v4.50 | 2026-07-07 | 演示示意图+CSDN/wechat/zhihu等通用登录适配 |
| v4.49 | 2026-07-07 | 账号弹窗全面升级—QR扫码登录+演示说明卡+验证码交互优化 |
| v4.48 | 2026-07-06 | 编辑弹窗统一改造—旧edit页面重定向到/accounts，掩码值保存 |
| v4.47 | 2026-07-06 | 修复test_connection解密兼容+config_json读路径加解密 |
| v4.46 | 2026-07-06 | 凭证加密存储—Fernet AES-128对称加密密码/Cookie/Token |
| v4.45 | 2026-07-06 | 网关QR扫码自动配置—/callback端点 |
| v4.42 | 2026-07-06 | OSHWHub签到Cookie过期自动重新登录+E2E存草稿 |
| v4.41 | 2026-07-06 | OSHWHub账号登录状态检测修复—Playwright验证Cookie |
| v4.39 | 2026-07-06 | 通知网关23 Provider+反检测中央模块+闲鱼V2 MTOP+Explorer防风重构 |
| v4.36 | 2026-07-06 | 通知系统+Gateway网关+统一流水线+闲鱼搜索UI+探索页增强 |
| v4.35 | 2026-07-06 | Twitter/X Publisher+探索页动态排序 |
| v4.33 | 2026-07-06 | 知乎发布器全面改进+探索页UI增强+签到统计修复 |

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
