# 平台探索报告：OSHWHub（立创开源硬件平台）

> **探索时间**: 2026-07-05  
> **探索方式**: Playwright (Headless Chrome) — 严格浏览器模拟  
> **账号状态**: ✅ **已登录**（首页显示用户名 `jim`，无登录/注册链接）  
> **站点**: https://oshwhub.com  
> **框架**: Next.js + Ant Design (React SPA, RSC 流式渲染)  
> **WAF**: ✅ Cloudflare（API 全部 418 阻挡 — 必须全 Playwright）

---

## 1. 登录状态

| 项目 | 值 |
|------|-----|
| 登录方式 | 嘉立创统一登录（passport.jlc.com） |
| 验证码 | 可能触发滑块验证码（阿里云滑块） |
| Cookie 有效期 | ✅ 有效（存储在 DB `platform_accounts.config_json` 的 `cookie` 字段） |
| 首页检测 | ✅ 用户名 `jim` 出现在 `home_user-avatar` 元素 |
| 登录/注册链接 | 0 个（已登录状态） |
| Cookie 格式 | 分号分隔的 cookie string，需解析为 Playwright 格式（domain: `.oshwhub.com`） |

> **注意**: Cookie 存储在 `config_json` 字段的 JSON 字符串 `cookie` 键下，不是独立列。需 `json.loads(config_json)["cookie"]` 提取。

### Cookie 包含的域
- `.oshwhub.com`（主要）
- `.jlc.com`（嘉立创统一认证）
- 以及其他第三方统计/追踪 cookie

## 2. 页面结构

### 导航栏
- `head_user-notifications__J3hIR` — 通知图标
- `home_user-avatar__M_KIK` — 用户头像+用户名
- `head_sign__5WmU3` — 签到记录链接（指向 `/sign_in`）

### 首页
- 可见导航：首页、开源广场、扩展广场、活动、大学计划
- 快速导航：星火计划、泰山派、STC、Arduino 等
- 推荐工程（Ant Design Card 渲染）

## 3. 项目创建页（`/project/create`）

| 字段 | ID/选择器 | 类型 | 说明 |
|------|-----------|------|------|
| 工程名称 | `#name` | `<input>` | placeholder="请输入工程名称" |
| 工程简介 | `#introduction` | `<textarea>` | placeholder="请填写工程简介，不超过100字" |
| 总成本 | `input[placeholder*='总成本']` | `<input>` | placeholder="请填写总成本"（无 id） |
| 开源许可证 | `#license` | `<input>` | **Ant Design Select**（`rc_select_3`，不是原生 `<select>`） |
| 用户UUID | `#user_uuid` | `<input>` | 隐藏字段 |
| 来源 | `#origin` | `<input>` | 隐藏字段 |
| 正文 | TinyMCE | 富文本编辑器 | ✅ 确认存在，95个 `.tox-*` 子元素 |

### TinyMCE 工具栏按钮
`上传图片`、`使用模板`、`编辑`、`查看`、`插入`、`格式`、`段落`、`12pt`

### 提交按钮
- `创建`（文字为"创 建"，可能有空格）

### 许可证选择器
- Ant Design Select (`#license`)，非原生 `<select>`
- 选项列表需通过 Ant Design Select 下拉交互获取（点击 #license → 弹出选项面板）

## 4. 签到功能

| 项目 | 值 |
|------|-----|
| 签到页 URL | `/user/signin` |
| 签到按钮 | ❌ **页面上无签到按钮** |
| 签到记录 | `head_sign__5WmU3` → `/sign_in`（签到历史记录页） |
| 观察 | 签到入口可能不在 `/user/signin`，可能在用户中心或首页顶部 |
| 结论 | 需进一步确认签到实际入口位置 |

> 待确认：签到入口可能在首页右上角头像下拉菜单、或首次访问时的弹窗/提示

## 5. 作品管理（`/write/works`）

| 项目 | 值 |
|------|-----|
| 当前作品数 | 0 |
| 页面布局 | 左侧用户信息（关注/粉丝/获赞/积分），右侧"TA的作品"标签页（工程/文章/创意） |
| 操作按钮 | 无编辑/删除按钮（因为无作品） |
| 底部链接 | 政策条款、隐私政策、软件版本等 |

### 用户资料区
- "暂无个人简介"
- 关注: 0 / 粉丝: 0 / 获赞: 0 / 积分: 0

## 6. 评论区

| 项目 | 值 |
|------|-----|
| 存在评论 | 待确认（未找到公开项目链接） |
| 待验证 | 需找到真实项目页并检查评论区组件 |

> 探索页项目卡片可能是 Ant Design Card + React Router 链接，选择器需用 `[class*='ant-card'] a[href*='/project/']`

## 7. API 端点（全部被 WAF 阻挡 418）

所有 API 端点返回 418 — 无法通过 API 直接交互。

## 8. FS 适配建议

### Cookie 注入流程
```python
# 从 DB 读取
config = json.loads(row["config_json"])
cookie_str = config["cookie"]
# 解析为 Playwright cookie
cookies = []
for pair in cookie_str.split(";"):
    name, value = pair.strip().split("=", 1)
    cookies.append({"name": name, "value": value, "domain": ".oshwhub.com", "path": "/"})

# 注入
await context.add_cookies(cookies)
```

### 发布器配置
```python
OSHWHUB_PUBLISHER = {
    "name": "oshwhub",
    "display_name": "立创开源硬件平台",
    "editor_url": "/project/create",
    "manage_url": "/write/works",
    "login_methods": [
        {"method": "password", "label": "密码+验证码登录", "icon": "🔑"},
        {"method": "cookie", "label": "Cookie粘贴", "icon": "🍪"},
    ],
    "fields": [
        {"key": "name", "label": "工程名称", "required": True, "selector": "#name"},
        {"key": "introduction", "label": "工程简介", "max_length": 100,
         "selector": "#introduction"},
        {"key": "cost", "label": "总成本", "required": False,
         "selector": "input[placeholder='请填写总成本']"},
        {"key": "license", "label": "开源许可证", "type": "antd_select",
         "selector": "#license"},
        {"key": "body", "label": "正文", "type": "richtext", "editor": "tinymce"},
    ],
    "supports_draft": True,
    "supports_cover": True,
    "signin_url": "/user/signin",
    "image_upload": "playwright",
    "cookie_field": "config_json.cookie",  # Cookie 在 config_json 的 cookie 字段
}
```

### 签到适配
- Playwright 打开 `/user/signin`
- 当前未发现签到按钮，需进一步确认入口
- 备选入口检查：首页顶部、用户头像下拉菜单

### 发布适配（Playwright 全流程）
```python
# 1. 读取 Cookie 注入 context
# 2. 打开 /project/create
# 3. 填写 #name （工程名称）
# 4. 填写 #introduction （工程简介）
# 5. 填写 input[placeholder='请填写总成本']
# 6. 点击 #license → 从 Ant Design 下拉选择许可证
# 7. 操作 TinyMCE 编辑器（tox-tinymce iframe）
# 8. 点击"创建"按钮提交
```

## 9. 待验证项

- [ ] 签到实际入口（不在 `/user/signin`）
- [ ] 评论区具体交互方式
- [ ] 许可证 Ant Design Select 选项列表
- [ ] TinyMCE 编辑器具体 iframe 交互（插入图片/文字）
- [ ] 存草稿/发布流程（需先有作品）
- [ ] 作品管理页的编辑功能（需先创建项目）
- [ ] 确认 `/explore` 页面项目链接选择器（Ant Design Card）
