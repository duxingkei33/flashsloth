# 平台探索报告：mydigit.cn（数码之家）

> **探索时间**: 2026-07-05 21:34  
> **探索方式**: Playwright (Headless Chrome)  
> **账号状态**: ✅ duxingkei 已登录  
> **对应适配版本**: v4.18.0

---

## 1. 登录状态

- 用户名: **duxingkei**
- Cookie 有效期: 有效（登录状态 True）
- 发帖权限: ✅ 有

## 2. 论坛公告

> 20周年重磅调整：取消登录阅览积分！(2026-7-1)

## 3. 编辑器结构

| 项目 | 值 |
|------|-----|
| 编辑器类型 | 富文本 iframe (`e_iframe`) |
| 标题最大长度 | 80 字符 |
| 主题分类 | 不需要 |
| 标签字段 | 无 |

## 4. 上传限制

### 4.1 文件格式

| 类型 | 允许的格式 |
|------|-----------|
| **图片** | jpg, jpeg, png, gif |
| **附件** | zip, rar, pdf, mp4 |
| **accept 属性** | `.jpg,.jpeg,.gif,.png,.zip,.rar,.pdf,.mp4` |

### 4.2 大小限制

- **图片最大**: **9MB**
- **其他附件**: 未明确标注（应与图片同限）

### 4.3 每日限额

- **今日还能上传**: **200 个**文件

### 4.4 上传 API

```
POST https://www.mydigit.cn/misc.php?mod=swfupload&action=swfupload&operation=upload&fid={fid}
```
参数: `uid`, `hash`, `Filedata` (multipart/form-data)

## 5. 版规要点

- 倡导文明用语，共创良好交流环境
- **禁止**发布社政/恐暴/反动/色情及违反国家法律法规的内容
- 违规者会被禁言
- ⚠️ **使用 emoji 表情可能造成内容丢失**

## 6. FS 适配状态 (v4.18.0)

| 适配项 | 状态 |
|--------|------|
| 图片格式校验（限定 jpg/png/gif） | ✅ `allowed_extensions` 可配置 |
| 图片大小上限 9MB | ✅ `max_image_size` 可配置，mydigit 默认 9MB |
| 每日上传限额 200/天 | ✅ 后端识别拒绝错误 |
| 附件格式 zip/rar/pdf/mp4 | ✅ `allowed_extensions` 已含 |
| Emoji 警告 | ✅ 检测到 emoji 时提示 |
| 标题截断 80 字符 | ✅ Discuz 通用 |
| 全流程干跑验证（存草稿） | ❌ **未做** |

## 7. 待完成

- [ ] 全流程干跑：用真实文章模拟填写→上传图片→存草稿→通知用户
