# Bug #8: Amobbs 验证码提交回归 — 预检阻断导致登录失败

**版本**: v5.21 | **严重度**: 🔴 | **模块**: captcha/login | **日期**: 2026-07-08

## 症状（Symptom）

Bug #6 (.seccodecheck 修复) 部署后，Amobbs 文本验证码登录出现新故障：验证码填写完毕点击提交后，登录流程被阻断，返回「核验未完成」错误，无法正常提交表单。

## 根因（Root Cause）

**回归链**：Bug #6 修复引入预检逻辑 → 预检不确定时返回错误阻断提交。

Bug #6 修复在 `submit_text_captcha()` 中增加了 `.seccodecheck` 检测-分流逻辑：
- 有 `.seccodecheck` → 走边框核验 → 通过后提交
- 无 `.seccodecheck` → 直接提交

但预检逻辑在「不确定」状态（如元素未完全加载、DOM 状态模糊）时，返回了 `'核验未完成'` 错误，阻断了本该成功的表单提交。Amobbs 没有 `.seccodecheck` 机制，但预检的超时/异常路径被错误地当作「核验未完成」处理，而非触发兜底直接提交。

## 修复（Fix）

**三态策略** (`submit_text_captcha`):

| 预检结果 | 行为 |
|---------|------|
| ✅ 确定有 `.seccodecheck` + 核验通过 | 正常提交 |
| ❌ 预检明确出错（DOM 异常） | 立即返回错误 |
| ⚠️ 预检不确定（超时/元素不存在） | **兜底→直接提交表单**（旧行为） |

同时修复：
1. **auth_cookie 过滤**：排除 `_sid` session cookie（非认证 cookie，不应参与 auth 判断）
2. **线程追踪恢复**：`routes/browser_login.py` 恢复 `_discuz_thread_owners` 字典追踪
3. **platform_accounts fallback**：线程切换时从 DB 恢复 platform 配置
4. **E2E 验证脚本**：新增 `test_amobbs_e2e.py` Playwright 端到端验证

## 验证

- ✅ 验证码检测正常 (151x81, 27KB)
- ✅ 错误验证码正确检测并拒绝
- ✅ 正确验证码正常提交登录

## 教训（Lesson）

1. **修复可能引入回归** — 每次修复后必须完整 E2E 验证，不能只测修复路径
2. **预检必须有三态（ok/err/兜底）** — 两态（ok/err）在不确定场景下会错误阻断正常流程
3. **兜底策略 = 旧行为** — 当预检不确定时，回退到修复前的旧行为是最安全的策略
4. **auth cookie 要过滤 session cookie** — `_sid` 等临时 session cookie 不应参与认证判断

## 关联铁律

- 铁律 #8: Captcha 检测必须在表单提交之前
- 铁律 #15: E2E 必须用 Playwright 真实浏览器
- 铁律 #42: Bug 修复必须记录到 docs/bug-fixes/
- 铁律 #36: 单登录类多平台隔离 — 不能硬编码平台特定逻辑