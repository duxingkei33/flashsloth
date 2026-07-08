"""FlashSloth — 账号管理路由：统一登录引擎"""
from flashsloth.routes._app import app
from flask import jsonify, request
from flask_login import login_required, current_user

from flashsloth.routes.accounts.helpers import _get_engine_for_platform, _get_login_lock
from flashsloth.routes.accounts.crud import _save_cookie_to_account


@app.route("/api/platform/<platform>/login/start", methods=["POST"])
@login_required
def api_platform_login_start(platform):
	"""统一登录入口：启动浏览器登录"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)
	username = data.get("username", "")
	password = data.get("password", "")
	site_url = data.get("site_url", "")

	if _get_engine_for_platform(platform) == "discuz":
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id, site_url=site_url)
			result = inst.login(username, password)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "xianyu":
		from flashsloth.routes.browser_login import _get_xianyu_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_xianyu_login(sess_id)
			result = inst.login(username, password)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_oshwhub_login(sess_id)
			result = inst.login(username, password)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "generic":
		from flashsloth.plugins.generic_login import get_generic_login, close_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			method = data.get("method", "password")
			if method == "phone":
				phone = data.get("phone", "")
				result = inst.phone_login(platform, phone, site_url)
			else:
				result = inst.login(platform, username, password, site_url)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持密码登录"})


@app.route("/api/platform/<platform>/login/captcha", methods=["POST"])
@login_required
def api_platform_login_captcha(platform):
	"""统一登录：提交验证码"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)

	if _get_engine_for_platform(platform) == "discuz":
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id)
			result = inst.click_captcha_and_submit()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "xianyu":
		from flashsloth.routes.browser_login import _get_xianyu_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_xianyu_login(sess_id)
			result = inst.solve_and_login()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_oshwhub_login(sess_id)
			result = inst.submit_captcha_and_login()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "generic":
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			result = inst.submit_captcha_and_login(platform)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持验证码提交"})


@app.route("/api/platform/<platform>/login/screenshot")
@login_required
def api_platform_login_screenshot(platform):
	"""统一登录：获取页面截图"""
	if _get_engine_for_platform(platform) == "discuz":
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_discuz_login(f"user_{current_user.id}_{platform}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	elif _get_engine_for_platform(platform) == "xianyu":
		from flashsloth.routes.browser_login import _get_xianyu_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_xianyu_login(f"user_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	elif _get_engine_for_platform(platform) == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_oshwhub_login(f"user_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	elif _get_engine_for_platform(platform) == "generic":
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			inst = get_generic_login(f"generic_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	return jsonify({"success": False, "error": f"平台 {platform} 不支持截图"})


@app.route("/api/platform/<platform>/login/submit_captcha", methods=["POST"])
@login_required
def api_platform_login_submit_captcha(platform):
	"""统一登录：提交手动输入的验证码"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)
	captcha_code = data.get("captcha_code", "")

	if not captcha_code:
		return jsonify({"success": False, "error": "请输入验证码"})

	if _get_engine_for_platform(platform) == "discuz":
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id)
			# 提交文本验证码 — 填入代码，点击边框核验，再提交登录
			result = inst.submit_text_captcha(captcha_code)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "xianyu":
		return jsonify({"success": False, "error": "闲鱼不支持手动验证码输入，请使用扫码登录"})

	elif _get_engine_for_platform(platform) == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_oshwhub_login(sess_id)
			result = inst.submit_text_captcha(captcha_code)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif _get_engine_for_platform(platform) == "generic":
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			result = inst.submit_text_captcha(captcha_code, platform)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持验证码提交"})


@app.route("/api/platform/<platform>/login/poll_result", methods=["POST"])
@login_required
def api_platform_login_poll(platform):
	"""轮询登录结果（验证码提交后的异步登录流程）"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)

	if _get_engine_for_platform(platform) == "discuz":
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id)
			# 检查当前登录状态
			cookies = inst.get_cookies()
			if cookies:
				try:
					page_url = inst.page.url if inst.page else ""
					is_still_login = "login" not in page_url.lower()
				except:
					is_still_login = False

				if is_still_login:
					if aid:
						_save_cookie_to_account(aid, cookies)
					return jsonify({"logged_in": True, "cookies": cookies})

			# 检查是否需要新验证码
			try:
				screenshot = inst.take_screenshot()
				page_content = inst.page.content() if inst.page else ""
				if "验证码" in page_content or "seccode" in page_content:
					return jsonify({
						"needs_captcha": True,
						"image": screenshot,
						"error": "需要新验证码",
					})
			except:
				pass

			return jsonify({"running": True, "message": "登录进行中..."})

	elif _get_engine_for_platform(platform) == "generic":
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			result = inst.poll_login_result()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持轮询"})


@app.route("/api/platform/<platform>/login/refresh_captcha", methods=["POST"])
@login_required
def api_platform_login_refresh_captcha(platform):
	"""刷新验证码图片 — 真正点击验证码图片触发刷新，然后用 _get_captcha_image 提取"""
	if _get_engine_for_platform(platform) == "discuz":
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_discuz_login(f"user_{current_user.id}_{platform}")
			# 确保页面在登录页（线程切换会导致实例重建）
			login_url = f"{inst.site_url}/member.php?mod=logging&action=login"
			try:
				inst._ensure_browser()
				page_url = inst.page.url if inst.page else ""
				needs_nav = "login" not in page_url or "about:blank" in page_url
			except Exception:
				needs_nav = True
			if needs_nav:
				inst.page.goto(login_url, wait_until="networkidle", timeout=15000)
				import time
				time.sleep(2)
			else:
				# 页面在登录页 → 重新加载以获取新验证码
				inst.page.goto(login_url, wait_until="networkidle", timeout=15000)
				import time
				time.sleep(2)
			# 等待验证码图片加载
			try:
				inst.page.wait_for_selector("img[src*='seccode']", timeout=5000)
			except Exception:
				pass
			# 提取验证码
			captcha_result = inst._get_captcha_image()
			return jsonify({
				"success": True,
				"image": captcha_result.get("image", ""),
				"captcha_image_url": captcha_result.get("captcha_image_url", ""),
			})
	elif _get_engine_for_platform(platform) == "generic":
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			inst = get_generic_login(f"generic_{current_user.id}")
			# 尝试点击验证码图片刷新
			try:
				captcha_img = inst.page.query_selector("img[src*='captcha'], img[src*='seccode'], img[id*='captcha']")
				if captcha_img:
					captcha_img.click()
					import time
					time.sleep(1.5)
			except:
				pass
			screenshot = inst.take_screenshot()
			return jsonify({"success": True, "image": screenshot})
	return jsonify({"success": False, "error": "不支持的平台"})


@app.route("/api/platform/<platform>/login/auto_captcha", methods=["POST"])
@login_required
def api_platform_login_auto_captcha(platform):
	"""自动识别验证码（预留：ttshitu/2captcha）"""
	from flashsloth.core.captcha_handler import get_handler
	handler = get_handler()
	# 先尝试截图
	try:
		if _get_engine_for_platform(platform) == "discuz":
			from flashsloth.routes.browser_login import _get_discuz_login
			with _get_login_lock(platform):
				inst = _get_discuz_login(f"user_{current_user.id}_{platform}")
				screenshot = inst.take_screenshot()
		else:
			from flashsloth.plugins.generic_login import get_generic_login
			with _get_login_lock(platform):
				inst = get_generic_login(f"generic_{current_user.id}")
				screenshot = inst.take_screenshot()

		if screenshot:
			# 尝试自动识别
			code = handler.auto_solve(screenshot, handler.CaptchaProvider.AUTO_TTSHITU)
			if code:
				return jsonify({"success": True, "code": code})
	except:
		pass
	return jsonify({"success": False, "error": "自动识别暂未配置，请手动输入验证码"})


@app.route("/api/platform/<platform>/login/close", methods=["POST"])
@login_required
def api_platform_login_close(platform):
	"""统一登录：关闭浏览器会话"""
	if _get_engine_for_platform(platform) == "discuz":
		from flashsloth.routes.browser_login import _close_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			_close_discuz_login(sess_id)
			return jsonify({"success": True})

	elif _get_engine_for_platform(platform) == "xianyu":
		from flashsloth.routes.browser_login import _xianyu_login_instances
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _xianyu_login_instances.pop(sess_id, None)
			if inst:
				inst.close()
			return jsonify({"success": True})

	elif _get_engine_for_platform(platform) == "oshwhub":
		from flashsloth.routes.browser_login import _oshwhub_login_instances
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _oshwhub_login_instances.pop(sess_id, None)
			if inst:
				inst.close()
			return jsonify({"success": True})

	elif _get_engine_for_platform(platform) == "generic":
		from flashsloth.plugins.generic_login import close_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			close_generic_login(sess_id)
			return jsonify({"success": True})

	return jsonify({"success": False, "error": f"平台 {platform} 不支持浏览器登录"})
