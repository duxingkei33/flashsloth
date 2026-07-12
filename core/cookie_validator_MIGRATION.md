# Cookie 验证器迁移指南

## 新增文件
`core/cookie_validator.py` — 统一 Cookie 验证器

## 所有被替换的旧代码

| 位置 | 函数/接口 | 替换方案 |
|------|----------|---------|
| `core/credential_provider.py:236-268` | `_check_auth_cookies(platform, cookies: list) -> bool` | → `verify_cookie(platform, cookies, input_type='list', phase='keyword')["valid"]` |
| `routes/accounts.py:1248-1264` | `_check_auth_cookies(platform, cookies: list) -> bool` | → `verify_cookie(platform, cookies, input_type='list', phase='keyword')["valid"]` |
| `core/credential_provider.py:781-857` | `verify_credential(platform, account_id, user_id) -> dict` | → 内部改用 `verify_cookie()` 调用 |
| `sdk/adapters/oshwhub.py:53-85` | `_has_valid_cookie() -> bool` | → `has_valid_cookie("oshwhub", self.cookie)` |
| `core/status_detector.py:748-790` | `PLATFORM_DETECTORS` + `detect_platform()` | → `verify_cookie()` 内部整合，**对外保留**（向后兼容） |

---

## 替换步骤

### Step 1: `core/credential_provider.py` — 替换 `_check_auth_cookies`

**操作**: 替换函数 + 更新调用方

**替换前** (line 234-268):
```python
# ─── Cookie 验证 ───────────────────────────────────────

def _check_auth_cookies(platform: str, cookies: list) -> bool:
    """按平台检查真正的认证 Cookie（UX2 铁律 — 禁止假阳性）"""
    cookie_map = {c["name"]: c.get("value", "") for c in cookies}
    if platform == "bilibili":
        return all(k in cookie_map for k in ["bili_jct", "SESSDATA", "DedeUserID"])
    if platform in ("discuz", "amobbs"):
        auth_val = cookie_map.get("auth", "")
        return bool(auth_val and auth_val.strip())
    if platform == "wechat":
        wx_keys = ["token", "fakeid", "slave_user", "slave_sid"]
        return any(k in cookie_map and cookie_map[k].strip() for k in wx_keys)
    auth_kw = ["auth", "token", "session", "login", "passport"]
    for c in cookies:
        for kw in auth_kw:
            if kw in c["name"].lower() and c.get("value", "").strip():
                return True
    return False
```

**替换后**:
```python
from flashsloth.core.cookie_validator import verify_cookie

# ─── Cookie 验证（委派到统一验证器）─────────────────────

def _check_auth_cookies(platform: str, cookies: list) -> bool:
    """按平台检查真正的认证 Cookie（委派到统一验证器）
    
    使用 phase='keyword' 避免网络请求，保持原有无网络开销特性。
    """
    return verify_cookie(platform, cookies, input_type="list", phase="keyword")["valid"]
```

同时更新 line 394 的调用方 `has_auth_cookies = _check_auth_cookies(platform, cookies)` — 这个调用无需改动（函数名和签名相同）。

### Step 2: `routes/accounts.py` — 替换 `_check_auth_cookies`

**操作**: 同上，替换函数体，删除 wechat 缺失的不一致问题。

**替换前** (line 1248-1264):
```python
def _check_auth_cookies(platform: str, cookies: list) -> bool:
    """按平台检查真正的认证 Cookie"""
    cookie_map = {c["name"]: c.get("value", "") for c in cookies}
    if platform == "bilibili":
        return all(k in cookie_map for k in ["bili_jct", "SESSDATA", "DedeUserID"])
    if platform in ("discuz", "amobbs"):
        auth_val = cookie_map.get("auth", "")
        return bool(auth_val and auth_val.strip())
    auth_kw = ["auth", "token", "session", "login", "passport"]
    for c in cookies:
        for kw in auth_kw:
            if kw in c["name"].lower() and c.get("value", "").strip():
                return True
    return False
```

**替换后**:
```python
from flashsloth.core.cookie_validator import verify_cookie

def _check_auth_cookies(platform: str, cookies: list) -> bool:
    """按平台检查真正的认证 Cookie（委派到统一验证器）

    使用 phase='keyword' 避免网络请求，保持原有无网络开销特性。
    """
    return verify_cookie(platform, cookies, input_type="list", phase="keyword")["valid"]
```

### Step 3: `core/credential_provider.py` — 更新 `verify_credential()`

**问题**: 现有代码 `detect_platform(platform, cookie=cookie)` **有 bug** — `cookie=cookie` 作为 keyword arg 被赋值给了 `site_url` 参数。

**替换前** (line 800-857):
```python
    from flashsloth.core.status_detector import detect_platform, PLATFORM_DETECTORS

    # ... 过期检查 ...

    # 使用平台特定的状态检测
    if platform in PLATFORM_DETECTORS:
        try:
            result = detect_platform(platform, cookie=cookie)  # ← BUG: cookie 传给 site_url
            logged_in = result.get("logged_in", False)
            return {"valid": logged_in, "message": "有效" if logged_in else "Cookie 已失效", "detail": result}
        except Exception as e:
            return {"valid": None, "message": f"验证异常: {str(e)[:80]}", "detail": {}}

    # 通用验证：尝试用 Cookie 访问平台首页
    try:
        import requests
        headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}
        resp = requests.get(
            f"https://{platform}.com" if "." not in platform else f"https://{platform}",
            headers=headers, timeout=10,
        )
        login_kw = ["login", "signin", "登录", "注册"]
        has_login_page = any(kw in resp.text[:2000].lower() for kw in login_kw)
        return {"valid": not has_login_page, "message": ..., "detail": ...}
    except Exception:
        pass
    return {"valid": None, "message": "无法验证（平台不支持自动检测）", "detail": {}}
```

**替换后**:
```python
    from flashsloth.core.cookie_validator import verify_cookie

    # ... 过期检查不变 ...

    # 使用统一验证器
    try:
        result = verify_cookie(
            platform=platform,
            cookie_input=cookie,
            input_type="string",
            phase="auto",  # 自动：优先 API 深度验证，异常时回退关键字
            site_url=cred.get("site_url", ""),
            username_hint=cred.get("username", ""),
        )
        return {
            "valid": result["valid"],
            "message": result["message"],
            "detail": result["detail"],
        }
    except Exception as e:
        return {"valid": None, "message": f"验证异常: {str(e)[:80]}", "detail": {}}
```

### Step 4: `sdk/adapters/oshwhub.py` — 替换 `_has_valid_cookie()`

**替换前** (line 53-85):
```python
    def _has_valid_cookie(self) -> bool:
        """检查是否有有效的 Cookie"""
        if not self.cookie:
            return False
        try:
            import requests
            for api in ["/api/user/profile", "/api/user/info"]:
                try:
                    r = requests.get(
                        f"{self.site_url}{api}",
                        headers={"Cookie": self.cookie, ...}, timeout=10,
                    )
                    if r.status_code == 200:
                        return True
                except: continue
            auth_keywords = ["auth", "token", "session", "oshwhub", "identity"]
            for item in self.cookie.split(";"):
                item = item.strip()
                if "=" in item:
                    name = item.split("=")[0].strip().lower()
                    for kw in auth_keywords:
                        if kw in name: return True
            return False
        except Exception: return False
```

**替换后**:
```python
    from flashsloth.core.cookie_validator import has_valid_cookie

    def _has_valid_cookie(self) -> bool:
        """检查是否有有效的 Cookie（委派到统一验证器）"""
        return has_valid_cookie(
            "oshwhub", self.cookie, site_url=self.site_url,
            username_hint=self.username,
        )
```

### Step 5: 所有 Adapter 的 `test_connection()` — 可选优化

各 Adapter 当前 `test_connection()` 只检查 `self.cookie` 非空即返回成功，可利用 `verify_cookie()` 做深度验证。

**以 juejin.py 为例**:
```python
# 替换前
def test_connection(self) -> dict:
    if not self.cookie:
        return {"success": False, "error": "Cookie 未配置"}
    return {"success": True, "status": "Cookie 已配置"}

# 替换后
from flashsloth.core.cookie_validator import verify_cookie_for_adapter

def test_connection(self) -> dict:
    result = verify_cookie_for_adapter("juejin", self.config)
    if not result["valid"]:
        return {"success": False, "error": result["message"]}
    return {"success": True, "status": result["message"], **result["detail"]}
```

---

## 向后兼容保证

1. **`_check_auth_cookies(platform, cookies: list) -> bool`** 签名不变 → 所有已有调用方无需修改函数签名
2. **`status_detector.PLATFORM_DETECTORS` / `detect_platform()`** 保留不动 → 其他地方的依赖不受影响
3. **`has_valid_cookie()`** 提供简化的布尔返回 → 适合 Adapter `_has_valid_cookie` 场景
4. **`verify_cookie_for_adapter()`** 直接从 config dict 取参 → 适合 Adapter `test_connection` 场景

---

## 验证清单

- [ ] `_check_auth_cookies` 在 credential_provider.py 和 routes/accounts.py 中函数体一致
- [ ] bilibili Playwright Cookie 校验：`bili_jct` + `SESSDATA` + `DedeUserID`
- [ ] discuz/amobbs 校验：`auth` 值非空
- [ ] wechat 校验：`token/fakeid/slave_user/slave_sid`
- [ ] oshwhub 专有校验：关键字包含 `oshwhub/identity/remember_user`
- [ ] csdn 校验：`UserName/user_info/CASTGC`
- [ ] zhihu 校验：`z_c0/d_c0`
- [ ] juejin 校验：`sessionid/USER_SESSION/monad`
- [ ] xianyu 校验：`_m_h5_tk/unb/cookie2`
- [ ] wordpress 校验：`wordpress_logged_in/wordpress_sec/wp-settings`
- [ ] API 级校验：bilibili/wechat/wordpress 现在有深度验证
- [ ] input_type='list' 支持（Playwright cookies list）
- [ ] input_type='string' 支持（"; " 分隔字符串）
- [ ] input_type='auto' 自动检测
