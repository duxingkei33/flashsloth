# Bug #2: Cookie 假阳性验证

| 属性 | 值 |
|------|-----|
| 版本 | v5.19b |
| 日期 | 2026-07-08 |
| 严重度 | 🔴 阻塞级 |
| 模块 | cookie/status |
| 关联铁律 | #9 数据驱动叠加硬性兜底, #17 禁止cookie数量判据 |

## 症状
`playwright_verify.py` 对已过期的 Cookie 返回"已登录"状态。用户看到绿色✅但实际无法发帖。

## 根因
数据驱动路径的 `required_indicators_for_success` 为空列表时，`required_found` 始终为 True，`is_logged_in` 退化到仅检查页面重定向 → 假 Cookie 可通过此路径误判为已登录。

具体流程：
1. 探索数据中某平台的 `login_indicator_selectors.required_indicators_for_success` 为空 `[]`
2. `playwright_verify.py` 的数据驱动分支：`required_found = all(selector in page for ...)` 由于列表为空直接返回 True
3. 唯一的防护只剩"是否重定向到登录页"检查
4. 部分平台过期 Cookie 访问时不会重定向，只是静默显示未登录状态

## 修复
**硬性兜底** — 所有登录验证路径必须叠加强制 `has_exit_or_logout` 检查：
```python
# 数据驱动指示器 + 硬性退出/注销检查
has_exit_or_logout = any(sel in page for sel in HARD_EXIT_SELECTORS)
is_logged_in = required_found and has_exit_or_logout
```

`HARD_EXIT_SELECTORS` 包含所有平台的退出/注销按钮选择器。

## 教训
- **数据驱动不等于放宽验证** — 探索数据应当增补而非取代硬性要求
- **空列表是危险的默认值** — 任何 `all([])` 都返回 True，需要显式处理
- **永远要有至少一个硬性兜底条件** — 不管探索数据说什么

## 关联
- 铁律 #9: 数据驱动登录验证必须叠加硬性兜底
- 铁律 #17: 禁止 cookie 数量判据
- 参考: `references/cookie-verify-false-positive-pattern.md`