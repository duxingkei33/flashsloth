# 📱 移动端 APP 平台接入方案

> **PM 分析报告** — 2026-07-08
> 针对：得物/小红书/抖音/快手等纯移动端平台

---

## 一、问题背景

FlashSloth 当前只支持 **PC 网页** 平台：通过 Playwright 操作浏览器登录/发布。

但有些平台（得物、小红书、抖音、快手等）是 **移动端 App 优先** 或 **纯移动端**：
- PC 网页仅为展示页/下载引导，无登录入口
- 核心功能（发帖、发布商品、社交互动）只在 App 内
- 部分有 API 但加密严重

---

## 二、环境评估（现有资源）

| 资源 | 值 | 结论 |
|------|-----|------|
| Docker 29.6.1 | ✅ 已安装 | 可运行容器 |
| Docker daemon | ❌ 未启动 | `sudo dockerd &` 可启动 |
| KVM | ✅ `/dev/kvm` 存在 | 支持硬件加速模拟器 |
| VT-x | ✅ 全虚拟化 | 支持 Android 模拟 |
| WSL2 | ✅ 内核 6.18 | 兼容性好 |
| RAM | 19GB 总量/12GB 可用 | 充裕 |
| 磁盘 | 854GB 可用 | 充裕 |
| 网络 | ✅ 云手机服务可达 | 红手指/多多云 200 OK |

---

## 三、可选方案对比

### 方案A：Redroid（Docker Android）

**原理**：在 Docker 容器中运行 Android 系统，通过 ADB 控制

```
┌─────────────────┐
│   FlashSloth     │
│   mobile_bridge  │←─ ADB ──→  Redroid Container
│   (Python)       │          (Android 11/12)
└─────────────────┘               ↓
                              App自动化
                           (Appium/Airtest)
```

| 项目 | 评估 |
|------|------|
| 资源消耗 | ~1.5GB RAM / 5GB 磁盘 / 实例 |
| 性能 | ✅ 硬件加速 (KVM) |
| 稳定性 | ⚠️ WSL2 需加载 binder 内核模块（需要自定义内核） |
| 安装复杂度 | 🔴 高 — 需编译 WSL 内核启用 binder/ashmem |
| 费用 | ✅ 免费 |
| **结论** | ⏳ 可行但落地周期长，需改 WSL 内核 |

### 方案B：云手机服务 ★推荐

**原理**：租用云端 Android 手机，通过 ADB over TCP 控制

```
┌─────────────────┐          ┌──────────────────┐
│   FlashSloth     │──ADB────→  云手机服务       │
│   mobile_bridge  │  TCP     │  (红手指/多多云)  │
│   (Python)       │          │  Android 实例     │
└─────────────────┘          └──────────────────┘
                                    ↓
                               App 自动化
                            (无需处理反检测)
```

| 项目 | 评估 |
|------|------|
| 资源消耗 | 几乎为零（本地只跑 Python 控制端） |
| 性能 | ✅ 云服务商提供真实 ARM 环境 |
| 稳定性 | ✅ 7×24h 在线，服务商维护 |
| 安装复杂度 | 🟢 低 — 只需装 ADB + Python 客户端 |
| 费用 | ⚠️ ¥30-100/月/实例（红手指 ¥59/月） |
| 反检测 | ✅ 真实手机环境，App 不会识别为模拟器 |
| **结论** | ✅ **最适合当前场景，快速落地** |

**推荐服务商**：
| 服务 | 价格 | 特点 |
|------|------|------|
| 红手指 | ¥59/月 | 成熟，ADB 支持好，中文文档 |
| 多多云 | ¥39/月起 | 便宜，支持 ADB 调试 |
| 雷电云手机 | ¥29/月起 | 性价比高 |
| 华为云手机 | ¥99/月起 | 稳定，但贵 |

### 方案C：Appium + AVD（本地模拟器）

**原理**：本地跑 Android 模拟器 + Appium 自动化框架

| 项目 | 评估 |
|------|------|
| 资源消耗 | 🔴 4-8GB RAM / 10GB 磁盘 |
| 性能 | ✅ KVM 硬件加速 |
| 稳定性 | ⚠️ WSL2 下 AVD 有时断连 |
| 安装复杂度 | 🔴 高 — 装 Android SDK + AVD + Appium |
| 反检测 | ❌ 模拟器易被 App 识别封号 |
| **结论** | ❌ **不推荐** — 太重、App 会检测模拟器 |

### 方案D：物理 Android 手机（USB 直连）

**原理**：一台旧 Android 手机通过 USB 连接 WSL

| 项目 | 评估 |
|------|------|
| 费用 | 🟢 一台旧手机（几百元） |
| 性能 | ✅ 真实 ARM 环境 |
| 稳定性 | ⚠️ USB 线缆/供电问题 |
| 反检测 | ✅ 真实手机，完全不被识别 |
| 可扩展性 | ❌ 一台手机只能跑一个平台 |
| **结论** | ⏳ 备选 — 适合有闲置手机的场合 |

---

## 四、推荐方案：云手机 + ADB Bridge（三阶段落地）

### Phase 1 🚀 快速验证（1-2天）

```
预算：¥59/月（红手指）
依赖：adb + appium-python-client
工作：验证「ADB 可以捕获 App 内的 Cookie/Token」
```

1. 注册红手指 → 购买 1 台云手机
2. 装 ADB → `apt install adb`
3. 云手机装得物 App → 登录 → ADB 提取 Cookie
4. 验证 Cookie 能否注入 FlashSloth
5. 可行 → 继续 Phase 2

### Phase 2 🏗️ 架构接入（1周）

在 FlashSloth 中新增：

```
core/
├── mobile_bridge.py          ← 新增：移动端抽象层
├── mobile_providers/
│   ├── __init__.py
│   ├── cloud_phone.py        ← 云手机 ADB 实现
│   ├── redroid.py            ← Redroid 实现（可选）
│   └── stub.py               ← 空实现（开发用）
plugins/
├── mobile_dewu_adapter.py    ← 得物 App 适配（新增）
├── mobile_xiaohongshu.py     ← 小红书 App 适配（新增）
├── mobile_douyin.py          ← 抖音 App 适配（后续）
└── mobile_kuaishou.py        ← 快手 App 适配（后续）
```

**MobileAdapter 基类设计**（仿照现有 Publisher 模式）：

```python
class MobileAdapter(ABC):
    """移动端 App 适配器基类"""
    name: str = ""
    display_name: str = ""
    package_name: str = ""       # Android package name
    app_activity: str = ""       # 主 Activity
    
    @abstractmethod
    def login_and_extract(self) -> dict:
        """自动登录 App 并提取 Cookie/Token"""
        pass
    
    @abstractmethod
    def screenshot(self) -> bytes:
        """截取 App 当前屏幕"""
        pass
    
    @abstractmethod
    def publish(self, content: dict) -> dict:
        """在 App 内发布内容"""
        pass
```

### Phase 3 🎯 平台适配（持续）

| 平台 | 分类 | 优先级 | 适配方式 |
|------|------|--------|---------|
| 得物 | shopping | **P1** | 云手机 → 得物 App → 抓登录 Cookie → 转发请求 |
| 小红书 | social | **P1** | 云手机 → 小红书 App → 获取发布 API Token |
| 抖音 | social | **P2** | 同上 |
| 快手 | social | **P2** | 同上 |
| 拼多多 | shopping | **P3** | 同上 |

---

## 五、技术细节 — ADB 做什么

```
# 连接云手机
adb connect <cloud_phone_ip>:5555

# 安装/启动 App
adb install dewu.apk
adb shell am start -n com.dewu.app/.MainActivity

# 截图（调试用）
adb shell screencap -p /sdcard/screen.png
adb pull /sdcard/screen.png

# 提取 App 内部 Cookie/Token
adb shell cat /data/data/com.dewu.app/shared_prefs/*.xml

# 拦截网络请求（抓 API）
# 方案1：通过 App 内置 WebView 调试
# 方案2：adb logcat | grep "Cookie\|Authorization"
# 方案3：mitmproxy 代理（需设置云手机代理）

# UI 自动化（Appium）
appium --address 0.0.0.0 --port 4723
# Python 客户端控制 App 点击/输入
```

### 核心流程：从 App 捕获 Cookie

```
1. ADB 登录云手机
2. Appium 打开得物 App
3. 自动点击「登录」→ 选择「密码登录」
4. 输入账号密码
5. 等待登录成功（检测首页元素）
6. adb shell 提取 App 内部 token/cookie
   → /data/data/com.dewu.app/shared_prefs/
   → 或通过 WebView CookieManager
7. 将 Cookie/Token 加密存入 FlashSloth DB
8. 后续请求直接用该 Token 调用 App API
```

---

## 六、与现有架构的集成

```
┌────────────────────────────────────────────────────────┐
│                    FlashSloth 统一架构                    │
├─────────────┬───────────────────┬──────────────────────┤
│   PC 平台    │   移动端 App       │  公共基础设施           │
│  (现有)      │   (新增)           │                       │
├─────────────┼───────────────────┼──────────────────────┤
│ Playwright  │   云手机 + ADB    │  统一 Cookie 验证器     │
│ Publisher   │   MobileAdapter   │  cookie_validator.py  │
│ (PC浏览器)  │   (App自动化)      │                       │
│             │                   │  统一凭证存储          │
│ 登录: QR码  │   登录: App内     │  encrypt_config()     │
│ 密码/OAuth  │   密码/短信/生物   │                       │
│             │                   │  状态检测与缓存        │
│ 发布: 浏览器 │   发布: App API   │  status_cache         │
│ API 调用    │   (Token 鉴权)    │                       │
└─────────────┴───────────────────┴──────────────────────┘
         ↑                    ↑
   已有的铁律+规则        新增 MobileAdapter 接口
   全量覆盖               注册制(@register)
```

**关键设计原则**：
1. **PC 和 Mobile 共享同一套凭证基础设施** — 加密/解密/验证
2. **MobileAdapter 也走 @register 注册制** — 和 Publisher 平级
3. **账号管理页面统一展示** — 不管 PC 还是 Mobile 平台
4. **不动的部分**：不碰 DB、不加新服务进程、不下新包（除 adb）

---

## 七、成本估算

| 项目 | 月费 | 一次性 |
|------|------|--------|
| 红手指云手机 ×1 | ¥59 | - |
| 红手指云手机 ×3 | ¥177 | - |
| ADB + Appium | 免费 | - |
| 开发人力 | - | 子AI干活，0额外成本 |
| **最低方案** | **¥59/月** | **0** |
| **全量方案（3台）** | **¥177/月** | **0** |

---

## 八、风险和缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| App 检测云手机并封号 | 中 | 高 | 选大厂服务（红手指等），用真实手机号注册 |
| ADB 被云手机限制 | 低 | 高 | 先买一个月验证，不行换服务商 |
| App 更新导致适配失效 | 高 | 中 | 模块化选择器，更新时只需改 selectors |
| 云手机网络延迟 | 低 | 低 | 控制指令轻量，只有关键操作走云手机 |
| 费用持续 | 中 | 低 | 只对需要的平台租用，按需增减 |

---

## 九、下一步行动建议

```
□ 1. 我先买一个月红手指验证                   — ¥59
   → ADB 连接测试 → 得物 App 登录 → 提取 Cookie

□ 2. 写 mobile_bridge.py 基础框架             — 子AI 1天
   → ADB 连接管理 + 截图 + 包管理

□ 3. 写得物 MobileAdapter                    — 子AI 1天
   → 登录 + Cookie 提取

□ 4. 写小红书 MobileAdapter                  — 子AI 1天
   → 同模式

□ 5. 写抖音 MobileAdapter                    — 子AI 1天
   → 同模式

□ 6. E2E 验证 + 三位一体备份
```

---

## 十、结论

| 方案 | 可行性 | 费用 | 落地速度 | 推荐 |
|------|--------|------|---------|:----:|
| **云手机 + ADB** | ✅ 高 | ¥59/月起 | 🟢 快 | **🥇** |
| Redroid Docker | ⚠️ 中 | 免费 | 🔴 慢（需改内核） | 🥈 |
| Appium + AVD | ❌ 低 | 免费 | 🔴 极慢 | ❌ |
| 物理手机 + USB | ⚠️ 中 | 购机费 | 🟡 中 | 🥉 |

**最佳路径**：云手机服务 ¥59/月 → 接入 ADB Bridge → 逐步覆盖得物/小红书/抖音/快手
