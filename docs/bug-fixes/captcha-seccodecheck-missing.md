# Bug #13: Amobbs 验证码提交 — .seccodecheck 机制缺失

**版本**: v5.21 | **严重度**: 🔴 | **模块**: captcha/login | **日期**: 2026-07-08

## 症状（Symptom）

Amobbs 文本验证码登录时，提交验证码后登录失败。代码尝试查找 `.seccodecheck` DOM 元素来检测验证码核验状态（✓/✗），但 Amobbs 使用简单文本验证码，**不存在 `.seccodecheck` 边框核验机制**。

## 根因（Root Cause）

`plugins/amobbs_login.py` 的 `submit_text_captcha()` 方法硬编码了 `.seccodecheck` 核验流程：
1. 填入验证码 → 点击输入框右侧边框触发 `.seccodecheck` 核验
2. 通过 `eval_on_selector(".seccodecheck", "el.classList.contains('seccodecheck_ok')")` 判断核验结果
3. `ok` → 提交登录，否则不提交

但 Amobbs 没有 `.seccodecheck` 元素，`page.wait_for_selector(".seccodecheck", timeout=1000)` 超时后代码执行异常路径，最终未正确提交表单。

部分 Discuz 变体有 `.seccodecheck` 机制（如 Mydigit），但 Amobbs 没有 — 代码统一处理所有 Discuz 平台，未区分。

## 修复（Fix）

1. **检测-分流模式**：提交前先检测 `.seccodecheck` 元素是否存在：
   - 有 `.seccodecheck` → 走边框核验流程（点击右侧触发 → 检查 class → 通过后提交）
   - 无 `.seccodecheck` → 直接提交表单（`click_captcha_and_submit()`）

2. **site_url 补全**：修复登录中 `site_url` 缺失导致后续跳转失败的问题

3. **验证码图片验证**：Playwright 元素截图确认验证码图片正确加载

## 教训（Lesson）

1. **DOM 结构不可假设跨 Discuz 变体** — Amobbs/Mydigit/Discuz 虽然同系，但前端细节不同。必须检测-分流，不能硬编码统一流程。
2. **验证码检测前置**（铁律 #8）— 表单提交前先检测验证码机制类型，再决定提交方式。
3. **Discuz 类平台差异**（铁律 #38）— `.seccodecheck` 是可选功能，不是所有 Discuz 站点都有。

## 关联铁律

- 铁律 #8: Captcha 检测必须在表单提交之前
- 铁律 #38: Discuz 验证码 — 选择器差异 + 元素截图
- 铁律 #36: 单登录类多平台隔离 — 不能硬编码平台特定逻辑