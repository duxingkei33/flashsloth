# 什么值得买 (smzdm)

- 分类: shopping
- 架构: custom (自建)
- 探索时间: 2026-07-08 02:55:39

## 🔐 登录能力

- **登录页**: https://zhiyou.smzdm.com/user/login (受WAF保护)
- **主站**: www.smzdm.com 含腾讯验证码WAF
- **登录方式**:
  - ✅ **手机验证码登录**: 手机号 + 短信验证码 (优先级1)
  - ✅ **密码登录**: 手机号/邮箱/用户名 + 密码 (优先级2)
  - ✅ **Cookie粘贴**: 备选 (优先级99)
- **第三方登录**: ✅ 微信 (推测)
- **二维码**: ❌ 无
- **验证码**: ✅ 腾讯验证码(TencentCaptcha) + 图片验证码(失败3次后)
- **Cookie提示**: sess, auth, token, smzdm_id, session, zhiyou

### ⚠️ 强反爬说明
什么值得买有**非常强**的反爬措施：
1. **WAF**: 所有页面返回 HTTP 202 状态码 + `probe.js` 探测脚本
2. **腾讯验证码**: ssl.captcha.qq.com/TCaptcha.js 人机验证
3. **验证流程**: 页面加载 → 自动弹腾讯验证码 → 验证通过后页面自动重载
4. **Playwright/headless**: 头部浏览器被检测后会持续显示空白页
5. 任何自动化解锁都是绕过WAF/验证码，难度较高

## 📝 发布能力

- 编辑器: https://www.smzdm.com/publish
- 需登录编辑: 需要
- API端点: 未获取（被WAF拦截）

## ⚙️ 技术信息

- 框架: 自建
- 反爬: ✅✅✅ 非常强（WAF + TencentCaptcha + probe.js）
- HTTPS: ✅
- 备注: 消费导购平台，自建架构。发布功能需要登录后探索
