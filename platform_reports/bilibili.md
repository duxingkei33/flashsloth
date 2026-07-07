# 平台探索报告：Bilibili（哔哩哔哩）

> **探索时间**: 2026-07-07
> **探索方式**: 综合（Playwright 登录页检测 + API 文档分析）
> **账号状态**: ❌ 未配置账号（需要用户提供 Cookie 或 QR 码登录）
> **站点**: https://www.bilibili.com
> **框架**: Next.js + Vite + jinkela（内部 SPA 框架）
> **对应适配版本**: v4.55

---

## 1. 登录状态

| 项目 | 值 |
|------|-----|
| 登录方式 | QR 码推荐（无需验证码）、密码登录（需极验 Geetest 滑块验证码）、第三方（QQ/微博/微信） |
| QR 码 API | `passport.bilibili.com/x/passport-login/web/qrcode/generate` + `/poll` |
| 密码登录 URL | `https://passport.bilibili.com/login` |
| 验证码 | 极验(Geetest)滑动验证码 — 高风控 |
| Cookie 需求 | `SESSDATA` + `bili_jct` + `DedeUserID` |
| 首页检测 API | `https://api.bilibili.com/x/web-interface/nav` — 返回 `isLogin` + `uname` |
| 推荐登录方式 | **QR 码扫码登录** — 无需触发风控验证码 |

### Cookie 结构

Bilibili 使用以下关键 Cookie 字段：
- `SESSDATA`: 会话令牌（必需）
- `bili_jct`: CSRF 保护令牌（必需，用于 POST 操作的 `csrf` 参数）
- `DedeUserID`: 用户 ID（必需）

Cookie 格式示例：
```
SESSDATA=abc123%2C...; bili_jct=def456...; DedeUserID=1234567; ...
```

### WBI 签名机制

Bilibili 部分 API 需要 WBI 签名（动态计算 `w_rid` 参数），但专栏创建/发布/图片上传 API 不需要。

## 2. 发布能力

### 2.1 专栏发布（图文）

Bilibili 专栏文章发布使用专用 API，**非 Playwright 浏览器操作**：

| 操作 | API 端点 | 方法 | 说明 |
|------|---------|------|------|
| 创建草稿 | `/x/article/creative/draft/addition` | POST form-data | 创建专栏草稿 |
| 提交发布 | `/x/article/creative/draft/submit` | POST form-data | 将草稿发布为公开文章 |
| 草稿列表 | `/x/article/creative/draft/list` | GET | 获取草稿列表 |
| 删除草稿 | `/x/article/creative/draft/delete` | POST | 删除草稿 |

**发布流程：** 两步 — 创建草稿 → 提交发布（支持 `save_as_draft` 仅存草稿不发布）

### 2.2 专栏分类

| ID | 分类 |
|----|------|
| 0 | 默认分类 |
| 1 | 动画 |
| 2 | 游戏 |
| 3 | 科技 |
| 4 | 生活 |
| 5 | 娱乐 |
| 6 | 影视 |

### 2.3 内容格式

Bilibili 专栏使用 **HTML 子集**（非 Markdown）。支持：
- `<h1>` ~ `<h3>` — 标题
- `<p>` — 段落
- `<strong>` / `<em>` — 粗体/斜体
- `<code>` — 行内代码
- `<img>` — 图片
- `<a>` — 链接

**不支持：** code block、表格、引用块、列表

### 2.4 视频发布

视频上传需要通过 Playwright 操作创作者中心：
- URL: `https://member.bilibili.com/platform/upload/video`
- 需要完整浏览器环境（多部分表单、大文件上传）
- **当前为预留状态**（需未来实现）

## 3. 图片上传

| 项目 | 值 |
|------|-----|
| API | `https://api.bilibili.com/x/article/creative/image/upload` |
| 方法 | `multipart/form-data POST` |
| 认证 | Cookie + CSRF (`bili_jct`) |
| 格式 | jpg, jpeg, png, gif, webp |
| 大小限制 | 推测 ≤10MB/文件 |
| CSRF 参数 | `csrf` 字段值 = `bili_jct` Cookie 值 |

上传成功后返回图片 URL（Bilibili 图床链接），可直接插入到专栏正文 `<img>` 标签。

## 4. 签到

| 项目 | 值 |
|------|-----|
| 支持签到 | ❌ 不支持 |
| 说明 | Bilibili 无公开签到 API，仅移动端有每日签到任务 |

## 5. 采集能力

| 操作 | API | 需要 |
|------|-----|------|
| 专栏列表 | `/x/space/article?mid={uid}&pn={page}&ps=30` | 目标用户 UID |
| 专栏详情 | `/x/article/viewinfo?id={cvid}` | 专栏 CV ID |
| 用户信息 | `/x/web-interface/nav` | 当前登录 Cookie |
| 评论采集 | 暂不支持 | — |

## 6. 适配状态

| 组件 | 状态 | 说明 |
|------|------|------|
| 探索报告 | ✅ 完整 | 登录 + 发布 + 上传 + 采集全部覆盖 |
| Publisher | ✅ 完整 | `plugins/publisher_bilibili.py` — API 方式发布、存草稿、上传图片 |
| SDK Adapter | ✅ 完整 | `sdk/adapters/bilibili.py` — 发布、采集、读帖、测试连接 |
| Login Plugin | ❌ 未创建 | 需要 QR 码 / 密码登录 Playwright 插件 |
| 账号配置 | ❌ 无 | 需要用户提供 Cookie 或通过 QR 码登录 |
| 平台配置 DB | ❌ 未写入 | 需要保存到 `platform_config` 表 |
| E2E 验证 | ❌ 未执行 | 需要有效 Cookie 后才能验证 |

## 7. 特殊注意事项

1. **WBI 签名**: 空间/推荐等 API 需要 WBI 签名（`w_rid` 参数），但**专栏发布 API 不需要**
2. **Geetest 风控**: 密码登录会触发极验滑动验证码，推荐使用 QR 码登录
3. **Cookie 有效期**: 未确认具体过期时间，建议定期刷新（每周一次）
4. **form-data 提交**: 专栏 API 使用 `application/x-www-form-urlencoded` 而非 JSON
5. **跨域问题**: CSRF token (`bili_jct`) 必须与 Cookie 中的 `bili_jct` 一致
6. **专栏编辑器 URL**: `https://member.bilibili.com/platform/upload/article`（需要登录）
