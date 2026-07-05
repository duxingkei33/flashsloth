[🇨🇳 中文](README.md) | [🇬🇧 English](README_EN.md)

---

# 🦥 FlashSloth

**Publish at sloth speed**

FlashSloth is an open-source multi-platform content publishing and site deployment system. Write once in Markdown, publish to multiple platforms with a single click, or deploy as a static site.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **📝 Article Editor** | Markdown editor with live preview, tag management, draft/published states |
| **📡 Multi-Platform** | 15+ platforms: Discuz! Forums, WordPress, WeChat, Juejin, Zhihu, CSDN, RSS, GitHub Pages, Xianyu, OSHWHub, Bilibili (WIP) |
| **🔑 Account Management** | Multi-account per platform (alias-based), enable/disable, cookie status monitoring |
| **🌐 Browser Auto-Login** | Playwright-based browser automation for amobbs, Xianyu, OSHWHub (JLCPCB passport), captcha handling |
| **🧠 AI Provider Config** | Database-driven management for 21+ providers (DeepSeek, OpenAI, Anthropic, Gemini), zero-token connection test, balance query |
| **📅 Auto Sign-In** | Discuz! forum auto check-in with random 1-hour window scheduling, per-account time settings |
| **🚀 Site Deployment** | One-click static site deployment to GitHub Pages |
| **↩️ Retract Management** | Retract published articles with optional re-publish |
| **📊 Publish Tracking** | Full publish history and deploy status for every article |
| **🔐 Security** | Auto-generated random admin credentials, no hardcoded secrets |
| **💾 Storage** | Local storage + AList cloud storage, image/file attachments |
| **🌐 i18n** | Chinese/English interface |

## 🚀 Quick Start

### Requirements

- Python 3.10+
- Git
- (Optional) Playwright for browser automation login
- (Optional) Cloudflare Tunnel / frpc for external access

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/duxingkei33/flashsloth.git
cd flashsloth

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright (for browser auto-login)
pip install playwright
python -m playwright install chromium

# 4. Start (auto-initializes DB and generates random admin credentials)
python admin.py

# 5. On first boot, you'll see:
# ======================================================
#   🦥 FlashSloth — 树懒的速度，闪电的发布
#   🌐 http://0.0.0.0:5000
#   👤 First boot: auto-generated admin credentials:
#      Username: admin_a1b2c3
#      Password: Xy7kPq9mR2vL4nW8
#   ⚠️  Please change password after login!
# ======================================================

# 6. Open http://localhost:5000 in your browser
```

> **⚠️ Production tips:**
> - Set the `FLASHSLOTH_SECRET` env var for a fixed secret key
> - Use Nginx + Gunicorn as a reverse proxy
> - See tunnel section below for secure external access

### External Access

```bash
# Use frpc or Cloudflare Tunnel to expose local port 5000
# Example (frpc):
frpc -c frpc.toml
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
│   ├── config.py             ← Configuration
│   ├── signin.py             ← Sign-in plugin base class
│   ├── provider_registry.py  ← AI provider dynamic registry (21+)
│   ├── provider_registry.json ← Provider preset data
│   └── platform_presets.json ← Well-known site presets
├── plugins/
│   ├── publisher_*.py        ← Platform publishers (Discuz/WordPress/…)
│   ├── *login.py             ← Playwright browser login modules
│   ├── forum_signin.py       ← Sign-in orchestrator
│   ├── signin_*.py           ← Per-platform sign-in implementations
│   └── forum_reader.py       ← Forum reader
├── sdk/
│   ├── adapter.py            ← SDK adapter base class
│   ├── router.py             ← SDK router
│   └── adapters/*.py         ← Per-platform SDK adapters
├── templates/                ← Jinja2 templates
│   ├── base.html             ← Base layout
│   ├── index.html            ← Dashboard (dynamic platform loading)
│   ├── accounts.html         ← Account management (with site presets)
│   ├── ai_settings.html      ← AI provider configuration
│   ├── signin.html           ← Sign-in management
│   └── ...
└── flashsloth.db             ← SQLite database (auto-created)
```

## 📸 Workflow

```
Create article → Edit Markdown → Save as draft
    ↓
Select target platforms + accounts
    ↓
Publish (Publisher writes to each platform)
    ↓
[Optional] Deploy to GitHub Pages (Deployer pushes to repo)
    ↓
[Optional] Retract → Re-publish
```

### Account Management Flow

```
Add new platform account
  → Select platform from dropdown (e.g. Discuz / OSHWHub)
  → Pick from well-known site presets (auto-fills site_url)
  → Enter alias (auto-generated if left empty)
  → Save → Browser auto-login
  → Cookie saved automatically
```

### AI Provider Configuration

```
Select provider (21+ presets) → Enter API Key → Test (zero-token /v1/models call)
  → Auto-saves to database on success
  → Supports multiple accounts per provider (alias)
  → Balance query (DeepSeek/OpenAI)
  → Enable/disable/delete
```

## 🖥️ Supported Platforms

| Platform | Type | Status |
|----------|------|--------|
| Discuz! Forums | Forum posts | ✅ Stable (18 well-known forums preset) |
| WordPress | Blog | ✅ Stable |
| WeChat Official Account | Blog | ✅ Stable |
| Juejin | Dev community | ✅ Stable |
| Zhihu | Q&A | ✅ Stable |
| CSDN | Tech blog | ✅ Stable |
| RSS | Feed | ✅ Stable |
| GitHub Pages | Static blog | ✅ Stable |
| OSHWHub (JLCPCB) | Hardware community | ✅ Fixed (passport.jlc.com) |
| Xianyu (Goofish) | Second-hand trading | ✅ Login + Product listing (WIP) |
| Bilibili | Video/Articles | 🔧 Article publishing done, video WIP |

## 🔒 Security

- **Auto-generated random admin credentials** on first boot
- API keys and passwords stored in database, never hardcoded
- Sensitive info auto-redacted in logs
- Set `FLASHSLOTH_SECRET` env var for production
- Cloudflare Tunnel / frpc support for secure external access

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
