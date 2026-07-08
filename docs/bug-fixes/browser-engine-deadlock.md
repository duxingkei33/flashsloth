# Bug #4: BrowserEngine 线程死锁

| 属性 | 值 |
|------|-----|
| 版本 | v4.64 |
| 日期 | 2026-07-07 |
| 严重度 | 🔴 阻塞级 |
| 模块 | browser |
| 关联铁律 | #20 持锁期间禁止调其他获取同一锁的函数 |

## 症状
所有页面请求超时卡死。访问任何 FS 页面都无响应，浏览器引擎状态显示异常。

## 根因
`threading.Lock` 不可重入（non-reentrant）。`context_processor` 在持有锁的情况下调用了 `get_engine()`，而 `get_engine()` 内部也尝试获取同一把锁 → 自死锁。

```python
# 错误模式:
with self._lock:           # 线程A获取锁
    get_engine()            # 内部 with self._lock → 死锁！
```

## 修复
1. 将 `context_processor` 中的锁获取改为 `acquire(timeout=0.5)`，超时即跳过
2. 将引擎状态读取（`get_engine()`）从锁保护中移出
3. 锁只保护状态写入和引擎启动/停止操作，读取操作不加锁

## 教训
- **Python `threading.Lock` 不可重入** — 同一线程不能重复获取
- **需要可重入锁时用 `threading.RLock`**
- **context_processor 在每个请求中运行** — 必须极快返回，不能阻塞
- **锁的粒度要尽量小** — 只保护必须互斥的操作

## 关联
- 铁律 #20: 持锁期间禁止调其他可能获取同一锁的函数
- 参考: `references/browser-engine-deadlock-pattern.md`