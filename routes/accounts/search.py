"""FlashSloth — 账号管理路由：平台搜索 + 登录能力"""
from flashsloth.routes._app import app
from flask import jsonify, request
from flask_login import login_required, current_user

import json
import os
import re
import time
from datetime import datetime, timezone

from flashsloth.routes.accounts.helpers import (
    _load_login_capabilities, _PLATFORM_CAP_MAP, _REPORTS_DIR,
    _extract_captcha_info, _enhance_login_methods, _infer_config_fields_from_cap,
)

# ─── API 缓存：空搜索缓存 30 秒 ───
_platform_search_cache = {"data": None, "ts": 0}
_PLATFORM_SEARCH_CACHE_TTL = 30  # 秒


@app.route("/api/platforms/search")
@login_required
def api_platforms_search():
	"""模糊搜索平台 — 匹配 name / display_name，动态加载架构类型

	数据来源（覆盖所有已配置平台）：
	1. list_publishers() — 已注册发布器
	2. platform_reports/*_login_capabilities.json — 有登录能力的平台
	3. forum_registry.FORUM_DATA — Discuz! 论坛域名

	异常保护：单个源失败不影响其他源
	缓存：空搜索（q 为空）结果缓存 30 秒
	"""
	from flashsloth.core.publisher import list_publishers
	q = request.args.get("q", "").strip().lower()

	# ─── 空搜索缓存命中 ───
	if not q and _platform_search_cache["data"] is not None:
		if time.time() - _platform_search_cache["ts"] < _PLATFORM_SEARCH_CACHE_TTL:
			return jsonify({"success": True, "results": _platform_search_cache["data"], "total": len(_platform_search_cache["data"])})

	results = []
	seen = set()  # 去重

	# ─── 1. list_publishers() ───
	try:
		publishers = list_publishers()
		for p in publishers:
			name = p["name"]
			display_name = p["display_name"]
			name_lower = name.lower()
			display_lower = display_name.lower()
			if q and q not in name_lower and q not in display_lower:
				continue
			arch = p.get("architecture", "")
			results.append({
				"name": name,
				"display_name": display_name,
				"architecture": arch,
				"config_fields": p.get("config_fields", []),
				"login_methods": p.get("login_methods", []),
			})
			seen.add(name)
	except Exception:
		# 源 1 失败不影响其他源
		pass

	# ─── 2. platform_reports/*_login_capabilities.json ───
	try:
		import glob as _glob
		reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "platform_reports")
		pattern = os.path.join(reports_dir, "*_login_capabilities.json")
		for cap_path in _glob.glob(pattern):
			fname = os.path.basename(cap_path)  # e.g. amobbs_login_capabilities.json
			pname = fname.replace("_login_capabilities.json", "")  # e.g. amobbs
			if pname in seen:
				continue
			if q and q not in pname.lower():
				continue
			# 读取 display_name + note
			try:
				with open(cap_path, "r", encoding="utf-8") as f:
					cap = json.load(f)
			except Exception:
				cap = {}
			display_name = cap.get("platform_name") or cap.get("display_name") or pname.replace("_", " ").title()
			note = cap.get("note", "")
			arch = ""
			if note:
				note_lower = note.lower()
				if "discuz" in note_lower:
					arch = "基于 Discuz! 架构"
			results.append({
				"name": pname,
				"display_name": display_name,
				"architecture": arch,
				"note": note[:80],
				"config_fields": _infer_config_fields_from_cap(cap),
				"login_methods": cap.get("login_methods", []),
			})
			seen.add(pname)
	except Exception:
		# 源 2 失败不影响其他源
		pass
	# ─── 3. forum_registry — 域名级 Discuz 补充 ───
	try:
		from flashsloth.core.forum_registry import FORUM_DATA
		for domain in FORUM_DATA:
			base = domain.split(".")[0]  # amobbs.com → amobbs
			if base in seen:
				continue
			if q and q not in base.lower():
				continue
			display_name = f"{base.title()} 论坛 ({domain})"
			results.append({
				"name": base,
				"display_name": display_name,
				"architecture": "",
				"config_fields": [],
				"login_methods": [],
			})
			seen.add(base)
	except Exception:
		# 源 3 失败不影响其他源
		pass

	# 按 display_name 排序
	results.sort(key=lambda x: x["display_name"])

	# ─── 空搜索写入缓存 ───
	if not q:
		_platform_search_cache["data"] = results
		_platform_search_cache["ts"] = time.time()

	return jsonify({"success": True, "results": results, "total": len(results)})


# ═══════════════════════════════════════════════════
# 登录能力 API — 从 platform_reports JSON 读取
# ═══════════════════════════════════════════════════


@app.route("/api/platform/<platform>/login-capabilities")
@login_required
def api_platform_login_capabilities(platform):
    """返回指定平台的登录能力（增强版：含 site_url_default、OAuth providers、验证码信息）"""
    cap = _load_login_capabilities(platform)
    if cap:
        from flashsloth.core.publisher import _registry as _publisher_registry
        cls = _publisher_registry.get(platform)
        guide = getattr(cls, 'guide', None) if cls else None

        login_url = cap.get("login_url", "")
        raw_detection = cap.get("raw_detection")
        methods = cap.get("login_methods", [])

        enhanced_methods = _enhance_login_methods(methods, raw_detection)
        captcha_info = _extract_captcha_info(raw_detection)

        return jsonify({
            "success": True,
            "platform": platform,
            "login_url": login_url,
            "engine": cap.get("engine", ""),
            "site_url_default": login_url if login_url.startswith("http") else "",
            "login_methods": enhanced_methods,
            "captcha_info": captcha_info,
            "source": "json",
            "guide": guide,
        })

    from flashsloth.core.publisher import _registry as _publisher_registry, list_login_methods
    methods = list_login_methods(platform)
    cls = _publisher_registry.get(platform)
    guide = getattr(cls, 'guide', None) if cls else None
    if methods:
        return jsonify({
            "success": True, "platform": platform, "source": "publisher",
            "login_methods": methods,
            "guide": guide,
            "note": f"来自 {platform} publisher 的预设登录方式",
        })
    return jsonify({"success": True, "platform": platform, "login_methods": [], "note": "待适配"})


@app.route("/api/platform/<platform>/login-capabilities/refresh", methods=["POST"])
@login_required
def api_platform_login_capabilities_refresh(platform):
	"""重新探索平台的登录能力（用 Playwright）

	铁律#12：优先使用 POST body 中的 site_url，避免硬编码。
	"""
	# 把平台名映射到 JSON 名
	json_name = _PLATFORM_CAP_MAP.get(platform, platform)
	report_path = os.path.join(_REPORTS_DIR, f"{json_name}_login_capabilities.json")

	# 🔥 铁律#12：先接受 post body 中动态 site_url
	data = request.get_json(silent=True) or {}
	site_url_from_body = str(data.get("site_url", "") or "").strip()
	# 如果 site_url 是纯域名，自动补上 https://
	if site_url_from_body and not site_url_from_body.startswith(("http://", "https://")):
		site_url_from_body = "https://" + site_url_from_body

	# 从探索数据读取登录URL（铁律#19：数据驱动）
	url = site_url_from_body
	if not url:
		cap = _load_login_capabilities(platform)
		if cap:
			url = cap.get("login_url", "")
	if not url:
		return jsonify({"success": False, "error": f"未知登录地址，请先通过 Playwright 探索或提供 site_url"})

	try:
		from flashsloth.core.browser_engine import BrowserEngine
		import base64
		from datetime import datetime, timezone

		_engine = BrowserEngine.get_instance()
		_ctx = _engine.create_isolated_context()
		if not _ctx:
			# 引擎未就绪 → 启动
			_engine.start()
			_ctx = _engine.create_isolated_context()
			if not _ctx:
				raise RuntimeError("无法启动 Playwright 浏览器引擎")
		page = _ctx.new_page()

		page.goto(url, wait_until="domcontentloaded", timeout=30000)
		page.wait_for_timeout(3000)

		# 截图
		screenshot_dir = os.path.join(_REPORTS_DIR, "screenshots")
		os.makedirs(screenshot_dir, exist_ok=True)
		screenshot_path = os.path.join(screenshot_dir, f"{json_name}_login.png")
		page.screenshot(path=screenshot_path, full_page=False)
		with open(screenshot_path, "rb") as f:
			screenshot_b64 = base64.b64encode(f.read()).decode("utf-8")

		# 检测登录方式
		body_text = page.inner_text("body")[:3000]
		page_html = page.content()
		page_url = page.url
		page_title = page.title()

		has_password = page.query_selector("input[type='password']") is not None
		has_phone = bool(re.search(r"手机号|电话号码|phone|mobile", body_text, re.I))
		has_code_btn = bool(re.search(r"获取验证码|发送验证码|get.*code|send.*code", body_text, re.I))
		has_qrcode = page.query_selector("img[src*='qrcode'], canvas[class*='qrcode'], div[class*='qrcode']") is not None
		has_wechat = bool(re.search(r"微信|wechat|weixin", body_text, re.I)) or page.query_selector("img[alt*='wechat'], i[class*='wechat']") is not None
		has_app_qr = bool(re.search(r"APP扫码|APP.*扫码|客户端扫码", body_text, re.I))
		has_oauth = page.query_selector("[class*='oauth'], [class*='third'], [class*='social'], a[href*='qq'], a[href*='weibo'], a[href*='github']") is not None

		# 检测第三方提供商
		third_providers = []
		for prov, patterns in [("qq", r"qq\.com|QQ"), ("weibo", r"weibo\.com|微博"),
								("github", r"github\.com|GitHub"), ("google", r"google|Google"),
								("wechat_oauth", r"微信登录|wechat")]:
			if re.search(patterns, page_html, re.I):
				third_providers.append(prov)
		third_providers = list(dict.fromkeys(third_providers))  # 去重保序

		# 构建 login_methods
		methods = []
		if has_password:
			methods.append({"method": "password", "label": "账号密码登录", "detected": True, "selector": "input[type='password']"})

		phone_detected = has_phone and has_code_btn
		if phone_detected:
			methods.append({"method": "phone", "label": "手机验证码登录", "detected": True, "selector": "input[type='tel']"})

		qrcode_sub_types = []
		if has_wechat:
			qrcode_sub_types.append({"id": "wechat", "label": "微信扫码", "detected": True})
		if has_app_qr:
			qrcode_sub_types.append({"id": "app", "label": "APP扫码", "detected": True})
		if has_qrcode or qrcode_sub_types:
			qrcode_sub_types = qrcode_sub_types or [{"id": "default", "label": "二维码登录", "detected": True}]
			methods.append({"method": "qrcode", "label": "扫码登录", "detected": True, "sub_types": qrcode_sub_types, "selector": "img[src*='qrcode']"})

		if third_providers or has_oauth:
			methods.append({"method": "oauth", "label": "第三方账号登录", "detected": True, "providers": third_providers or ["wechat_oauth", "qq", "weibo"]})

		methods.append({"method": "cookie", "label": "Cookie粘贴", "detected": True})

		# 构建备注
		detected_labels = [m["label"] for m in methods if m.get("detected") and m["method"] != "cookie"]
		note_parts = [f"{json_name}登录页支持"]
		note_parts.append("/".join(detected_labels))
		if third_providers:
			note_parts.append(f"/第三方({','.join(third_providers)})")
		note = "".join(note_parts)

		cap_data = {
			"platform": json_name,
			"explored_at": datetime.now(timezone.utc).isoformat(),
			"login_url": url,
			"login_methods": methods,
			"note": note,
			"raw_detection": {
				"has_password_input": has_password,
				"has_phone_input": has_phone,
				"has_code_button": has_code_btn,
				"has_qrcode_img": has_qrcode,
				"has_wechat": has_wechat,
				"has_app_qr": has_app_qr,
				"third_party_providers": third_providers,
				"page_title": page_title,
				"page_url": page_url,
			},
			"error": None,
			"screenshot": screenshot_path,
		}

		# 保存 JSON
		with open(report_path, "w", encoding="utf-8") as f:
			json.dump(cap_data, f, ensure_ascii=False, indent=2)

		page.close()
		_ctx.close()

		return jsonify({
			"success": True, "platform": platform, "message": "登录能力已重新探索",
			"login_methods": [m["method"] for m in methods if m.get("detected")],
			"capabilities": cap_data,
		})
	except Exception as e:
		# 清理 Playwright 资源
		try:
			if 'page' in dir(): page.close()
			if '_ctx' in dir(): _ctx.close()
		except: pass
		return jsonify({"success": False, "error": f"Playwright 检测异常: {str(e)[:200]}"})


# ═══════════════════════════════════════════════════
# 扫码登录方式查询 API
# ═══════════════════════════════════════════════════
@app.route("/api/login/scan-methods/<platform>")
@login_required
def api_login_scan_methods(platform):
    """返回指定平台支持的扫码登录方式列表

    数据驱动（铁律#19）：
    直接从探索数据 *_login_capabilities.json 动态推导扫码方式
    """
    # 数据驱动：从探索 JSON 动态推导扫码方式
    cap = _load_login_capabilities(platform)
    if cap:
        login_url = cap.get("login_url", "")
        for m in cap.get("login_methods", []):
            if m.get("method") == "qrcode" and m.get("detected"):
                methods = []
                sub_types = m.get("sub_types", [])
                if sub_types:
                    for st in sub_types:
                        if st.get("detected"):
                            methods.append({
                                "id": st.get("id", "qrcode"),
                                "name": st.get("label", "扫码登录"),
                                "scan_app": st.get("label", "扫码"),
                                "hint": f"请使用{st.get('label', '扫码')}功能扫描此二维码",
                                "type": "qrcode",
                            })
                else:
                    methods.append({
                        "id": "qrcode",
                        "name": "扫码登录",
                        "scan_app": "扫码",
                        "hint": "请使用扫码功能扫描此二维码",
                        "type": "qrcode",
                    })
                return jsonify({
                    "success": True,
                    "platform": platform,
                    "login_url": login_url,
                    "methods": methods,
                    "source": "exploration",  # 标记数据来源
                })

    # 都没有 → 返回空列表，不报错（前端自动处理）
    return jsonify({
        "success": True,
        "platform": platform,
        "login_url": "",
        "methods": [],
    })


# ═══════════════════════════════════════════════════
# 登录方式演示/说明数据 API
# ═══════════════════════════════════════════════════
LOGIN_METHOD_DEMOS = {
	"password": {
		"title": "🔑 密码登录流程",
		"steps": [
			"① 输入该平台的用户名和密码",
			"② 点击「开始浏览器登录」— 系统在后台打开浏览器",
			"③ 如果出现验证码，查看截图后点击「点验证码并登录」",
			"④ 登录成功后 Cookie 自动保存，无需手动粘贴",
		],
		"note": "适合大多数论坛和博客平台，如 amobbs、mydigit、CSDN",
	},
	"qrcode": {
		"title": "📱 扫码登录流程",
		"steps": [
			"① 选择「扫码登录」方式",
			"② 点击「生成二维码」— 系统打开平台登录页并截图",
			"③ 截图中会显示二维码 / 扫码入口",
			"④ 用手机 App（微信/淘宝/论坛App等）扫码",
			"⑤ 系统自动检测到登录成功，Cookie 自动保存",
		],
		"note": "适合支持扫码登录的平台，如微信公众号、淘宝、B站等",
	},
	"cookie": {
		"title": "🍪 Cookie 粘贴（备选方案）",
		"steps": [
			"① 在浏览器中手动登录该平台",
			"② 打开 F12 → Application → Cookies → 找到该站点",
			"③ 复制所有 Cookie 字符串（或导出为 Netscape 格式）",
			"④ 粘贴到 Cookie 输入框中并保存",
		],
		"note": "Cookie 模式下需要手动续期，建议作为密码登录的备选方案",
	},
	"phone": {
		"title": "📞 手机验证码登录",
		"steps": [
			"① 选择「手机验证码登录」方式",
			"② 输入手机号码",
			"③ 点击「发送验证码」— 系统通过 Playwright 在登录页自动发送",
			"④ 查看截图中的验证码输入框，填入收到的验证码",
			"⑤ 提交后 Cookie 自动保存",
		],
		"note": "适用于支持手机号+验证码登录的平台，如知乎、掘金等",
	},
}


@app.route("/api/login/method-demo/<method>")
@login_required
def api_login_method_demo(method):
	"""返回指定登录方式的演示/说明数据"""
	demo = LOGIN_METHOD_DEMOS.get(method)
	if not demo:
		return jsonify({"success": False, "error": "未知登录方式"})
	return jsonify({"success": True, "demo": demo})
