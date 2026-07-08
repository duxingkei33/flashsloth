# OSHWHub 登录修复 — Claude 编码任务

## 根因分析（已确认）

### 1. site_url 错误 ✅ 已修
- 账号 oshwhub01 (ID=33) 的 site_url = `https://passport.jlc.com/login` ❌
- 已改为 `https://oshwhub.com` ✅
- 影响：playwright_verify.py 用错误域名注入 cookie，导致登录页代替主页被访问

### 2. OshwhubPlaywrightLogin 表单选择器过时 ⏳ 需要 Claude
- 登录页 `passport.jlc.com/login` 已从 **Element UI** → **Ant Design**
- `_wait_for_login_form()` 找 `input.el-input__inner` → **找不到**
- `_fill_login_form()` 找 `input.el-input__inner` → **找不到**
- 结果：`"登录表单未渲染完成"` / `"无法定位登录输入框"`

### 3. Cookie 存储格式问题 ⏳ 需要 Claude
- 当前存的是扁平 cookie 字符串（`name=value; name=value`）
- oshwhub 需要**结构化 cookies_json**（含 domain/path/secure）
- 因为 JLC SSO 用了多个 domain (.oshwhub.com, passport.jlc.com, .jlc.com) 的不同 cookie

### 4. 密码登录也失败 ⏳ 需要 Claude
- publisher_oshwhub.py 的 test_connection 调用 `_fresh_login_context()` → `OshwhubPlaywrightLogin.login()`
- 由于 #2 选择器问题，表单找不到 → 返回 "登录失败"

## 当前实际 DOM（已探索确认）

```python
# passport.jlc.com/login 的 Ant Design 表单
TABS:
  button:has-text('扫码登录')     # 默认选中
  button:has-text('账号登录')     # 密码登录
  button:has-text('手机号登录')   # 手机验证码

FORM FIELDS (账号登录 tab):
  username: input[placeholder*='手机号码'] 或 input[placeholder*='邮箱'] 或 input[placeholder*='账号']
  password: input[type='password']
  submit:   button.ant-btn-primary:has-text('登录') 或 button[type='submit']

LOGIN INDICATORS (已登录态):
  - [class*='user-avatar'] → 用户头像
  - a:has-text('退出') / span:has-text('退出')
  - [class*='user-name'] / [class*='nickname']
```

## 需要 Claude 修改的文件

### 文件 1: `plugins/oshwhub_login.py`
修复 `OshwhubPlaywrightLogin` 类的以下方法：

**`_wait_for_login_form()`** — 当前行 133-167
- 添加 Ant Design 选择器（`.ant-input`, `input.ant-input`, `.ant-form-item` 等）
- Element UI 选择器保留做 fallback
- 加日志：检测到哪种框架

**`_fill_login_form()`** — 当前行 332-406
- Ant Design 模式下找 `input.ant-input` 或 `input[placeholder*='手机号码']`
- 注意区分用户名框和密码框
- 加上 tab 切换后的等待（`page.wait_for_timeout(1000)`）

**`_check_cookies_logged_in()`** — 当前行 432-440
- 确认 cookie_validator 能正确验证 oshwhub 已登录态

**`login()` 表单提交后检查** — 当前行 569-594
- 提交后等待页面跳转（从 passport.jlc.com → oshwhub.com）
- 检查 URL 是否包含 oshwhub.com

### 文件 2: `plugins/publisher_oshwhub.py` — `test_connection()` 行 144-218
- 密码登录路径：已经调用了 `_fresh_login_context()`，修复文件 1 后自动生效
- Cookie 路径：行 178-218，调用 `self._parse_cookies_fallback()` 
  - 此方法硬编码 `domain: ".oshwhub.com"` — 应该是可行的
  - 但如果 cookie 是直接从浏览器复制的扁平字符串，可能缺少 oshwhub.com 域的 cookie

### 文件 3: `scripts/playwright_verify.py` 和 `scripts/playwright_verify_raw.py`
- 两个脚本都是用 `site_url` 提取 cookie 的 domain
- 现在 site_url 已改为 `https://oshwhub.com`，domain 为 `.oshwhub.com`
- 确认 oshwhub 的 cookie 验证逻辑在 cookie 有效时能正确判断已登录态

## 验证方式
1. 先手动运行 `python3 -c "from plugins.oshwhub_login import OshwhubPlaywrightLogin; l=OshwhubPlaywrightLogin(); result=l.login('13423796740','Lcsc@211211'); print(result)"` 测试密码登录
2. 然后在 FS UI 点「状态检测」看是否返回 `logged_in: true`
3. 最后验证发布功能

## 参考文件
- `platform_reports/oshwhub_exploration_report.json` — 最新探索数据
- `platform_reports/oshwhub_login_capabilities.json` — 登录能力数据
