[🇨🇳 中文](README.md) | [🇬🇧 English](README_EN.md)

---

# 🦥 FlashSloth

**Publish at sloth speed**

FlashSloth is an open-source multi-platform content publishing and site deployment system. Write once in Markdown, publish to multiple platforms with a single click, or deploy as a static site.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **📝 Article Editor** | Markdown editor with live preview, tag management, draft/published states |
| **📡 Multi-Platform Publishing** | Discuz! Forums, GitHub Pages Blog, WordPress, WeChat, Juejin, Zhihu, CSDN, RSS |
| **🚀 Site Deployment** | One-click static site deployment to GitHub Pages |
| **↩️ Retract Management** | Retract published articles with optional re-publish |
| **📊 Publish Tracking** | Full publish history and deploy status for every article |
| **🔐 Security** | Auto-generated random admin credentials on first boot, GitHub Token auth |
| **💾 Storage** | Local storage + AList cloud storage, image/file attachments |
| **🌐 i18n** | Chinese/English interface (see language switcher at top) |

## 🚀 Quick Start

### Requirements

- Python 3.10+
- Git
- (Optional) Cloudflare Tunnel for external access

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/duxingkei33/flashsloth.git
cd flashsloth

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start (auto-initializes DB and generates random admin credentials)
python flashsloth/admin.py

# 4. On first boot, you'll see:
# ======================================================
#   🦥 FlashSloth — 树懒的速度，闪电的发布
#   🌐 http://0.0.0.0:5000
#   👤 First boot: auto-generated admin credentials:
#      Username: admin_a1b2c3
#      Password: Xy7kPq9mR2vL4nW8
#   ⚠️  Please change password after login!
# ======================================================

# 5. Open http://localhost:5000 in your browser
```

> **⚠️ Production tips:**
> - Set the `FLASHSLOTH_SECRET` env var for a fixed secret key
> - Use Nginx + Gunicorn as a reverse proxy
> - See Cloudflare Tunnel section below for secure external access

### External Access (Cloudflare Tunnel)

```bash
# Start a Cloudflare Tunnel (no domain needed, no ports opened)
cloudflared tunnel --url http://localhost:5000

# You'll get a https://xxxx.trycloudflare.com URL
```

## 🔧 Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `FLASHSLOTH_SECRET` | Auto-generated | Recommended | Flask secret key |
| `FLASHSLOTH_HOST` | `0.0.0.0` | No | Listen address |
| `FLASHSLOTH_PORT` | `5000` | No | Listen port |

## 🏗️ Project Structure

```
flashsloth/
├── admin.py                  ← Web admin panel (main entry)
├── core/
│   ├── article.py            ← Unified article model
│   ├── publisher.py          ← Publisher base class + registry
│   ├── deployer.py           ← Deployer base class + registry
│   ├── storage.py            ← Storage abstraction layer
│   └── config.py             ← Configuration
├── plugins/
│   ├── publisher_discuz.py   ← Discuz! Forum publisher
│   ├── publisher_github_pages.py ← GitHub Pages blog publisher
│   ├── publisher_wordpress.py    ← WordPress publisher
│   ├── publisher_wechat.py       ← WeChat Official Account
│   ├── publisher_juejin.py       ← Juejin publisher
│   ├── publisher_rss.py          ← RSS feed publisher
│   ├── publisher_zhihu.py        ← Zhihu publisher
│   ├── publisher_csdn.py         ← CSDN publisher
│   ├── deployer_github_pages.py  ← GitHub Pages deployer
│   └── storage_alist.py          ← AList cloud storage
├── templates/                ← Jinja2 templates
│   ├── base.html
│   ├── index.html
│   ├── edit.html
│   ├── login.html
│   ├── publish_select.html
│   ├── publish_manage.html
│   ├── deployers.html
│   ├── accounts.html
│   ├── storage_settings.html
│   └── settings.html
└── flashsloth.db             ← SQLite database (auto-created)
```

## 📸 Workflow

```
Create article → Edit Markdown → Save as draft
    ↓
Select target platforms
    ↓
Publish (Publisher writes to each platform)
    ↓
[Optional] Deploy to GitHub Pages (Deployer pushes to repo)
    ↓
[Optional] Retract → Re-publish
```

## 🔒 Security

- **Auto-generated random admin credentials** on first boot
- GitHub deployment uses **Personal Access Token authentication** — no hardcoded credentials
- Set `FLASHSLOTH_SECRET` env var for production
- Cloudflare Tunnel support for secure external access without opening firewall ports

## 🤝 Contributing

Bug reports and feature requests are welcome via GitHub Issues. For Pull Requests, please open an issue first to discuss.

## 📄 License

See the [LICENSE](LICENSE) file for details.

FlashSloth uses a **dual-license model**:

| Use Case | License |
|---------|---------|
| 🆓 Personal learning, education, research | AGPL-3.0 (free) |
| 🆓 Non-profit organizations, open-source projects | AGPL-3.0 (free) |
| 💼 Commercial use by organizations | **Requires commercial license** (contact author) |

For commercial licensing: **277563381@qq.com**
