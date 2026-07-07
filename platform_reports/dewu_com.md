# 得物 (dewu)

- 分类: shopping
- 架构: custom (Vue.js + Element UI)
- 探索时间: 2026-07-08 02:52:45

## 🔐 登录能力

- **登录页**: https://open.dewu.com/login#/login (开放平台)
- **主站 login**: www.dewu.com/login 有云图人机验证，无实际登录表单
- **登录方式**:
  - ✅ **短信登录**: 手机号 + 短信验证码 + 滑块验证 (优先级1)
  - ✅ **密码登录**: 手机号 + 密码 + 滑块验证 (优先级2)
  - ✅ **Cookie粘贴**: 备选 (优先级99)
- **第三方登录**: ❌ 无 (微信/微博/QQ/Apple 均无)
- **二维码**: ❌ 无
- **验证码**: ✅ 滑块验证（请按住滑块，拖动到最右边）
- **Cookie提示**: token, sid, session, dewu_token, passport

### 登录流程
1. 访问 https://open.dewu.com/login#/login
2. 默认显示密码登录 Tab（手机号 + 密码）
3. 可通过 Tab 切换到短信登录（手机号 + 短信验证码）
4. 每次登录前必须完成滑块验证码
5. 有「忘记密码」「立即注册」链接

## 📝 发布能力

- 编辑器: 无网页端（仅App支持发布）
- 需登录编辑: N/A
- API端点: prd-otel-h5-public.dewu.com/api/traces

## ⚙️ 技术信息

- 框架: Vue.js + Element UI
- 反爬: ✅ 云图(Yuntu)人机验证 + 滑块验证码
- HTTPS: ✅
- 备注: 得物是App导向的潮流网购社区，网页端仅品牌展示和开放平台(开发者)。普通用户登录/发布主要在得物App内完成。开放平台是给开发者/商家的入口
