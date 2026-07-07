# 🦥 FlashSloth 项目状态
> 最后更新：2026-07-08 07:35 | PM: duxingkei | 铁律: fs-iron-rules

> ⚠️ 本文档通过梳理全部聊天记录 + 最新需求对齐生成

## 🎯 核心目标
统一多平台内容发布与管理平台（个人数字资产中心），保持轻量、稳定、不膨胀。

## 📍 当前阶段
**v5.11** — signin BrowserEngine复用 + 验证凭证按钮 + deploy页面重定向

---

## 📋 历史需求对照（按最新要求对齐）

### ✅ 已完成的重大模块

| 模块 | 状态 | 说明 |
|------|------|------|
| 通知网关22Provider移植 | ✅ | 飞书/企微/Telegram/Discord/Slack/钉钉/微信等全部完成 |
| 闲鱼V2发布器 | ✅ | MTOP API链路完整移植，含签名/风控/限流/CDN/AI类目 |
| 平台发布器（7个） | ✅ | Discuz/CSDN/OSHWHub/知乎/B站/掘金/微信 |
| 登录弹窗三种方式 | ✅ | 密码/QR码/短信验证码，全部通过验收 |
| **P0账号弹窗归一化深化** | ✅ | 统一模态框+QR码优先+密码/验证码备选+Cookie仅调试模式 |
| **统一凭证体系** | ✅ | ScanLoginEngine统一扫码引擎+QR码轮询10秒 |
| **Cookie验证修复** | ✅ | DiscuzPublisher严格登录态检测+Playwright子进程降级+playwright_verify_raw |
| QR码线程安全修复 | ✅ | 后台线程模式，22/22测试通过 |
| 短信验证码登录 | ✅ | phone_login跨线程修复，支持CSDN/知乎/掘金/B站 |
| 智能版块匹配引擎 | ✅ | forum_registry + 全平台匹配 |
| 探索页重构 | ✅ | 折叠式+能力配置+标签管理 |
| 三层状态检测 | ✅ | 缓存→API轻量→Playwright |
| 浏览器自死锁修复 | ✅ | threading.Lock不可重入→v4.64 |
| 验证码+进度条登录 | ✅ | 5步进度条+Amobbs核验 |
| 批量文章操作 | ✅ | 多选删除/发布 |
| 铁律skill固化 | ✅ | 7章完整：禁止/必须/流程/备份(加强)/数据流/违规记录/PM协作 |
| 项目架构梳理文档 | ✅ | PROJECT_ARCHITECTURE_REVIEW.md 645行 |
| Claude PM协作模式 | ✅ | 我管架构，Claude写代码 |
| 定时任务清理省token | ✅ | 暂停3个假阳性cron，省~145次/天 |
| **备份体系加固** | ✅ | 铁律B1-B9（三位一体强制+每日自动+完整性校验）+ 每日4:30自动备份cron |

### ❌ 已取消/不做的

| 任务 | 原因 |
|------|------|
| FRPC隧道自动管理 | 铁律禁止，frpc独立守护 |
| browser-use/video-use集成FS | 仅学技能，不与FS绑定 |
| 闲鱼AutoReply运行/安装 | 只学代码思路移植，已移出 FS 目录到 ~/study/ |
| CSDN签到修复 | 用户说不做了 |
| 视频下载模块 | 不与FS绑定 |

### 🔄 正在进行/待办

**P0 — 紧急**
- [x] **统一凭证体系+账号弹窗归一化** — ✅ 已完成 (v4.92~v5.03)
- [x] **login-capabilities refresh site_url传透** — ✅ 已完成
- [x] **QR码全平台优先级#1** — ✅ 已修复
- [x] **Cookie验证修复** — ✅ 已完成 (v5.06)
- [x] **清理api_platforms_list死代码** — ✅ 已完成
- [x] **Provider抽象框架+工作台集成** — ✅ 已完成 (v5.11)

**P1 — 重要（需你在场）**
- [ ] CSDN签到实测验证
- [ ] bilibili/xianyuV2/Twitter发布实测
- [ ] 验证flashsloth-exploration脚本是否完全修复

**P2 — 优化**
- [x] forum_registry读DB（JSON/DB双轨）
- [ ] 监控flashsloth-pm-daily-progress首次运行

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

## ⏰ 34个定时任务管理（7/7更新）

### ✅ 运行正常（29个）
| 类别 | 任务 | 状态 |
|------|------|:----:|
| **核心执行** | flashsloth-autonomous-dev, evening-report, fs-auto-task-executor | ✅ |
| **监控三件套** | 🐶 TODO看门狗, 🛡️铁律监督, 🔍审计 | ✅ |
| **文档自动化** | 📖开发说明书, 📚README同步 | ✅ |
| **P0持续监控** | Provider工作台, 登录能力探索, Cookie修复, Playwright引擎, 签到统计, Giscus部署 | ✅ 6个 |
| **TODO开发落地** | TODO-ai-call-log (4/6 🔄Claude编写中), TODO-mobile-responsive (4/6 🔄Claude编写中) | 🅱️ |
| **平台推进** | 🔧平台适配流水线-B站等 | ✅ |
| **E2E测试** | 01登录/02账号/03发布/04社区/05日志/06杂项 | ✅ 6个每日 |
| **例行巡检** | weekly-regression(周日), fs-cleanup(周日), code-review(周六) | ✅ |
| **每日审计** | pm-daily-progress(9/21点), hardcode-audit(3点) | ✅ |
| **功能开发** | 📄日志统一管理页面(30次,每天9点) | 🅰️ |
| **脚本任务** | flashsloth-exploration(每小时), AI趋势(早8/晚8), FS每日备份(4:30) | ✅ 4个no_agent |

### ⚠️ 异常/暂停（3个）
| 任务 | 问题 | 处理 |
|------|------|:----:|
| AI趋势日报-早8点 | ~~delivery_error~~ ✅ **已修复**（deliver → origin），明早8点恢复 | ✅ 我修的 |
| AI趋势日报-晚8点 | ~~delivery_error~~ ✅ **已修复**（同上），明晚8点恢复 | ✅ 我修的 |
| flashsloth-morning-report | 暂停 — DeepSeek API 402 余额不足 | ⏸ 等你充值 |

### 🗑️ 已清理（3个）
| 任务 | 删除原因 |
|------|----------|
| 🔴 P0-登录弹窗完整验收 | 12/12全部通过，已做完 → **已删除** |
| 🔴 P0-登录状态深度验证 | Broken pipe假阳性，功能已做好 → **已删除** |
| TODO-twitter-publisher | 代码已完成，缺你的Twitter API Key → **任务结束** |

### 🆕 PM自主（2个）
| 任务 | 频率 | 职责 |
|------|------|------|
| flashsloth-pm-daily-progress | 每天9/21点 | 自动检查进度派活 |
| 📦 FS每日自动备份 | 每天4:30 no_agent | 三位一体备份（tar.gz+TAG.txt+git tag），静默成功，失败告警 |

---

## 🛑 暂停/遗留事项
- 网关其他平台测试（等用户有需要时）
- 论坛探索DB/JSON双轨（✅ 已完成于v5.02，今晨验证通过）
- 发布器E2E全面验收（缺真实账号）

## 📊 资源现状
- AI余额：DeepSeek ¥36.52（偏低）
- 隧道：103.97.178.234:5001 ✅
- 服务：本地运行 ✅
- 数据库：flashsloth.db (749KB) + status_cache.db (20KB)
- token节省：~145次/天 ✅
- **备份体系：铁律B1-B9强制三位一体，每日4:30自动备份到 ~/fastsloth/**
