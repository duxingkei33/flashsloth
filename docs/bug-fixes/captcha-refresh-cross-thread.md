# Bug Fix: Amobbs 验证码刷新损坏 — Playwright sync 跨线程访问

**日期**: 2026-07-08  
**版本**: v5.21  
**关联铁律**: #15 (Playwright 必须), #41 (文档同步)

## 症状
- 登录页 `login/start` 返回有效验证码图片
- 调用 `refresh_captcha` API 刷新时，返回空白/全页截图（非验证码）
- 前端显示 "验证码加载失败" 或空白图
- 错误日志显示 Playwright 页面变 blank

## 根因
Flask 多线程模型下，`sync_playwright` 实例不支持跨线程访问：

1. `login/start` 在线程 A 创建 `sync_playwright` 实例 + 打开登录页
2. `refresh_captcha` 在线程 B 尝试访问线程 A 的 Playwright 页面
3. 跨线程访问导致页面变 blank（Playwright 内部状态损坏）
4. `_get_captcha_image()` 检测到页面 blank → 降级到全页截图 → 返回空白图

## 修复

### 1. `routes/browser_login.py` — 线程追踪 + 自动重建
`_get_discuz_login()` 增加 `_discuz_thread_owners` 字典，记录每个 `sync_playwright` 实例的所属线程 ID。检测到线程切换时自动关闭旧实例并在当前线程重建。

### 2. `routes/accounts/login.py` — 简化 refresh 流程
`refresh_captcha` 不再依赖 JS 点击「换一个」链接，改为直接重新加载登录页获取新验证码。更可靠，不依赖页面特定 DOM 元素。

## 验证方法
1. API `/api/platform/amobbs/login/start` → 验证码图片有效 ✅
2. API `/api/platform/amobbs/login/captcha/refresh` x2 → 每次返回有效新验证码 ✅
3. 确认不同线程间不再出现 blank 页面

## 教训
1. **`sync_playwright` 实例绑定创建线程** — 不能在 Flask 多线程模型中跨线程共享
2. **线程追踪是必要的防御** — 线程切换时自动重建实例，避免静默失败
3. **简化比复杂更可靠** — 直接重新加载登录页比 JS 点击「换一个」更稳定
4. **降级策略要警惕** — `_get_captcha_image()` 的降级（全页截图）掩盖了真实问题