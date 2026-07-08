# 🐛 Bug 修复记录索引

> 每个 bug 一条记录，包含：症状 → 根因 → 修复 → 教训 → 关联铁律
> 目的：避免重复犯错，加速诊断

| # | Bug | 版本 | 严重度 | 模块 |
|---|-----|------|:---:|------|
| 1 | [验证码图片损坏（Amobbs）](captcha-broken-image.md) | v5.20 | 🔴 | captcha/login |
| 2 | [Cookie 假阳性验证](cookie-false-positive.md) | v5.19b | 🔴 | cookie/status |
| 3 | [OSHWHub SSO 登录失败](oshwhub-sso-login.md) | v5.19 | 🔴 | login/SSO |
| 4 | [BrowserEngine 线程死锁](browser-engine-deadlock.md) | v4.64 | 🔴 | browser |
| 5 | [WSGI Playwright 子进程死锁](wsgi-playwright-deadlock.md) | v4.65 | 🟠 | browser/WSGI |
| 6 | [QR 码扫码线程安全](qr-thread-safety.md) | v4.76 | 🟠 | qrcode/thread |
| 7 | [39 项硬编码违规](hardcode-39-violations.md) | v5.18 | 🔴 | 全项目 |
| 8 | [模板 .pyc 缓存陈旧](stale-pycache.md) | v4.58 | 🟡 | template |
| 9 | [JS 浏览器缓存陈旧](stale-js-cache.md) | v5.17 | 🟡 | frontend |
| 10 | [探索数据预热空表](exploration-warmup-empty.md) | v5.16 | 🟡 | exploration |
| 11 | [签到注册器分裂](signin-registry-split.md) | v4.76 | 🟡 | signin |
| 12 | [site_url 硬编码回退](site-url-hardcode-fallback.md) | v5.15 | 🟠 | data-driven |