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
- [x] 📱 Phone SMS login — phone_login + SMS verification code flow + frontend support
- [x] 🪪 Unified login capability exploration — 7-platform Playwright real detection (password/QR/SMS) + JSON report + dynamic tab rendering
- [x] 🍪 Cookie paste (debug mode)
- [x] 🖼️ Login method demo cards (mini-app style step-by-step guide)
- [x] 🔒 Credential encryption storage (Fernet AES-128-CBC + HMAC-SHA256)
- [x] 📊 Three-layer status detection — persistent BrowserEngine + API lightweight check + Playwright real verification + 3-tier cache (memory/SQLite/real-time) + batch refresh + deep user info
- [x] 🧩 Unified browser login button — shared edit dialog for all platforms
- [x] 📱 Phone SMS login extended to CSDN/Bilibili publishers
- [x] 🏗️ BrowserEngine persistent refactor — shared engine + subprocess Playwright verification (avoids WSGI deadlock)
- [x] 🪟 Account modal deepening — amobbs/discuz/mydigit/wordpress + captcha input + 5-step progress bar + Amobbs border verification
- [x] 🔍 Login status deep verification — real extraction of username/points/level + frontend display enhancement
- [x] 🎨 Account page UI enhancement — search optimization/platform color labels/quick add/time labels/batch progress bar

### 📝 Multi-Platform Publishing
- [x] Discuz! Forums (amobbs/mydigit etc.) — post + draft + sign-in
- [x] WordPress — REST API publish (App Password auth)
- [x] WeChat Official Account — Official API draft (AppID + AppSecret) + exploration + image upload/cover/summary
- [x] CSDN — Playwright publish + sign-in
- [x] Zhihu — Full Playwright rewrite (password/QR/Cookie) + platform exploration report
- [x] OSHWHub (JLCPCB Open Source) — Playwright publish + sign-in
- [x] Juejin — Cookie-based publish (password/QR/Cookie)
- [x] Bilibili Articles — Playwright publish + draft save + image upload + login plugin + exploration reports (password/QR/Cookie)
- [x] Twitter/X — tweepy API v2 OAuth1.0a + login capability/presets/image extraction + draft isolation
- [x] Xianyu (Goofish) Product Listing — MTOP Signature V2 + AI category + SDK
- [x] Xianyu Auto-Reply System Integration — Docker service (product listing/order query)
- [x] Xianyu Auto-Reply Sidecar Adapter — xianyu-auto-reply REST API + health monitoring
- [x] Gallery Product Listing (Reserved)
- [x] RSS Feed — Pure Python generation
- [x] GitHub Pages — git push deployment
- [x] 📋 Article list multi-select batch delete/publish

### 🔔 Notification Gateway
- [x] 22 notification channels (Telegram/Discord/Slack/WhatsApp/DingTalk/WeCom/Feishu/WeChat/Email/Matrix/Teams/LINE etc.)
- [x] QR code auto-configuration via /callback endpoint
- [x] Message queue + Provider registry
- [x] Batch test / single channel test

### 🔍 Platform Exploration
- [x] Discuz forum auto-exploration (Playwright)
- [x] Login capability exploration — 7-platform auto-detection (password/QR/SMS) + JSON reports
- [x] Hourly incremental polling + anti-detection rate limiting (dual-cache memory+DB persistence for cross-process)
- [x] Forum section keyword matching + exploration data management page
- [x] Platform publish capability display + tag section management
- [x] Bilibili full exploration report + login plugin + platform capability import
- [x] Zhihu platform exploration — login/editor/capability data
- [x] WeChat Official Account exploration — image upload/cover/summary capability
- [x] WeChat full exploration + publisher enhancement
- [x] 🤖 Zhihu/Juejin API lightweight login status detector

### 👨‍👩‍👧‍👦 Auto Sign-In
- [x] OSHWHub sign-in (with auto re-login on cookie expiry + asyncio isolation fix)
- [x] CSDN sign-in
- [x] amobbs / Discuz! sign-in
- [x] Sign-in statistics (success/failure breakdown, de-duplication fix)
- [x] Batch sign-in time configuration + random offset (±30min) setting
- [x] Randomized execution window (within 1 hour of configured time, account_id offset to avoid concurrent sign-ins)

### 🛒 Xianyu Integration
- [x] Product search (keyword/price range/sort/pagination)
- [x] Price monitoring & comparison (LCSC components)
- [x] MTOP Signature V2 publisher + AI category recognition
- [x] xianyu_client SDK (mtop/sign/session/media/category/limiter/guard)
- [x] Xianyu Auto-Reply System — Docker service integration + API proxy + health status monitoring

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

### 🧰 Workspace & Provider Framework
- [x] Unified content management workspace — Provider selection + pipeline + content logs
- [x] Provider abstraction framework — base→workspace, 3 Providers (Markdown/Notion/Taobao), config management
- [x] AI call log system — auto-recording + visual log page + pagination/filtering
- [x] 📋 Unified log management — publish/sign-in/AI/deploy logs in one page + pagination + real-time filtering
- [x] 🖥️ Playwright browser engine settings page
- [x] 🖥️ BrowserEngine auto-cleanup — 60s monitoring thread, auto-recycle idle browser instances
- [x] External service registry — unified management for xianyu-auto-reply etc.
- [x] Deployment config enhancement — deploy block embedded in account page + deployers enhanced

### 💬 Comment Monitoring
- [x] Multi-forum comment monitoring — unread/reply/stats dashboard
- [x] Comment notification push

### 📱 Mobile Support
- [x] 📱 Full-page responsive enhancement — zero horizontal overflow at 375px, touch-friendly buttons/modals/nav/card grid
- [x] Mobile CSS enhancements — responsive layout for phones/tablets

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  User Interface Layer (Flask Web UI)               │
│  Dashboard · Articles · Sign-In · Xianyu Search · Accounts        │
│  Config · Exploration Data · Gateway · Approval · AI Settings     │
│  Workspace · AI Logs · Playwright Settings · Comment Monitor      │
│  Deploy Config · External Services · Storage Settings             │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                    Gateway API Layer (routes/)                     │
│  routes/accounts.py · gateway.py · ai.py · signin.py              │
│  exploration.py · posts.py · api_v2.py · browser_login.py         │
│  approval.py · notifications.py · price_monitor.py                │
│  workspace_ui.py · browser_engine.py · external_services.py       │
│  storage_deploy.py · auth.py                                      │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                 Unified Workflow Engine (core/)                    │
│  publisher · gateway · scheduler · database · credential_crypto   │
│  anti_detect · explorer · price_monitor · approval · notifier     │
│  ai_provider · article · deployer · compiler · pipeline           │
│  signin · image_pipeline · captcha_handler                        │
│  browser_engine · status_detector · status_cache · provider       │
│  provider_registry · storage                                       │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                Plugin + Adapter Layer (plugins/ + sdk/)            │
│  publisher_*.py — 16 platform publishers                          │
│  signin_*.py   — 3 sign-in plugins                                │
│  provider_*.py — 3 Provider plugins (Markdown/Notion/Taobao)      │
│  generic_login.py · bilibili_login.py · xianyu_client/           │
│  sdk/adapters/ (15+ platform adapters)                            │
└──────────────────────────────────────────────────────────────────┘
                             ↕
┌──────────────────────────────────────────────────────────────────┐
│                    Public Infrastructure                            │
│  SQLite (flashsloth.db + status_cache.db)                         │
│  .fs_key encryption key · config/ · templates/ · static/          │
│  platform_reports/ (7+ login capability reports)                  │
│  scripts/ · DEVELOPMENT_SPECIFICATION.md · ARCHITECTURE.md        │
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
| Auto Sign-In | Every minute | Daemon thread executes within configured time window, account_id offset to avoid concurrent sign-ins |
| Forum Exploration | Hourly | `scripts/hourly_forum_check.py` — incremental Discuz section check |
| Price Refresh | Per config | LCSC component price refresh |

---

## 📋 Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| v4.91 | 2026-07-07 | QR code login priority #1 across all publishers + site_url propagation fix + BrowserEngine auto-cleanup + Unified log mgmt page |
| v4.90 | 2026-07-07 | Unified log management (publish/sign-in/AI/deploy) + adapter architecture fix + composite search dropdown |
| v4.80 | 2026-07-07 | Mobile layout optimization — full-page responsive (375px zero overflow, touch-friendly buttons/modals/nav/card grid) |
| v4.79 | 2026-07-07 | Login status deep verification — real username/points/level extraction + frontend display |
| v4.78 | 2026-07-07 | Account page UI enhancement (search/platform colors/quick-add/time labels/batch progress) + article multi-select batch ops + Zhihu/Juejin API lightweight status + Xianyu Sidecar adapter |
| v4.77 | 2026-07-07 | Account modal captcha input + 5-step progress bar + Amobbs border verify + Twitter/X login capability complete + ai_call_log fix |
| v4.76 | 2026-07-07 | BrowserEngine thread safety + QR code background thread + signin registry fix |
| v4.75 | 2026-07-07 | Account modal deepening — amobbs/discuz/mydigit/wordpress login completion |
| v4.74 | 2026-07-07 | Provider framework → workspace — base→workspace, 3 Providers, config mgmt + mobile CSS |
| v4.70 | 2026-07-07 | Sign-in stats fix — manual sign-in counting + de-duplication + state persistence |
| v4.67 | 2026-07-07 | Twitter Publisher improvements — image upload pipeline + Article compatibility + draft isolation |
| v4.66 | 2026-07-07 | Zhihu platform exploration — login/editor/capability data |
| v4.65 | 2026-07-07 | Playwright verification subprocess (WSGI deadlock fix) + batch sign-in time + random offset |
| v4.64 | 2026-07-07 | BrowserEngine deadlock fix — context_processor timeout decoupling |
| v4.63 | 2026-07-07 | Cookie count anti-pattern cleanup |
| v4.62 | 2026-07-07 | OSHWHub cookie expiry auto-fallback password + CSDN sign-in fix |
| v4.60 | 2026-07-07 | BrowserEngine persistent + accounts.py refactor + Phone login thread fix |
| v4.59 | 2026-07-07 | Phone SMS login extended to CSDN/Bilibili publishers |
| v4.58 | 2026-07-07 | Production perf optimization — disable hot reload + BrowserEngine 2s cache |
| v4.57 | 2026-07-07 | 3-layer status detection — persistent BrowserEngine + API lightweight + Playwright verify + cache + deep user info |
| v4.56 | 2026-07-07 | Bilibili full exploration report + login plugin + platform capability import + WeChat exploration/publisher |
| v4.55 | 2026-07-07 | AI call log system + Workspace + Phone SMS login + unified login exploration + Playwright settings + mobile CSS |

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
