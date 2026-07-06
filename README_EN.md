[🇨🇳 中文](README.md) | [🇬🇧 English](README_EN.md)

---

# 🦥 FlashSloth — Your Personal Digital Asset Hub

> Sloth speed, lightning publishing
> One dashboard to manage all your digital assets across the internet

---

## ✨ Features

### 🔐 Account Management
- [x] Unified multi-platform account management (add/edit/delete/enable/disable)
- [x] 🔑 Password + captcha login — Playwright browser automation
- [x] 📱 QR code scan login — Remote browser screenshot + 10s polling cookie capture
- [x] 🍪 Cookie paste (debug mode)
- [x] 🖼️ Login method demo cards (mini-app style step-by-step guide)
- [x] 🔒 Credential encryption storage (Fernet AES-128-CBC + HMAC-SHA256)
- [x] 📊 Real-time account status detection (Playwright cookie verification)
- [x] 🧩 Unified browser login button — shared edit dialog for all platforms

### 📝 Multi-Platform Publishing
- [x] Discuz! Forums (amobbs/mydigit etc.) — post + draft + sign-in
- [x] WordPress — REST API publish (App Password auth)
- [x] WeChat Official Account — Official API draft (AppID + AppSecret)
- [x] CSDN — Playwright publish + sign-in
- [x] Zhihu — Full Playwright rewrite (password/QR/Cookie)
- [x] OSHWHub (JLCPCB Open Source) — Playwright publish + sign-in
- [x] Juejin — Cookie-based publish (password/QR/Cookie)
- [x] Bilibili Articles — Playwright publish + draft save + image upload (password/QR/Cookie)
- [x] Twitter/X — tweepy API v2 OAuth1.0a
- [x] Xianyu (Goofish) Product Listing — MTOP Signature V2 + AI category + SDK
- [x] Gallery Product Listing (Reserved)
- [x] RSS Feed — Pure Python generation
- [x] GitHub Pages — git push deployment

### 🔔 Notification Gateway
- [x] 23 notification channels (Feishu/DingTalk/WeCom/WeChat/Telegram/Discord/Slack etc.)
- [x] QR code auto-configuration via /callback endpoint
- [x] Message queue + Provider registry
- [x] Batch test / single channel test

### 🔍 Platform Exploration
- [x] Discuz forum auto-exploration (Playwright)
- [x] Hourly incremental polling
- [x] Anti-detection rate limiting (1/domain/hour, dual-cache memory+DB for cross-process)
- [x] Forum section keyword matching
- [x] Exploration data management page
- [x] Platform publish capability display + tag section management

### 👨‍👩‍👧‍👦 Auto Sign-In
- [x] OSHWHub sign-in (with auto re-login on cookie expiry + asyncio isolation fix)
- [x] CSDN sign-in
- [x] amobbs / Discuz! sign-in
- [x] Sign-in statistics (success/failure breakdown)
- [x] Random execution window (within 1 hour of configured time)

### 🛒 Xianyu Integration
- [x] Product search (keyword/price range/sort/pagination)
- [x] Price monitoring & comparison (LCSC components)
- [x] MTOP Signature V2 publisher + AI category recognition
- [x] xianyu_client SDK (mtop/sign/session/media/category/limiter/guard)

### 🧠 Smart Matching
- [x] AI section matching (multi-platform support)
- [x] Keyword library sync
- [x] AI provider dynamic management (21+ providers, balance query, test connection)

### 📋 Approval Workflow
- [x] Create/approve/reject/cancel approval requests
- [x] Webhook endpoint (text commands like "approve 123")
- [x] Gateway notifications + approval history

### 📚 Unified Pipeline
- [x] 3-module shared workflow engine (Collect→Compile→Preview→Draft→Publish)
- [x] Visual pipeline flow chart
- [x] Run history list

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  User Interface Layer (Flask Web UI)               │
│  Dashboard · Articles · Sign-In · Xianyu Search · Accounts        │
│  Config · Exploration Data · Gateway · Approval · AI Settings     │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                    Gateway API Layer (routes/)                     │
│  routes/accounts.py · gateway.py · ai.py · signin.py              │
│  exploration.py · posts.py · api_v2.py · browser_login.py         │
│  approval.py · notifications.py · price_monitor.py                │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                 Unified Workflow Engine (core/)                    │
│  publisher · gateway · scheduler · database · credential_crypto    │
│  anti_detect · explorer · price_monitor · approval · notifier      │
│  ai_provider · article · deployer · compiler · pipeline            │
│  pipeline · signin · image_pipeline · captcha_handler              │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                Plugin + Adapter Layer (plugins/ + sdk/)            │
│  publisher_*.py — 14 platform publishers                          │
│  signin_*.py   — 3 sign-in plugins                                │
│  generic_login.py · xianyu_client/ · sdk/adapters/                │
└──────────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                    Public Infrastructure                            │
│  SQLite (flashsloth.db) · .fs_key encryption key · config/        │
│  templates/ · static/ · platform_reports/ · scripts/               │
│  DEVELOPMENT_SPECIFICATION.md · ARCHITECTURE.md                    │
└──────────────────────────────────────────────────────────────────┘
```

> See [ARCHITECTURE.md](ARCHITECTURE.md) for full architecture details

---

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
#   🦥 FlashSloth — Sloth speed, lightning publishing
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
> - Set `FS_ENCRYPTION_KEY` for a fixed encryption key
> - Use Nginx + Gunicorn as a reverse proxy

### External Access

```bash
# Use frpc or Cloudflare Tunnel to expose local port 5000
frpc -c frpc.toml
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `FLASHSLOTH_SECRET` | Auto-generated | Recommended | Flask secret key for production |
| `FS_ENCRYPTION_KEY` | Auto-generated | Recommended | Fernet encryption key; falls back to .fs_key |
| `FLASHSLOTH_HOST` | `0.0.0.0` | No | Listen address |
| `FLASHSLOTH_PORT` | `5000` | No | Listen port |

### Key Files

- `.fs_key` — Fernet credential encryption key (mode 600), auto-generated on first boot

---

## 📊 Scheduled Tasks

| Task | Interval | Description |
|------|----------|-------------|
| Auto Sign-In | Every minute | Daemon thread executes within configured time window (default 08:00-09:00) |
| Forum Exploration | Hourly | `scripts/hourly_forum_check.py` — incremental Discuz section check |
| Price Refresh | Per config | LCSC component price refresh |

---

## 📋 Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| v4.51 | 2026-07-07 | Bilibili Publisher enhancements (save_as_draft+upload_image) + dev spec + exploration report |
| v4.50 | 2026-07-07 | Demo diagrams + generic login adapters (CSDN/wechat/zhihu) |
| v4.49 | 2026-07-07 | Account dialog overhaul — QR login + demo cards + captcha UX |
| v4.48 | 2026-07-06 | Unified edit dialog — redirect /edit to /accounts, masked value save |
| v4.47 | 2026-07-06 | Fix test_connection decrypt compat + config_json encrypt/decrypt |
| v4.46 | 2026-07-06 | Credential encryption — Fernet AES-128 for passwords/cookies/tokens |
| v4.45 | 2026-07-06 | Gateway QR auto-config — /callback endpoint |
| v4.42 | 2026-07-06 | OSHWHub auto re-login on cookie expiry + E2E draft save |
| v4.41 | 2026-07-06 | Fix OSHWHub login status detection — Playwright cookie verify |
| v4.39 | 2026-07-06 | 23-channel gateway + anti-detect module + Xianyu V2 MTOP + Explorer overhaul |
| v4.36 | 2026-07-06 | Notification system + Gateway + unified pipeline + Xianyu search UI + exploration |
| v4.35 | 2026-07-06 | Twitter/X Publisher + dynamic exploration sort |
| v4.33 | 2026-07-06 | Zhihu publisher overhaul + exploration UI + sign-in stats fix |

---

## 📄 License

See the [LICENSE](LICENSE) file for details.

FlashSloth uses a **dual-license model**:

| Use Case | License |
|---------|---------|
| 🆓 Personal learning, education, research | AGPL-3.0 (free) |
| 🆓 Non-profit organizations, open-source projects | AGPL-3.0 (free) |
| 💼 Commercial use by organizations | **Requires commercial license** (contact author) |

For commercial licensing: **277563381@qq.com**
