# 平台探索报告：知乎 (zhihu.com)

> **探索时间**: 2026-07-07 14:38 CST
> **探索方式**: Playwright 无头浏览器（非登录态公开页面）
> **账号状态**: ⏸ 无有效登录凭据
> **对应适配版本**: v4.65

## 1. 平台概览

| 项目 | 内容 |
|------|------|
| 平台类型 | 问答/专栏 SNS |
| 站点 URL | https://www.zhihu.com |
| 专栏编辑器 | https://zhuanlan.zhihu.com/write |
| 登录页 | https://www.zhihu.com/signin |
| 技术栈 | React SPA + 自家 API |
| 图片 CDN | picx.zhimg.com / pica.zhimg.com |
| 验证码 | NetEase CAPTCHA (NECaptchaValidate) |
| 登录方式 | 手机号+短信验证码（主要）/ App扫码 / 微信扫码 / Cookie粘贴 |

## 2. 登录状态

**当前**: ⏸ 无有效登录凭据

**登录方式（从探索确认）：**
- 手机号+短信验证码（主要方式，无密码字段）
- 隐藏字段 `NECaptchaValidate` = NetEase CAPTCHA 验证
- UI 有「忘记密码」按钮（说明有密码登录能力但非默认展示）
- 支持微信扫码、App扫码
- Cookie 粘贴（备选，从浏览器 F12 复制）

**登录页字段：**
| 字段 | 选择器 | 类型 | 说明 |
|------|--------|------|------|
| 手机号 | `input[name="username"]` | tel | 手机号输入 |
| 验证码 | `input[name="digits"]` | tel | 6位短信验证码 |
| CAPTCHA | `input[name="NECaptchaValidate"]` | hidden | NetEase 验证码令牌 |
| 登录按钮 | `button:has-text("登录/注册")` | submit | 提交登录 |

## 3. 编辑器结构

**未登录无法获取编辑器结构** — zhuanlan.zhihu.com/write 未登录时重定向到 signin。

**已知信息（从代码和历史数据）：**
- 知乎专栏使用 Draft.js 富文本编辑器
- 标题：contenteditable 区域或 TitleInput
- 正文：DraftEditor-editorContainer 内的 contenteditable div
- 图片上传：input[type='file'] → 上传到 picx.zhimg.com CDN
- 发布按钮：`button:has-text('发布')` 或 `'发布文章'`
- 存草稿：`button:has-text('存为草稿')` 或 `'保存草稿'`

## 4. 图片上传限制

| 项目 | 内容 |
|------|------|
| 上传方式 | Playwright set_input_files + 编辑器中触发上传 |
| 图片 CDN | https://picx.zhimg.com/... |
| 格式 | 常见格式（jpg/png/gif/webp） |
| 大小限制 | 未知（需登录验证） |
| 每日限额 | 未知（需登录验证） |
| 多图上传 | 支持（编辑器内逐张上传） |

## 5. API 端点

| 端点 | 用途 | 方式 |
|------|------|------|
| `https://api.zhihu.com/*` | 知乎主 API | 需要 Cookie/Authorization |
| `https://zhuanlan.zhihu.com/api/*` | 专栏 API | 需要 Cookie/Authorization |

未登录状态下无法探索到详细 API 端点。

## 6. 内容限制

| 项目 | 内容 |
|------|------|
| 标题最大长度 | 200 字符（来自 publisher 配置） |
| 正文格式 | Draft.js 富文本 / Markdown |
| 标签支持 | 不支持（单篇专栏无标签） |
| 封面支持 | 支持独立封面图 |
| 定时发布 | 不支持 |
| 文章分类 | 支持（专栏分组） |
| 审核机制 | 可能有自动审核 |

## 7. FS 适配现状

| 组件 | 状态 | 备注 |
|------|------|------|
| Publisher | ✅ 已实现 (317 行) | Playwright 方式，支持存草稿/发布/图片上传 |
| SDK Adapter | ❌ 未实现 | 需要登录凭证 |
| Login Plugin | ⏸ 已有登录能力数据 | 需要有效账号 |
| login_methods | ✅ 4种方法 | password/phone/qrcode/cookie |
| @register | ✅ 已注册 | 导入 admin.py |
| E2E 验证 | ⏸ 待验证 | 缺有效登录凭据 |
| 签到 | ❌ 未实现 | 需要登录凭证 |
| 评论采集 | ❌ 未实现 | 需要登录凭证 |

## 8. 待完成

- [ ] 用户提供知乎账号密码/手机号
- [ ] 通过统一弹窗 QR 码完成登录
- [ ] E2E 验证完整发布流程（存草稿）
- [ ] 创建 SDK Adapter (sdk/adapters/zhihu.py)
- [ ] 实现签到功能
- [ ] 探索编辑器中图片上传的具体限制
