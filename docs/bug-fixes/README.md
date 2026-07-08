# 🐛 Bug 修复记录索引

> 每个 bug 一条记录，包含：症状 → 根因 → 修复 → 教训 → 关联铁律
> 目的：避免重复犯错，加速诊断

| # | Bug | 版本 | 严重度 | 模块 |
|---|-----|------|:---:|------|
| 1 | [验证码图片损坏（Amobbs）](captcha-broken-image.md) | v5.20 | 🔴 | captcha/login |
| 2 | [Cookie 假阳性验证](cookie-false-positive.md) | v5.19b | 🔴 | cookie/status |
| 3 | [BrowserEngine 线程死锁](browser-engine-deadlock.md) | v4.64 | 🔴 | browser |
| 4 | [39 项硬编码违规](hardcode-39-violations.md) | v5.18 | 🔴 | 全项目 |
| 5 | [模板 .pyc 缓存陈旧](stale-pycache.md) | v4.58 | 🟡 | template |
| 6 | [Amobbs .seccodecheck 机制缺失](captcha-seccodecheck-missing.md) | v5.21 | 🔴 | captcha/login |
| 7 | [Amobbs 验证码刷新 — Playwright 跨线程](captcha-refresh-cross-thread.md) | v5.21 | 🔴 | captcha/login |
| 8 | [Amobbs 验证码提交回归 — 预检阻断](captcha-submit-regression.md) | v5.21 | 🔴 | captcha/login |
| 9 | [Amobbs border click 误触刷新验证码](captcha-border-click.md) | v5.21 | 🔴 | captcha/login |