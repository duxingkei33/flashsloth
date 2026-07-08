# Bug #5: 模板 .pyc 缓存陈旧

| 属性 | 值 |
|------|-----|
| 版本 | v4.58 |
| 日期 | 2026-07-07 |
| 严重度 | 🟡 中 |
| 模块 | template |
| 关联铁律 | #33 Flask 模板缓存 + .pyc 陷阱 |

## 症状
修改 HTML 模板后，页面不更新。重启 Flask 服务也不生效。

## 根因
Flask 的 `TEMPLATES_AUTO_RELOAD = False`（生产环境设置），且 `__pycache__` 中缓存了旧版模板的编译字节码。即使重启 Flask，`.pyc` 文件仍然指向旧版本。

## 修复
```bash
find . -name "__pycache__" -exec rm -rf {} +
```
然后重启 Flask 服务。

## 教训
- 修改模板后必须清理 `__pycache__`
- 开发环境应开启 `TEMPLATES_AUTO_RELOAD = True`
- 生产环境的 `.pyc` 缓存是性能优化，但也是坑

## 关联
- 铁律 #33: Flask 模板缓存使修改不生效 + .pyc 陷阱