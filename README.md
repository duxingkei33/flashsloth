[🇨🇳 中文](README.md) | [🇬🇧 English](README_EN.md)

---

# 🦥 FlashSloth

**树懒的速度，闪电的发布**

FlashSloth（树懒）是一款开源多平台内容发布与站点部署系统。一次编写 Markdown，一键发布到多个内容平台，或部署为静态站点。

## ✨ 特性

| 功能 | 说明 |
|------|------|
| **📝 文章管理** | Markdown 编辑器，实时预览，标签管理，草稿/发布状态 |
| **📡 多平台发布** | Discuz! 论坛、GitHub Pages 博客、WordPress、微信公众号、掘金、知乎、CSDN、RSS |
| **🚀 站点部署** | 一键部署静态站点到 GitHub Pages |
| **↩️ 撤回管理** | 已发布的文章可撤回，支持重新发布 |
| **📊 发布追踪** | 每篇文章的发布记录、部署状态一目了然 |
| **🔐 安全设计** | 首次启动自动生成随机管理员凭据，GitHub Token 认证 |
| **💾 存储管理** | 本地存储 + AList 网盘，文章图片附件管理 |
| **🌐 国际化** | 支持中文/英文界面（见本页顶部的语言切换） |

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Git
- （可选）Cloudflare Tunnel 用于外网访问

### 安装与启动

```bash
# 1. 克隆仓库
git clone https://github.com/duxingkei33/flashsloth.git
cd flashsloth

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动（会自动初始化数据库和随机管理员账号）
python flashsloth/admin.py

# 4. 看到终端输出类似以下内容，即表示启动成功：
# ======================================================
#   🦥 FlashSloth — 树懒的速度，闪电的发布
#   🌐 http://0.0.0.0:5000
#   👤 首次启动，自动生成了管理员账号：
#      用户名: admin_a1b2c3
#      密码:   Xy7kPq9mR2vL4nW8
#   ⚠️  请尽快登录后台修改密码！
# ======================================================

# 5. 打开浏览器访问 http://localhost:5000 即可管理
```

> **⚠️ 生产环境建议：**
> - 设置环境变量 `FLASHSLOTH_SECRET` 固定 Secret Key
> - 使用 Nginx + Gunicorn 反向代理
> - 参考下方 Cloudflare Tunnel 章节配置外网安全访问

### 外网访问（Cloudflare Tunnel）

```bash
# 启动 Cloudflare Tunnel（无需域名，无需开放端口）
cloudflared tunnel --url http://localhost:5000

# 会得到一个 https://xxxx.trycloudflare.com 地址，可以直接访问
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
│   └── config.py             ← 配置管理
├── plugins/
│   ├── publisher_discuz.py        ← Discuz! 论坛发布
│   ├── publisher_github_pages.py  ← GitHub Pages 博客发布
│   ├── publisher_wordpress.py     ← WordPress 发布
│   ├── publisher_wechat.py        ← 微信公众号发布
│   ├── publisher_juejin.py        ← 掘金发布
│   ├── publisher_rss.py           ← RSS 订阅
│   ├── publisher_zhihu.py         ← 知乎发布
│   ├── publisher_csdn.py          ← CSDN 发布
│   ├── deployer_github_pages.py   ← GitHub Pages 部署
│   └── storage_alist.py           ← AList 网盘存储
├── templates/                ← Jinja2 模板
│   ├── base.html             ← 基础布局（含导航栏）
│   ├── index.html            ← 仪表盘
│   ├── edit.html             ← 文章编辑器（含实时预览）
│   ├── login.html            ← 登录页
│   ├── publish_select.html   ← 发布目标选择
│   ├── publish_manage.html   ← 发布管理（撤回/重新发布）
│   ├── deployers.html        ← 部署管理
│   ├── accounts.html         ← 平台账号管理
│   ├── storage_settings.html ← 存储设置
│   └── settings.html         ← 系统设置
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

## 🔒 安全

- 首次启动**自动生成随机管理员账号密码**
- GitHub 部署使用 **Personal Access Token 认证**，不在代码中硬编码凭据
- 生产环境建议配置 `FLASHSLOTH_SECRET` 环境变量
- 支持外部 Cloudflare Tunnel 安全穿透，无需开放服务器端口

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
