# Bug #9: Amobbs border click 误触「换一个」链接导致验证码刷新

**版本**: v5.21 | **严重度**: 🔴 | **模块**: captcha/login | **日期**: 2026-07-09

## 症状（Symptom）
Amobbs 验证码提交时总是返回「验证码错误」，即使输入的是正确的验证码。用户反复输入验证码仍失败。

## 根因（Root Cause）
`submit_text_captcha()` 中的 border click 用于触发 Discuz 风格的 `.seccodecheck` 核验。border click 坐标计算为 `(input.x + width + 10, input.y + height/2)`，在 Amobbs 登录页上这个坐标恰好命中「换一个」链接 (`<a>` 元素，x=528, y=453)。

点击「换一个」触发 `updateseccode()` → 刷新验证码图片 → 旧的 `seccodehash` 失效 → 提交时服务器校验失败 → 返回「验证码错误」。

Amobbs 没有 `.seccodecheck` 机制（只有 `checksec()` 通过 focus/blur 触发），所以 border click 是多余且有害的。

## 修复（Fix）
仅在 `.seccodecheck` 元素存在时执行 border click（Discuz 风格平台）。Amobbs 无此元素，跳过 border click，仅靠 `focus()` + `blur()` 触发 `checksec()` 即可完成验证码预检。

```python
# plugins/amobbs_login.py
has_seccodecheck = page.query_selector(".seccodecheck") is not None
if has_seccodecheck:
    # Discuz 风格：border click 触发 seccodecheck
    input_el.click(position={"x": input_box["width"] + 10, "y": input_box["height"] / 2})
else:
    # Amobbs 风格：focus/blur 触发 checksec 即可
    input_el.focus()
    page.wait_for_timeout(300)
    input_el.blur()
```

## 教训（Lesson）
1. **坐标点击不可靠** — 绝对坐标 `(x+10, y/2)` 在不同页面布局下可能命中不同元素。应使用选择器定位目标元素，而非坐标推算。
2. **平台差异必须显式检测** — 不能假设所有 Discuz 系平台都有 `.seccodecheck`。必须运行时检测 DOM 元素存在性，而非硬编码行为。
3. **border click 的副作用** — 任何页面交互（包括 border click）都可能触发意外的 DOM 事件。在添加交互前必须确认目标区域无干扰元素。

## 关联铁律
- 铁律 #15: 前端/Cookie/登录 E2E 必须用 Playwright 真实浏览器 — 此 bug 的根因是坐标点击在真实浏览器中的副作用，纯代码审查无法发现
- 铁律 #28: 一切工作必须数据驱动，禁止硬编码 — 平台行为差异必须从探索数据动态判断