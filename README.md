[🇨🇳 中文](README.md) | [🇬🇧 English](README_EN.md)

---

# 🦥 FlashSloth

**树懒的速度，闪电的发布**

FlashSloth（树懒）是一款开源多平台内容发布与站点部署系统。一次编写 Markdown，一键发布到多个内容平台，或部署为静态站点。

## ✨ 特性

| 功能 | 说明 |
|------|------|
| **📝 文章管理** | Markdown 编辑器，实时预览，标签管理，草稿/发布状态 |
| **📡 多平台发布** | 支持 15+ 平台：Discuz! 论坛、WordPress、微信公众号、掘金、知乎、CSDN、RSS、GitHub Pages、闲鱼、立创开源硬件、B站（预留）、自定义平台 |
| **🔑 多账号管理** | 每个平台支持多个账号（别名区分），启用/禁用，Cookie 状态监测 |
| **🌐 浏览器自动化登录** | Playwright 真实浏览器登录 amobbs、闲鱼、立创开源硬件（OSHWHub），自动处理验证码 |
| **🧠 AI 供应商配置** | 从数据库动态管理 DeepSeek/OpenAI/Anthropic/Gemini 等 21+ 供应商，零消耗测试连接，余额查询 |
| **📅 智能签到** | 支持 Discuz! 论坛自动签到，定时+随机1小时窗口执行，各账号独立设置时间 |
| **🚀 站点部署** | 一键部署静态站点到 GitHub Pages |
| **↩️ 撤回管理** | 已发布的文章可撤回，支持重新发布 |
| **📊 发布追踪** | 每篇文章发布记录、部署状态一目了然 |
| **🔐 安全设计** | 首次启动自动生成随机管理员凭据，敏感信息不硬编码 |
| **💾 存储管理** | 本地存储 + AList 网盘，文章图片附件管理 |
| **🌐 国际化** | 支持中文/英文界面 |

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Git
- （可选）Playwright（浏览器自动化登录需要）
- （可选）Cloudflare Tunnel 用于外网访问

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
> - 使用 Nginx + Gunicorn 反向代理
> - 参考下方隧道章节配置外网安全访问

### 外网访问

```bash
# 使用 frpc 或 Cloudflare Tunnel 将本地 5000 端口映射到外网
# 示例（frpc）：
frpc -c frpc.toml
```

## 🔧 环境变量

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `FLASHSLOTH_SECRET` | 自动生成 | 建议 | Flask 密钥，生产环境建议固定 |
| `FLASHSLOTH_HOST` | `0.0.0.0` | 否 | 监听地址 |
| `FLASHSLOTH_PORT` | `5000` | 否 | 监听端口 |

## 🏗️ 项目结构

```
flashsloth/
├── admin.py                  ← Web 管理后台（主入口）
├── core/
│   ├── article.py            ← 统一文章模型
│   ├── publisher.py          ← Publisher 基类 + 注册中心
│   ├── deployer.py           ← Deployer 基类 + 注册中心
│   ├── storage.py            ← 存储抽象层（Local / AList）
│   ├── config.py             ← 配置管理
│   ├── signin.py             ← 签到插件基类
│   ├── provider_registry.py  ← AI 供应商动态注册表（21+）
│   ├── provider_registry.json ← 供应商预设数据
│   └── platform_presets.json ← 知名站点预置列表
├── plugins/
│   ├── publisher_*.py        ← 各平台发布器（Discuz/WordPress/…）
│   ├── *login.py             ← Playwright 浏览器登录器
│   ├── forum_signin.py       ← 签到 orchestrator
│   ├── signin_*.py           ← 各平台签到实现
│   └── forum_reader.py       ← 论坛阅读器
├── sdk/
│   ├── adapter.py            ← SDK 适配器基类
│   ├── router.py             ← SDK 路由器
│   └── adapters/*.py         ← 各平台 SDK 适配器
├── templates/                ← Jinja2 模板
│   ├── base.html             ← 基础布局
│   ├── index.html            ← 仪表盘（动态加载已配置平台）
│   ├── accounts.html         ← 平台账号管理（含知名站点预置）
│   ├── ai_settings.html      ← AI 供应商配置
│   ├── signin.html           ← 签到管理
│   └── ...                   ← 其他页面模板
└── flashsloth.db             ← SQLite 数据库（自动生成）
```

## 📸 工作流程

```
创建文章 → 编辑 Markdown → 保存为草稿
    ↓
选择发布目标（勾选平台+账号）
    ↓
发布（Publisher 写入各平台）
    ↓
[可选] 部署到 GitHub Pages（Deployer 推送到仓库）
    ↓
[可选] 撤回 → 重新发布
```

### 账号管理流程

```
添加新平台账号
  → 从下拉列表选择平台（如 Discuz / 立创开源硬件）
  → 选择知名站点预置（自动填充 site_url）
  → 填写账号别名（留空自动生成）
  → 保存 → 使用浏览器自动登录
  → Cookie 自动保存
```

### AI 供应商配置

```
选择供应商（21+ 预设）→ 填 API Key → 测试连接（零消耗调 /v1/models）
  → 成功自动保存到数据库
  → 支持同一供应商多个账号（别称区分）
  → 余额查询（DeepSeek/OpenAI 支持）
  → 启用/禁用/删除
```

## 🖥️ 支持的发布平台

| 平台 | 类型 | 状态 |
|------|------|------|
| Discuz! 论坛 | 论坛发帖 | ✅ 稳定（18个知名论坛预置） |
| WordPress | 博客 | ✅ 稳定 |
| 微信公众号 | 公众号 | ✅ 稳定 |
| 掘金 | 技术社区 | ✅ 稳定 |
| 知乎 | 问答社区 | ✅ 稳定 |
| CSDN | 技术博客 | ✅ 稳定 |
| RSS | 订阅源 | ✅ 稳定 |
| GitHub Pages | 静态博客 | ✅ 稳定 |
| 立创开源硬件平台 | 硬件社区 | ✅ 登录已修复 |
| 闲鱼 | 二手交易 | ✅ 登录 + 商品发布（预留） |
| 哔哩哔哩 | 视频/专栏 | 🔧 专栏发布已完成，视频投稿开发中 |

## 🔒 安全

- 首次启动**自动生成随机管理员账号密码**
- API Key / 密码均存储在数据库，不硬编码
- 敏感信息在日志中自动脱敏
- 生产环境建议配置 `FLASHSLOTH_SECRET` 环境变量
- 支持外网隧道安全穿透，无需开放服务器端口

## 🤝 贡献

欢迎通过 GitHub Issues 提交 bug 报告和功能建议。Pull Requests 请先开 issue 讨论。

## 📄 许可

请参阅 [LICENSE](LICENSE) 文件。

FlashSloth 采用 **双许可模式**：

| 使用场景 | 许可类型 |
|---------|---------|
| 🆓 个人学习、教育、研究 | AGPL-3.0（免费） |
| 🆓 非营利组织、开源项目 | AGPL-3.0（免费） |
| 💼 企业商业使用 | **需要商业许可**（请联系作者） |

商业许可请联系：**277563381@qq.com**
