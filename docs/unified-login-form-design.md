# 🏗️ 统一登录表单 + 验证码归一化 架构设计

> **PM 设计文档** — 子AI实现依据
> 目标：让添加账号弹窗动态适配每个平台的真实登录能力

---

## 一、当前问题

| 问题 | 表现 | 根因 |
|------|------|------|
| site_url 未自动填写 | 用户每次都要手动输入论坛地址 | 前端没读 exploration 中的 `login_url` |
| 登录方法硬编码 | 所有平台显示同一套方法 | `renderMethodFields` 未按 `detected` 过滤 |
| OAuth 未细分 | B站第三方显示一个Tab，不显示QQ/微博/微信 | 前端未处理 `oauth.providers[]` |
| 验证码未归一化 | 阿莫论坛的点击验证码没统一处理 | 无统一验证码接口 |
| 探索数据闲置 | `platform_reports/*_login_capabilities.json` 有完整数据但前端没充分用 | 前后端数据管道不完整 |

---

## 二、数据流设计

```
platform_reports/
  *_login_capabilities.json     ← 探索数据源
        ↓
  routes/accounts.py
  api_platform_login_capabilities()  ← 增强此API
        ↓
  templates/accounts.html
  onAddAccount() → 动态渲染         ← 改造前端
```

---

## 三、API 增强（后端）

### 现有 API: `GET /api/platform/<platform>/login-capabilities`

**增强后返回格式：**

```json
{
  "success": true,
  "platform": "bilibili",
  "login_url": "https://www.bilibili.com/",
  "site_url_default": "https://www.bilibili.com",
  "login_methods": [
    {
      "method": "qrcode",
      "label": "扫码登录",
      "detected": true,
      "sub_types": [{"id": "wechat", "label": "微信扫码", "detected": true}],
      "description": "打开B站登录页截图，用手机扫码后自动捕获Cookie"
    },
    {
      "method": "password",
      "label": "账号密码登录",
      "detected": true,
      "fields": ["username", "password"],
      "captcha": {
        "has_captcha": false,
        "type": null,
        "description": null
      }
    },
    {
      "method": "phone",
      "label": "手机验证码登录",
      "detected": true,
      "fields": ["phone"]
    },
    {
      "method": "oauth",
      "label": "第三方账号登录",
      "detected": true,
      "providers": [
        {"id": "qq", "label": "QQ登录", "icon": "🐧"},
        {"id": "weibo", "label": "微博登录", "icon": "📣"},
        {"id": "wechat_oauth", "label": "微信登录", "icon": "💬"}
      ]
    },
    {
      "method": "cookie",
      "label": "Cookie粘贴（调试）",
      "detected": true,
      "fields": ["cookie"]
    }
  ],
  "captcha_info": {
    "has_captcha": false,
    "types": [],
    "note": ""
  }
}
```

### 新增 API: 验证码截屏

`GET /api/captcha/<platform>/screenshot`
- 启动 Playwright 打开平台登录页
- 截图验证码区域
- 返回 base64 图片 + 验证码类型 + 描述

`POST /api/captcha/<platform>/verify`
- 提交用户输入的验证码
- 返回验证结果

---

## 四、前端改造

### 4.1 site_url 自动填充

`onAddAccount()` 获取 API 数据后，自动填充 site_url 输入框：
```javascript
if (data.site_url_default) {
    document.querySelector('input[name="cfg_site_url"]').value = data.site_url_default;
}
```

### 4.2 登录方法 Tab 渲染

`renderLoginCapabilityTabs()` 改为仅显示 `detected: true` 的方法：

| 方法 | Tab 显示 | 字段 | 说明 |
|------|---------|------|------|
| `password` | 🔑 密码登录 | username + password | 标准表单 |
| `phone` | 📱 手机验证码 | phone | 手机号输入 |
| `qrcode` | 📷 扫码登录 | 按钮 + 二维码截图 | 显示二维码+倒计时 |
| `oauth` | 🔗 第三方登录 | 按钮列表 | 每个 provider 一个按钮 |
| `cookie` | 🍪 Cookie粘贴 | textarea | 调试用，优先级最低 |

### 4.3 OAuth Provider 渲染

当 method === 'oauth' 时，遍历 `providers[]` 每个显示一个按钮：
```
[ 🐧 QQ登录 ] [ 📣 微博登录 ] [ 💬 微信登录 ]
```

### 4.4 验证码统一区域

在登录表单下方固定一个 CAPTCHA 区域：
```
┌─────────────────────────────┐
│  🔐 验证码验证               │
│  ┌─────────────────────┐    │
│  │   验证码图片截图      │    │
│  └─────────────────────┘    │
│  [输入验证码] [提交验证]     │
│  💡 提示文字                 │
└─────────────────────────────┘
```

- 截图来自 `GET /api/captcha/<platform>/screenshot`
- 输入框 + 提交按钮
- 有验证码的平台才显示（`captcha_info.has_captcha === true`）
- 无验证码的平台隐藏此区域

---

## 五、分步实现

### Step 1: 后端增强（routes/accounts.py）

**改 `api_platform_login_capabilities()`**：
1. 从 `_load_login_capabilities(platform)` 读取完整 JSON
2. 读取 `login_url` 作为 `site_url_default`
3. 按 method 分类处理：
   - `password` → fields: ["username", "password"] + 带 captcha 信息
   - `phone` → fields: ["phone"]
   - `qrcode` → 保留 sub_types
   - `oauth` → 展平 providers 成 `[{id, label, icon}]`
   - `cookie` → fields: ["cookie"]
4. 把 `raw_detection` 中的 captcha 信息映射到 `captcha_info`
5. 标记 `detected: false` 的方法不返回（不展示）

**新加 `api_captcha_screenshot()`**：
1. 检查 platform 是否有 captcha（从 login_capabilities JSON 读取）
2. 用 Playwright 打开登录页、截图验证码区域
3. 返回 base64 图片

### Step 2: 前端改造（templates/accounts.html）

**onAddAccount() 改动**：
1. 拿到 API 返回后，如果有 `site_url_default` 自动填充
2. 过滤只显示 `detected: true` 的方法
3. 调用新的渲染函数

**renderLoginCapabilityTabs() 增强**：
1. 每个 Tab 只显示 detected 的方法
2. 新增 oauth 渲染分支 → 显示 provider 按钮网格
3. 新增统一 captcha 区域

**renderMethodFields() 增强**：
1. password 方法：如果 `captcha.has_captcha`，显示验证码区域
2. oauth 方法：显示 provider 按钮
3. site_url 已有预设值的情况下自动填充

---

## 六、验证清单

| # | 验证项 | 方法 |
|---|--------|------|
| 1 | 选B站 → 显示 扫码/密码/手机/第三方(QQ/微博/微信)/Cookie | 浏览器实测 |
| 2 | 选CSDN → 显示 密码/扫码/第三方(QQ/GitHub/Google/微信)/Cookie | 浏览器实测 |
| 3 | 选阿莫论坛 → 显示 扫码/密码/Cookie，有验证码提示 | 浏览器实测 |
| 4 | 选阿莫论坛 → site_url 自动填为 amobbs.com | 浏览器实测 |
| 5 | 有验证码的平台 → 显示验证码截图区域 | 浏览器实测 |
| 6 | E2E-02 账号管理测试全通过 | 跑测试脚本 |
