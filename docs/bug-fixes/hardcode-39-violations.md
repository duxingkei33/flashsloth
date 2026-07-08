# Bug #7: 39 项硬编码违规

| 属性 | 值 |
|------|-----|
| 版本 | v5.18 |
| 日期 | 2026-07-08 |
| 严重度 | 🔴 结构性 |
| 模块 | 全项目 |
| 关联铁律 | #28 一切工作必须数据驱动, #36 单登录类多平台隔离 |

## 症状
新增同系平台（如 Mydigit）时，多处功能异常：site_url 错误跳到 amobbs.com、登录引擎路由错误、验证码提示显示错误的平台名。

## 根因
全项目扫描发现 39 处硬编码违规，分为以下几类：

| 类别 | 数量 | 典型例子 |
|------|:---:|---------|
| 硬编码平台名 | 13 | `DISCUZ_PLATFORMS = {"amobbs", "discuz"}` 不包含 mydigit |
| 硬编码 site_url | 8 | `_get_default_site_url()` 回退到 `"https://www.amobbs.com"` |
| 硬编码登录引擎 | 6 | `if platform == "amobbs" → AmobbsPlaywrightLogin` |
| 硬编码验证码判断 | 5 | 前端 `if platform === 'amobbs'` 显示验证码提示 |
| 硬编码路由 | 4 | 12个专属路由 `/api/amobbs/login/*` 等 |
| 硬编码错误消息 | 3 | `"Amobbs 登录失败"` 而非 `"{platform} 登录失败"` |

## 修复策略
采用"数据驱动分发"模式，每项修复分三步：
1. **从探索数据读取** — platform_exploration 表的 engine/architecture/site_url 字段
2. **动态推导** — `_get_engine_for_platform()` 从 DB 查询引擎类型
3. **删除硬编码** — 移除 _ENGINE_FALLBACK_MAP、DISCUZ_PLATFORMS 等硬编码常量

## 验证
- 每个修复后跑 E2E 隧道测试
- 验证 Mydigit 和 Amobbs 两个同系平台不互相干扰
- 验证码提示从 `engine` 字段动态判断

## 教训
- **永远不要假设只有两个平台** — 同系平台会不断增加
- **硬编码平台名是最敏感的红线** — 每次新增平台都会触发一连串问题
- **数据驱动需要全链路贯彻** — 后端+前端+模板 三层都要数据驱动
- **修复后必须验证 API 返回的字段** — 原 API 缺 engine 字段导致修复后又出问题

## 关联
- 铁律 #28: 一切工作必须数据驱动
- 铁律 #36: 单登录类多平台隔离
- 铁律 #39: 新增同系平台必须创建完整探索数据
- 参考: `references/hardcode-audit-procedure.md`