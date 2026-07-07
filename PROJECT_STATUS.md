# 🦥 FlashSloth 项目状态
> 最后更新：2026-07-07 22:55 | PM: duxingkei | 铁律: fs-iron-rules

> ⚠️ 本文档通过梳理全部聊天记录 + 最新需求对齐生成

## 🎯 核心目标
统一多平台内容发布与管理平台（个人数字资产中心），保持轻量、稳定、不膨胀。

## 📍 当前阶段
**维护期 v4.91** — QR码优先级优化 + site_url传透修复

---

## 📋 历史需求对照（按最新要求对齐）

### ✅ 已完成的重大模块

| 模块 | 状态 | 说明 |
|------|------|------|
| 通知网关22Provider移植 | ✅ | 飞书/企微/Telegram/Discord/Slack/钉钉/微信等全部完成 |
| 闲鱼V2发布器 | ✅ | MTOP API链路完整移植，含签名/风控/限流/CDN/AI类目 |
| 平台发布器（7个） | ✅ | Discuz/CSDN/OSHWHub/知乎/B站/掘金/微信 |
| 登录弹窗三种方式 | ✅ | 密码/QR码/短信验证码，全部通过验收 |
| QR码线程安全修复 | ✅ | 后台线程模式，22/22测试通过 |
| 短信验证码登录 | ✅ | phone_login跨线程修复，支持CSDN/知乎/掘金/B站 |
| 智能版块匹配引擎 | ✅ | forum_registry + 全平台匹配 |
| 探索页重构 | ✅ | 折叠式+能力配置+标签管理 |
| 三层状态检测 | ✅ | 缓存→API轻量→Playwright |
| 浏览器自死锁修复 | ✅ | threading.Lock不可重入→v4.64 |
| 验证码+进度条登录 | ✅ | 5步进度条+Amobbs核验 |
| 批量文章操作 | ✅ | 多选删除/发布 |
| 铁律skill固化 | ✅ | 6章完整：禁止/必须/流程/备份/数据流/违规记录 |
| 项目架构梳理文档 | ✅ | PROJECT_ARCHITECTURE_REVIEW.md 645行 |
| Claude PM协作模式 | ✅ | 我管架构，Claude写代码 |
| 定时任务清理省token | ✅ | 暂停3个假阳性cron，省~145次/天 |

### ❌ 已取消/不做的

| 任务 | 原因 |
|------|------|
| FRPC隧道自动管理 | 铁律禁止，frpc独立守护 |
| browser-use/video-use集成FS | 仅学技能，不与FS绑定 |
| 闲鱼AutoReply运行/安装 | 只学代码思路移植 |
| CSDN签到修复 | 用户说不做了 |
| 视频下载模块 | 不与FS绑定 |

### 🔄 正在进行/待办

**P0 — 紧急**
- [ ] **AI趋势日报飞书推送修复** — Claude正在修
- [x] **login-capabilities refresh site_url传透** — ✅ 已完成（自动补 https:// 前缀）
- [x] **QR码全平台优先级#1** — ✅ 已修复（登录方式首选项改为扫码登录）
- [ ] 监控flashsloth-pm-daily-progress首次运行（明早9点）

**P1 — 重要**
- [ ] 验证flashsloth-exploration脚本是否完全修复
- [ ] 评估剩余P0看门狗是否继续保留

**P2 — 优化**
- [ ] 发布前检查Cookie过期（代码改动，不动DB）
- [ ] 清理api_platforms_list死代码
- [ ] forum_registry读DB（JSON/DB双轨）

---

## 📊 用户铁律汇总（来自聊天记录）

| 铁律 | 来源 | 说明 |
|------|------|------|
| 不扩数据库 | 本会话最新要求 | 只用flashsloth.db |
| 不扩服务 | 本会话最新要求 | 不下包、不加新进程 |
| 不动frpc | 铁律#4 | frpc独立守护 |
| 不动用户密码 | 铁律#4 | admin_redacted密码不变 |
| 闲鱼只学不装 | 本会话最新要求 | 只移植代码模式 |
| 密码特殊字符 | 铁律P1-P5 | `&`等需要urlencode |
| site_url传透 | 铁律#12 | 禁止硬编码 |
| 永不同时多改 | 铁律#6 | 增量E2E：改→测→过 |
| 不反问 | 铁律#1 | 自己决策执行完报告 |
| 高峰省token | 铁律E1-E4 | 9-11/14-17禁止AI任务 |
| PM模式 | 本会话最新要求 | 我管架构，Claude写代码 |

---

## ⏰ 27个定时任务管理

### ✅ 运行正常（19个）
| 任务 | 备注 |
|------|------|
| flashsloth-autonomous-dev, evening-report, fs-auto-task-executor | 核心执行器 |
| 🐶 TODO看门狗, 🛡️铁律监督, 🔍审计 | 监控三件套 |
| 📖开发说明书, 📚README同步 | 文档自动化 |
| 🔧平台适配-B站等, TODO-twitter-publisher | 平台推进 |
| P0-连接状态Cookie, P0-登录能力, P0-Playwright引擎 | 6个P0监控 |
| P0-签到统计, P0-Provider工作台, P0-Giscus | 持续监控 |
| TODO-ai-call-log, TODO-mobile-responsive | 开发落地 |
| P4-签到时间批量设置 | 低频维护 |
| flashsloth-exploration (no_agent脚本) | 已修好 |

### ⚠️ 异常待修（3个）
| 任务 | 问题 |
|------|------|
| AI趋势日报-早8点 | 🔄 Claude在修飞书推送 |
| AI趋势日报-晚8点 | 🔄 Claude在修飞书推送 |
| flashsloth-weekly-regression | 从未跑过，待观察 |

### ❌ 已暂停省token（3个）
| 任务 | 省 | 原因 |
|------|----|------|
| P0-登录弹窗完整验收 | 72次/天 | 假阳性 |
| P0-登录状态深度验证 | 72次/天 | 误报 |
| flashsloth-morning-report | 1次/天 | 持续Error |

### 🆕 PM自主（1个）
| 任务 | 频率 | 职责 |
|------|------|------|
| flashsloth-pm-daily-progress | 每天9/21点 | 自动检查进度派活 |

---

## 🛑 暂停/遗留事项
- 网关其他平台测试（等用户有需要时）
- 论坛探索DB/JSON双轨（精度问题，低优先级）
- 发布器E2E全面验收（缺真实账号）

## 📊 资源现状
- AI余额：DeepSeek ¥36.52（偏低）
- 隧道：103.97.178.234:5001 ✅
- 服务：本地运行 ✅
- 数据库：flashsloth.db (749KB) + status_cache.db (20KB)
- token节省：~145次/天 ✅
