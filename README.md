# 🦥 FlashSloth

**树懒的速度，闪电的发布**

多平台内容发布系统。写一次 Markdown，一键发布到 WordPress、微信公众号、掘金、知乎、CSDN 等多个平台。

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/duxingkei33/flashsloth.git
cd flashsloth

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
python flashsloth/admin.py
```

首次启动会自动生成管理员账号密码，直接打印在终端上。

```
======================================================
  🦥 FlashSloth — 树懒的速度，闪电的发布
  🌐 http://0.0.0.0:5000
  👤 首次启动，自动生成了管理员账号：
     用户名: admin_a1b2c3
     密码:   Xy7kPq9mR2vL4nW8
  ⚠️  请尽快登录后台修改密码！
======================================================
```

打开浏览器访问 `http://localhost:5000` 即可进入管理后台。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FLASHSLOTH_SECRET` | 自动生成 | Flask 密钥（生产环境建议固定） |
| `FLASHSLOTH_HOST` | `0.0.0.0` | 监听地址 |
| `FLASHSLOTH_PORT` | `5000` | 监听端口 |

## 功能

- **文章管理** — 新建、编辑、删除文章（Markdown 编辑）
- **一键发布** — 选中文章，勾选平台，一键发布
- **多平台支持**：
  - WordPress（REST API）
  - 微信公众号
  - 掘金
  - 知乎（Playwright）
  - CSDN（Playwright）
  - RSS 订阅源
- **多账号管理** — 每个平台可配置多个发布账号
- **发布日志** — 全程追踪发布历史
- **Provider 切换** — Markdown / Notion 源切换

## 项目结构

```
flashsloth/
├── admin.py               ← Web 管理后台（主入口）
├── cli.py                 ← 命令行工具
├── core/
│   ├── article.py         ← 统一文章模型
│   ├── publisher.py       ← Publisher 基类 + 注册中心
│   └── config.py          ← 配置管理
├── plugins/
│   ├── publisher_wordpress.py
│   ├── publisher_wechat.py
│   ├── publisher_juejin.py
│   ├── publisher_rss.py
│   ├── publisher_zhihu.py
│   └── publisher_csdn.py
└── templates/             ← Jinja2 模板
    ├── login.html
    ├── register.html
    ├── index.html
    ├── settings.html
    ├── accounts.html
    ├── edit.html
    └── publish_select.html
```
