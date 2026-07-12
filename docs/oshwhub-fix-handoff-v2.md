# OSHWHub 登录修复 — Claude 编码任务（v2 修正版）

## 网站关系
- **passport.jlc.com** = 嘉立创统一SSO登录中心（JLC ecosystem）
- **oshwhub.com** = 立创开源硬件平台（使用 JLC SSO）
- 关系：**同一SSO体系**，登录 passport.jlc.com 后 SSO 跳转到 oshwhub.com
- Cookie 域：`.jlc.com`（JSESSIONID 等核心凭证在此域）

## 根因链

### 问题1：Cookie 扁平化丢失 domain ❌
credential_provider.py line 661-663 的扫码登录轮询：
```python
all_cookies_str = "; ".join(
    [f"{c['name']}={c['value']}" for c in cookies]  # domain/path 全丢了！
)
```
→ 存入 DB 的是扁平字符串 `JSESSIONID=xxx; JSESSIONID=yyy`
→ playwright_verify.py 取出后强加 domain `.oshwhub.com`
→ 实际 JSESSIONID 需要 domain `.jlc.com` 才能 SSO 验证
→ **cookie 从来没真正有效过！**

### 问题2：test_connection 表单选择器过时
publisher_oshwhub.py 的 `test_connection()` 密码登录路径：
→ 调用 `_fresh_login_context()` → `OshwhubPlaywrightLogin.login()`
→ `_wait_for_login_form()` 找 Element UI 的 `.el-input__inner`
→ 页面已改为 **Ant Design**（`input.ant-input`, `button.ant-btn-primary`）
→ 找不到表单 → 返回 "登录失败"
→ 然后 fallback 到扁平 cookie 验证（问题1）

### 问题3：密码登录其实能工作但被选择器阻塞
用户密码 `13423796740` / `Lcsc@211211` 是对的
OshwhubPlaywrightLogin 的 `_find_input_by_placeholder`、`_fill_login_form` 用的都是 Element UI 选择器
页面实际是 Ant Design，找 `.el-input` 找不到，填不了表单

## SSO 登录流程（正确理解）
```
用户填写账号密码
  → OshwhubPlaywrightLogin 打开 passport.jlc.com/login
  → 点击「账号登录」tab
  → 填写 手机号/密码
  → 点击登录按钮
  → 如果验证码 -> 弹出阿里云滑块
  → 登录成功后 cookies 同时包含:
     - .jlc.com 域: JSESSIONID, SESSION, etc.
     - .oshwhub.com 域: 可能的 oshwhub 专属 cookie
  → 浏览器重定向到 oshwhub.com
  → SSO 自动通过 ✅
```

## 修改方案

### 文件1: `plugins/oshwhub_login.py`

**`_wait_for_login_form()`** — 当前行 133-167
- 添加 Ant Design 选择器检测：
  ```python
  ant_selectors = [
      "input.ant-input",
      ".ant-form-item input",
      "input[placeholder*='手机号码']",
      "input[placeholder*='邮箱']",
  ]
  ```
- Element UI 选择器保留做 fallback
- 增加日志输出：检测到的框架类型

**`_fill_login_form()`** — 当前行 332-406
- 添加 Ant Design 的输入框定位：
  - 用户名：`.ant-form-item` 内第一个非密码 input
  - 密码：`.ant-form-item` 内 `input[type='password']`

**`login()`** — 当前行 453+
- `_check_cookies_logged_in` 后增加：
  - 登录成功后保存 cookies_json（结构化 JSON 含 domain/path/secure）
  - 通过 `_save_cookies_to_db()` 保存到 DB

### 文件2: `core/credential_provider.py` — 扫码登录轮询

**`_scan_login_worker()` 行 661-663**
- 改成同时保存结构化 cookies_json：
```python
cookies_list = _ctx.cookies()  # Playwright 返回完整 cookie 对象
all_cookies_str = "; ".join(...)  # 保留扁平字符串向后兼容
cookies_json = json.dumps(cookies_list)  # 新增结构化 JSON
```
- 行 674-679 的 oshwhub 分支：
```python
if _login_engine == "oshwhub" and has_auth_cookies:
    sess["_poll_result"] = {
        "status": "logged_in",
        "cookies": all_cookies_str,
        "cookies_json": cookies_json,  # 新增！
        "image": sc_b64,
    }
```

### 文件3: `scripts/playwright_verify.py` 和 `scripts/playwright_verify_raw.py`

**playwright_verify.py** — 行 109-118（cookie 注入部分）
- 检查 cfg 中是否有 `cookies_json`：
```python
cookies_json = cfg.get("cookies_json", "")
if cookies_json:
    cookies_list = json.loads(cookies_json)
    ctx.add_cookies(cookies_list)  # 用原始 domain/path！
else:
    # fallback: 扁平字符串（丢失 domain 信息）
    domain = site_url.replace(...)
    for pair in cookie.split(";"):
        ...
```

**playwright_verify_raw.py** — 行 67-77（同样 cookie 注入）
- 同样支持 cookies_json 参数

### 文件4: `plugins/publisher_oshwhub.py`

**`test_connection()`** — 行 144-218
- cookie 路径（行 178-218）：
  - 先检查 `config` 中是否有 `cookies_json`
  - 如果有：使用结构化 cookie（保留 domain）
  - 否则降级到扁平字符串
- _fresh_login_context() 行 66 已调用 `_save_cookies_to_db()`
  - 行 71-106：已有 cookies_json 保存逻辑 ✅
  - 确认这个路径在 test_connection 正常触发

### 文件5: `routes/accounts/crud.py`

**`api_test_connection()`** — 行 391-469
- 降级路径（行 439-466）：playwright_verify_raw.py 传参增加 `cookies_json`
- 现有的 publisher test_connection 路径（行 420-436）：如果 publisher 返回 `cookies_json`，更新到 config 中

## 验证方式
1. 直接跑 `python3 -c "from plugins.oshwhub_login import OshwhubPlaywrightLogin; l=OshwhubPlaywrightLogin(); print(l.login('13423796740','Lcsc@211211'))"` → 应该返回 logged_in=True
2. 在 FS UI 点该账号「状态检测」→ `logged_in: true` 且有 cookies_json
3. 扫码登录流程 → cookie 保存为结构化格式
4. 删除旧账号重新添加 → test_connection 返回成功

## 参考
- `platform_reports/oshwhub_exploration_report.json` — 最新探索数据
- `platform_reports/oshwhub_login_capabilities.json` — 登录能力
- `docs/oshwhub-fix-handoff.md` — 旧版（已过时，看此文件）
