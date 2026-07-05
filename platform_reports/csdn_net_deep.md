# CSDN 编辑器深入探索补充报告（Playwright 验证）

> **探索时间**: 2026-07-05  
> **探索方式**: Playwright (Headless Chrome) — 严格浏览器模拟  
> **账号状态**: ✅ **已登录**（用户名: `AI辅助软件开发伍斌`，Cookie 有效 2066 字节）  
> **站点**: https://www.csdn.net  
> **编辑器**: https://editor.csdn.net/md/

---

## 1. 登录验证

| 项目 | 值 |
|------|-----|
| 首页登录态 | ✅ 已登录，显示用户名 `AI辅助软件开发伍斌` |
| Cookie 有效期 | ✅ 有效（20秒内加载编辑器） |
| Cookie 格式 | 分号分隔字符串，domain: `.csdn.net` |
| 获取方式 | 微信扫码登录（之前） |

## 2. Markdown 编辑器详情

### 标题输入
- 选择器: `input[placeholder*='标题']` 或 `#articleTitle`
- placeholder: `请输入文章标题（5~100个字）`
- ✅ 可以 `fill()` 写入

### 编辑器正文区
- **Markdown 模式**: `<PRE class='editor__inner markdown-highlighting'>`
- **编辑器容器**: `<DIV class='editor'>`
- 编辑器区域数: 2个
- ✅ 文本可写入

### 工具栏按钮（完整列表）
```
保存草稿、发布文章、导入、导出、Markdown、使用富文本编辑器
代码块、代码运行、列表、无序列表、引用、待办事项
AI、扩写、内容建议、投票
同步滚动、打字机模式
历史版本、更多插入、更多操作、撤销、取消
填写标题才可自动保存、我知道了
```

### 关键按钮
| 功能 | 存在 | 说明 |
|------|------|------|
| **保存草稿** | ✅ | 支持存草稿 |
| **发布文章** | ✅ | 提交发布 |
| **导入/导出** | ✅ | 支持 Markdown 文件导入导出 |
| **富文本切换** | ✅ | MD ↔ 富文本可切换 |
| **AI 助手** | ✅ | 扩写、内容建议 |
| **图片上传** | ✅ | 通过"更多插入"或拖拽（待确认精确选择器）|
| **历史版本** | ✅ | 每120秒自动保存 |
| **分类/标签** | ✅ | 下拉选择，需进一步确认选择器 |

### 分类/类型
- 存在代码语言选择器（`code-selector-box`）
- 分类和标签需进一步定位选择器

## 3. CSDN 博客

| 项目 | 值 |
|------|-----|
| 博客地址 | `https://blog.csdn.net/duxingkei` |
| 博客等级 | Level 1 |
| 文章数 | 0（新用户） |

## 4. FS 适配建议

### 发布流程（Playwright）
1. 注入 Cookie（domain: `.csdn.net`）
2. 导航到 `https://editor.csdn.net/md/?not_checkout=1`
3. 等待编辑器渲染（需等 ~5-8 秒）
4. 填写标题：`input[placeholder*='标题']`
5. 写入正文：通过 editor API 或直接操作 DOM
6. 设置分类/标签
7. 点击"保存草稿"或"发布文章"
8. 发布时可能弹出设置对话框

### 已确认可用的选择器
```python
title_selector = "input[placeholder*='标题']"
editor_selector = ".editor__inner.markdown-highlighting"  # Markdown 模式
save_btn = "button:has-text('保存草稿')"
publish_btn = "button:has-text('发布文章')"
```
