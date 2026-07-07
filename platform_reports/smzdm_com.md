# 什么值得买 (smzdm)

- 分类: shopping
- 架构: custom
- 探索时间: 2026-07-08 00:35:09

## 🔐 登录能力

### 登录方式
- **登录入口**: 首页点击 `.J_login_trigger` 触发弹窗
- **登录弹窗ID**: `#J_login_popup`
- **登录iframe**: `#J_login_iframe`, 加载 `https://zhiyou.smzdm.com/user/login/window/`
- **iframe通信**: postMessage (agreeType: register_post / reload_post)

### 支持的方式
| 方式 | 说明 |
|------|------|
| 🔑 密码登录 | POST /user/login/doLogin |
| 📱 短信验证码 | POST /user/login/smsLogin |
| ⚡ 快速登录 (quick_login) | POST /user/login/quickLogin |
| 📲 App唤起 | call_client_login() |
| 💬 微信 | ✅ 第三方登录 |
| 🐧 QQ | ✅ 第三方登录 |
| 📢 微博 | ✅ 第三方登录 |

### 验证码
- **WAF**: 腾讯云WAF (Tencent Cloud WAF)，JS挑战 + 拖拽验证码
- **JS引擎**: `__TENCENT_CHAOS_VM` 虚拟机指纹检测
- **Probe脚本**: `/C2WF946J0/probe.js`
- **腾讯验证码**: appid=2017163193, 拖拽类型
- **图片验证码**: 密码错误≥3次时显示, 选择器 `#captcha_img`
- **headless检测**: 所有页面被WAF拦截，headless浏览器无法直接访问

### 选择器
| 用途 | 选择器 |
|------|--------|
| 登录触发 | `.J_login_trigger` |
| 注册触发 | `.J_register_trigger` |
| 登录弹窗 | `#J_login_popup` |
| 登录iframe | `#J_login_iframe` |
| 关闭按钮 | `.J_popup_close` |
| 弹窗标题 | `.z-popup-head` |
| 验证码图片 | `#captcha_img` |
| 用户入口 | `.J_user_entry` |
| 用户名显示 | `.J_nav_username` |

### API端点
| 端点 | 方法 | WAF | 说明 |
|------|------|-----|------|
| /user/login/doLogin | POST | ✅ | 密码登录 |
| /user/login/login | POST | ✅ | 登录 |
| /user/login/quickLogin | POST | ✅ | 快速登录 |
| /user/login/smsLogin | POST | ✅ | 短信验证码登录 |
| /user/info/jsonp_get_current | GET | ❌ | 获取用户信息(可用) |

### Cookie提示
sess, auth, token, smzdm_id, w_tsfp, x-waf-captcha-referer

### 字段说明
| 字段名 | 类型 | 说明 |
|--------|------|------|
| username | text | 手机号/邮箱/用户名 |
| password | password | 密码 |
| sms_code | text | 短信验证码 |
| captcha | image | 验证码(≥3次失败) |

## 📝 发布能力

- 编辑器: https://www.smzdm.com/publish
- 需登录编辑: False
- API端点: 0 个

## ⚙️ 技术信息

- 框架: 自建
- 反爬: ✅ 腾讯云WAF + 拖拽验证码
- 动态内容: ✅
- WAF: Tencent Cloud WAF, JS challenge (__TENCENT_CHAOS_VM) + drag captcha
- 备注: 消费导购平台，自建架构。所有页面受腾讯云WAF保护，headless浏览器无法直接访问，需要处理JS挑战
