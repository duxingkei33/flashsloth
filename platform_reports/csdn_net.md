# 平台探索报告：CSDN（csdn.net）

> **探索时间**: 2026-07-05  
> **探索方式**: Playwright (Headless Chrome) + API 解析  
> **账号状态**: ✅ duxingkei 已登录（Cookie 2066字节，微信扫码登录）  
> **博客等级**: Level 1  
> **博客地址**: https://blog.csdn.net/duxingkei

---

## 1. 登录状态

| 项目 | 值 |
|------|-----|
| 用户名 | **duxingkei** |
| 登录方式 | 微信扫码登录（passport.csdn.net） |
| 登录方式选择 | 微信扫码 / 验证码登录 / APP扫码 / 其他登录 |
| Cookie 有效期 | ✅ 有效 |
| 博客等级 | 1（新用户）|
| VIP 状态 | ❌ 非VIP |
| 专家认证 | ❌ 否 |
| 文章数 | 0篇（新用户）|

## 2. 编辑器

### 2.1 基本信息

| 项目 | 值 |
|------|-----|
| 编辑器 URL | `https://editor.csdn.net/md/` |
| 编辑器类型 | Markdown（可切换富文本）|
| 标题限制 | **5~100 个字** |
| 代码高亮 | prism-atom-one-dark（可配置）|
| 图片上传 | ✅ 拖拽上传 + API上传 |
| 封面图 | ✅ 支持 |
| 水印 | ❌ 关闭 |
| 定时发布 | ✅ 支持 |
| 草稿 | ✅ 支持（showDraftPopUp=0）|
| AI 助手 | ✅ DeepSeek-V3.2/V4-Pro/V4-Flash |
| 历史版本 | ✅ 支持，每120秒自动保存 |
| 数学公式 | ✅ KaTeX |
| 图表 | ✅ Mermaid (甘特图等) |

### 2.2 编辑器字段

| 字段 | 类型 | 说明 |
|------|------|------|
| 标题 | `<input>` | placeholder="请输入文章标题（5~100个字）" |
| 正文 | Markdown `<textarea>` / 富文本 `<div contenteditable>` | 支持 Markdown 语法 |
| 分类 | 下拉选择 | 可创建最多10个自定义分类（当前0个） |
| 标签 | 输入框 | 自定义标签 |
| 封面图 | 上传组件 | 可选 |
| 文章类型 | 选项 | 原创 / 转载 / 翻译 |
| 摘要 | 自动生成 | AI 智能提取 |
| VIP 文章 | 开关 | 非VIP不可用 |

### 2.3 编辑器模板

| 模板名 | 说明 |
|--------|------|
| 学习计划模板示例 | 学习计划格式 |
| 系列文章模板 | 系列文章格式 |
| 记录bug模板 | Bug记录格式 |

## 3. 关键 API

| API 端点 | 方法 | 用途 |
|----------|------|------|
| `passport.csdn.net/v1/api/check/userstatus` | POST | 用户登录状态检查 |
| `bizapi.csdn.net/blog-console-api/v3/editor/getBaseInfo` | GET | 编辑器基础信息（用户信息、分类、设置等） |
| `bizapi.csdn.net/blog/phoenix/console/v1/write/get-config` | GET | 写作配置（VIP文章协议等）|
| `bizapi.csdn.net/blog/phoenix/console/v1/user/list-permission` | GET | 用户权限（AI、历史版本、草稿弹窗等）|
| `bizapi.csdn.net/blog/phoenix/console/v1/article/is-zero-article-user` | GET | 是否零文章用户 |
| `bizapi.csdn.net/blog/phoenix/console/v1/editModel/findPublicShowEditModels` | GET | 公开编辑模板列表 |
| `bizapi.csdn.net/blog/phoenix/console/v1/write-active/list` | GET | 写作活动列表 |
| `bizapi.csdn.net/blog/phoenix/console/v1/ai/assistant/models` | GET | AI 模型列表 |
| `bizapi.csdn.net/blog/phoenix/console/v1/ai/assistant/get-config` | GET | AI 助手配置 |

### 上传 API

| 项目 | 值 |
|------|-----|
| 上传组件 | `csdn-upload.js` (1.0.9) |
| 图片域名 | `img-blog.csdnimg.cn`, `latex.csdn.net` |
| 上传方式 | API 上传（待进一步抓取上传端点）|

### 发布 API

发布按钮文字: **「发布文章」**
发布选项: 需点击按钮后从弹出菜单获取详细发布选项（含分类、标签、类型选择）

## 4. 文章管理

| 项目 | 值 |
|------|-----|
| 管理页 URL | `https://mp.csdn.net/mp_blog/manage/article` |
| 文章状态 | 已发布 / 草稿 / 审核中 / 回收站 |
| 文章类型筛选 | 原创 / 转载 / 翻译 |
| 分类管理 | 自定义分类（最多10个）|

## 5. 发布限制

| 项目 | 限制 |
|------|------|
| 标题长度 | 5~100 字 |
| 图片大小 | 需通过 CSDN 图床上传（具体限制待确认）|
| 每日发布数 | 未明确（新用户可能有限制）|
| 审核 | 普通文章无需审核（VIP文章可能需审核）|
| 转载 | 需填写转载来源 |

## 6. FS 适配建议

### 发布器配置

```python
CSDN_PUBLISHER = {
    "name": "csdn",
    "display_name": "CSDN",
    "editor_url": "https://editor.csdn.net/md/",
    "manage_url": "https://mp.csdn.net/mp_blog/manage/article",
    "login_methods": [
        {"method": "qrcode", "label": "微信扫码登录", "icon": "📱"},
        {"method": "sms", "label": "验证码登录", "icon": "📞"},
        {"method": "app_qrcode", "label": "APP扫码登录", "icon": "📲"},
    ],
    "fields": [
        {"key": "title", "label": "标题", "max_length": 100, "required": True},
        {"key": "body", "label": "正文", "type": "markdown", "required": True},
        {"key": "category", "label": "分类", "type": "select", "api": "自定义"},
        {"key": "tags", "label": "标签", "type": "text"},
        {"key": "type", "label": "文章类型", "type": "select", 
         "options": ["原创", "转载", "翻译"]},
        {"key": "cover", "label": "封面图", "type": "image"},
        {"key": "summary", "label": "摘要", "type": "text"},
    ],
    "supports_draft": True,
    "supports_schedule": True,
    "supports_cover": True,
    "supports_tags": True,
    "image_upload": "api",
}
```

### 编译规则

```python
CSDN_RULE = {
    "format_type": "markdown",  # CSDN 原生支持 Markdown
    "allow_html": True,
    "allow_code_block": True,
    "max_title_length": 100,
    "image_upload": "api",
}
```
