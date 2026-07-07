# 平台探索报告：douban.com（豆瓣）

> **探索时间**: 2026-07-08 01:06 CST
> **探索方式**: Playwright 无登录态预探索
> **账号状态**: ❌ 无登录凭据
> **站点**: https://www.douban.com
> **框架**: 传统 HTML（非 SPA）
> **分类**: social（社交/社区）

## 1. 登录状态
| 维度 | 结果 |
|------|------|
| 密码登录 | ❌ 不支持（无密码字段） |
| 手机验证码登录 | ✅ 默认Tab，字段：手机号 + 验证码 |
| QR码扫码登录 | ✅ 支持（豆瓣App扫码） |
| 第三方 OAuth | ❌ 微信/微博/QQ 未检到 |
| 验证码/CAPTCHA | ✅ 有（注册/敏感操作） |
| 极验 Geetest | ❌ 未发现 |
| 登录 URL | `https://accounts.douban.com/passport/login` |

**发现：** 豆瓣登录采用手机号+短信验证码为主要方式，同时支持 QR 码扫码登录。无传统密码字段。

## 2. 发布能力
| 内容类型 | 编辑器 URL | 登录要求 | 说明 |
|----------|-----------|---------|------|
| 写日记 | `/note/create` | ✅ 需登录 | 日记发布 |
| 创建小组 | `/group/create` | ❌ 未登录可访 | 创建小组表单 |
| 创建豆列 | `/doulist/create` | ❌ 未登录可访 | 收藏列表创建 |
| 线上活动 | `/online/create` | ✅ 需登录 | 活动创建 |
| 广播/发帖 | `/` | ✅ 需登录 | 社交动态 |

## 3. API 端点发现（15个）

### 认证类
- `accounts.douban.com/passport/login_popup`

### frodo 类（追踪/展示）
- `frodo.douban.com/rohirrim/tracking/impression`（商品/书籍追踪）

### rexxar 类（移动端 API）
- `m.douban.com/rexxar/api/v2/search/hots` — 热搜
- `m.douban.com/rexxar/api/v2/subject/recent_hot/movie` — 热门电影
- `m.douban.com/rexxar/api/v2/subject/recent_hot/tv` — 热门电视

### 其他
- `book.douban.com/j/home/ebooks` — 电子书推荐

## 4. 技术栈分析
- 传统 HTML 页面（非 React/Vue SPA）
- 使用 accounts.douban.com 统一认证子域名
- frodo 子域名用于追踪/数据服务
- rexxar 子域名提供 REST API

## 5. 适配评估

| 需求 | 可行性 | 备注 |
|------|--------|------|
| PC端登录适配 | ✅ 可行 | QR码扫码（推荐）+ 手机验证码登录 |
| PC端发布（日记） | ✅ 需登录后 | 日记编辑页 `/note/create` |
| PC端发布（小组） | ⏸ 需评估 | 小组发帖需登录 |
| 公开 API | ⏸ frodo/rexxar 可用 | 需要认证 token |
| 签到能力 | ❌ 未确认 | 豆瓣无签到概念 |
| 图片上传 | ⏸ 未测试 | 需登录后诊断 |

## 6. 适配建议
- **推荐登录方式**: QR码扫码登录（无验证码），兜底手机验证码
- **发布能力**: 日记 (note) → 支持存草稿（未登录态保存本地）+ 发布
- **小组发帖**: 可考虑支持，但需凭证
- **豆列创建**: 无需登录可访问，最易适配

## 7. FLASHSLOT 适配差距清单
- [ ] 登录适配（QR码 + 手机验证码）
- [ ] Publisher 开发（日记 + 豆列 + 小组发帖）
- [ ] 日记存草稿
- [ ] 签到（如不适用则标记）
- [ ] E2E 验证

## 8. 注意事项
- 豆瓣无密码登录字段
- 日记/广播发布需要有效登录 Cookie
- 无签到机制
- 豆瓣的反爬主要通过 Cookie 和 IP 频率控制
