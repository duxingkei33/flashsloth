# 平台探索报告：oshwhub.com（立创开源硬件平台）

> **探索时间**: 2026-07-05 22:30  
> **探索方式**: Playwright (Headless Chrome)  
> **账号状态**: Cookie 有效（JSESSIONID + 其他 Token）  
> **对应适配版本**: v4.x（需新增）

---

## 1. 平台特性

- **类型**: React SPA（Next.js + Ant Design）
- **内容形式**: 硬件工程项目（非博客文章）
- **发布入口**: `/project/create`（新建工程项目）
- **写文章**: `/write/works`（文章管理页，非编辑器）

## 2. 项目创建页面（/project/create）

| 字段 | 选择器 | 说明 |
|------|--------|------|
| 工程名称 | `#name` | 必填 |
| 工程简介 | `#introduction` | 不超过100字 |
| 总成本 | placeholder="请填写总成本" | 可选 |
| 开源许可证 | `#license` | 选择 |
| 编辑器 | React 富文本 | 工具栏：上传图片、插入、格式、段落 |
| 提交按钮 | "创建" | 提交 |

## 3. 上传限制

- **图片上传**: 通过编辑器工具栏"上传图片"按钮
- **附件**: 通过 EDA 工程文件上传（非标准附件）
- **API**: WAF 保护（返回 418）

## 4. API 端点（均被 WAF 拦截）

| 端点 | 状态 |
|------|------|
| `/api/user/info` | 418 |
| `/api/project/publish` | 418 |
| `/api/project/list` | 418 |

## 5. 现有代码问题

- `publisher_oshwhub.py` 使用 `requests` 直接调 API → **418 被 WAF 挡**
- Playwright 方式只实现了登录，**没有实现发布流程**

## 6. 待适配项

- [ ] 改用 Playwright 全流程：导航到 `/project/create` → 填写表单 → 上传图片 → 提交
- [ ] React SPA 交互处理（非标准 HTML 表单）
- [ ] 存草稿支持（React SPA 中实现）
- [ ] 附件上传支持（工程文件 vs 文章图片）
- [ ] E2E 验证
