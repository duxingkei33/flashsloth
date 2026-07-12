# Bug #1: 验证码图片损坏（Amobbs）

| 属性 | 值 |
|------|-----|
| 版本 | v5.20 |
| 日期 | 2026-07-08 |
| 严重度 | 🔴 阻塞级 |
| 模块 | captcha/login |
| 关联铁律 | #28 数据驱动, #38 Discuz验证码刷新 |

## 症状
Amobbs 论坛添加账号时，验证码图片显示为损坏/空白图。前端 `showCaptchaInput()` 显示的是相对URL（如 `/misc.php?mod=seccode&...`），浏览器无法加载。

## 根因
三重问题：
1. **后端 `_get_captcha_image()`**: 使用 `urllib.request` 直接下载验证码图片，但缺少 Playwright 浏览器会话的 Cookie，服务器返回空响应
2. **前端**: 用相对 URL 作为 `<img src>`，但当前页面是 FS 的 domain（localhost），Discuz 的相对路径无法解析
3. **验证码刷新**: 点击图片不会触发刷新（Discuz 机制是点 `<a>换一个</a>` 链接）

## 修复
1. `_get_captcha_image()` 改用 Playwright 元素截图 (`element.screenshot()`)，带完整浏览器会话 Cookie
2. 前端 `showCaptchaInput()` 优先使用 base64 数据，不再依赖相对 URL
3. 验证码刷新改用 `a:has-text('换一个')` 选择器点击

## 教训
- **永远不要用 urllib/requests 替代 Playwright 下载需要登录态的资源** — 会话 Cookie 是关键
- **前端不能假设跨域资源可用** — 验证码图片必须由后端代理转发
- **每个平台的验证码刷新机制不同** — 必须从探索数据动态读取刷新方式

## 关联
- 铁律 #38: Discuz 验证码刷新选择器
- 铁律 #28: 数据驱动，禁止硬编码平台行为