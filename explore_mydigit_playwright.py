"""
数码之家 (mydigit.cn) — Playwright 浏览器深度探索
协议：
  - 2-5秒间隔
  - 单Session最多5次操作
  - 遇418/验证码/拒绝连接立即停止
  - 只读不写
  - 分散访问不同页面，不刷同一页
"""
import json, time, sys, os, re

SITE = "https://www.mydigit.cn"
COOKIE_STR = "security_session_verify=f914cba344c390591e5da3fd9a180323; VhUn_2132_saltkey=IrvJJvVg; VhUn_2132_lastvisit=1782748430; VhUn_2132_lastact=1782752032%09member.php%09logging; VhUn_2132_ulastactivity=1782752032%7C0; VhUn_2132_auth=cfadIKXWJI7YytmyzLevcaMGKn3dQTZ9tLjFhAogPKqJ8UYL6Ug95miAjsDdVbHHUft7NVN9EAgf0xfoZHVrHPul2BSZ; VhUn_2132_lastcheckfeed=1722267%7C1782752032; VhUn_2132_checkfollow=1; VhUn_2132_lip=103.97.178.234%2C1782752032"

# 切换到 FS venv 的 playwright
FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
os.environ["PATH"] = os.path.join(FS_VENV, "bin") + ":" + os.environ.get("PATH", "")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

findings = {}
op_count = 0
MAX_OPS = 5
last_request_time = 0

def human_delay(min_s=2, max_s=5):
    """2-5秒随机延迟，模拟人类阅读时间"""
    global last_request_time
    now = time.time()
    if last_request_time > 0:
        elapsed = now - last_request_time
        if elapsed < min_s:
            time.sleep(min_s - elapsed + (time.time() % 2))
    delay = min_s + (time.time() % (max_s - min_s))
    time.sleep(delay)
    last_request_time = time.time()

def log_op(num, desc, detail=""):
    global op_count
    op_count += 1
    print(f"\n{'='*60}")
    print(f"[OP {num}/{MAX_OPS}] {desc}")
    if detail:
        print(f"  {detail}")

def check_ban(page):
    """检查是否被反爬/封杀"""
    url = page.url
    title = page.title()
    body_text = page.content()[:500].lower()
    ban_signals = [
        "418", "429", "403", "too many requests", 
        "rate limit", "blocked", "captcha", "验证码",
        "拒绝访问", "频繁", "安全验证",
    ]
    for signal in ban_signals:
        if signal in body_text or signal in url.lower() or signal in title.lower():
            print(f"  ⛔ 检测到反爬信号: '{signal}' — 立即停止")
            return True
    # 检查页面是否是错误页
    error_el = page.query_selector("#messagetext, .alert_error, .alert_info")
    if error_el:
        err_text = error_el.inner_text()
        if any(s in err_text.lower() for s in ["拒绝", "权限", "错误", "禁止"]):
            print(f"  ⛔ 页面错误: {err_text[:100]} — 停止")
            return True
    return False

def explore_mydigit():
    global op_count, last_request_time
    op_count = 0
    last_request_time = 0
    
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        # 用有头模式（headless=false）可以开无头，但我们已经尽量模拟人了
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )
        
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        
        # 注入反检测脚本
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)
        
        # 设置 Cookie
        for c in COOKIE_STR.split("; "):
            if "=" in c:
                k, v = c.split("=", 1)
                ctx.add_cookies([{
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": ".mydigit.cn",
                    "path": "/"
                }])
        
        page = ctx.new_page()
        
        # ============================================================
        # OP 1: 访问首页 — 检查登录状态 + 看论坛结构
        # ============================================================
        log_op(1, "访问首页，检查登录状态 + 论坛结构")
        page.goto(f"{SITE}/forum.php", wait_until="networkidle", timeout=60000)
        human_delay()
        
        if check_ban(page):
            browser.close()
            return {"error": "BANNED", "findings": findings}
        
        # 截图
        page.screenshot(path="/tmp/mydigit_op1_home.png", full_page=True)
        print(f"  截图: /tmp/mydigit_op1_home.png")
        
        # 检查登录
        username_el = page.query_selector(".vwmy, .z a[href*='space-uid'], #um .z a")
        login_link = page.query_selector("a[href*='member.php?mod=logging']")
        print(f"  已登录: {username_el is not None} (登录链接: {login_link is not None})")
        if username_el:
            print(f"  用户名: {username_el.inner_text()}")
        
        # 读取公告/通知栏
        notice = page.query_selector("#announcement, .notice, #wp .notice")
        if notice:
            print(f"  公告: {notice.inner_text()[:200]}")
            findings["notice"] = notice.inner_text()[:500]
        
        # 获取板块列表
        forums = page.query_selector_all("h2 a[href*='fid=']")
        print(f"  板块数: {len(forums)}")
        forum_list = []
        for f in forums[:15]:
            name = f.inner_text().strip()
            href = f.get_attribute("href") or ""
            fid_m = re.search(r'fid=(\d+)', href)
            fid = fid_m.group(1) if fid_m else ""
            forum_list.append({"name": name, "fid": fid})
            print(f"    [{fid}] {name}")
        findings["forums"] = forum_list
        
        # ============================================================
        # OP 2: 访问板块公告/版规页
        # ============================================================
        log_op(2, "访问公告页 + 检查版规")
        page.goto(f"{SITE}/forum.php?mod=announcement", wait_until="networkidle", timeout=60000)
        human_delay()
        
        if check_ban(page):
            browser.close()
            return {"error": "BANNED", "findings": findings}
        
        ann_content = page.query_selector(".mn, #annbody, .annbody")
        if ann_content:
            text = ann_content.inner_text()[:1500]
            print(f"  公告内容:\n{text}")
            findings["announcement"] = text
        else:
            print("  公告页无可见内容（可能无权限）")
        
        page.screenshot(path="/tmp/mydigit_op2_announcement.png")
        
        # ============================================================
        # OP 3: 访问板块 fid=40 + 读置顶帖版规
        # ============================================================
        log_op(3, "访问板块 fid=40，读取版规帖")
        page.goto(f"{SITE}/forum.php?mod=forumdisplay&fid=40", wait_until="networkidle", timeout=60000)
        human_delay()
        
        if check_ban(page):
            browser.close()
            return {"error": "BANNED", "findings": findings}
        
        # 读取板块规则
        rules_el = page.query_selector("#forumrules, .rules, .bn")
        if rules_el:
            rules_text = rules_el.inner_text()[:2000]
            print(f"  板块规则:\n{rules_text}")
            findings["forum_rules"] = rules_text
        else:
            print("  板块规则区域不可见")
        
        # 找置顶帖 — 优先读取含"规"字的
        sticky_threads = page.query_selector_all("th.common a.xst")
        print(f"\n  帖子列表 ({len(sticky_threads)} 个):")
        rule_thread = None
        for t in sticky_threads[:15]:
            title = t.inner_text().strip()
            href = t.get_attribute("href") or ""
            print(f"    - {title[:60]}")
            if any(kw in title for kw in ["规", "公告", "须知", "指南", "必读", "限制", "上传", "要求", "帮助"]):
                rule_thread = (title, href)
        
        page.screenshot(path="/tmp/mydigit_op3_forum40.png")
        
        # ============================================================
        # OP 4: 读取版规帖内容（如果有）
        # ============================================================
        log_op(4, "读取版规帖子内容")
        
        if rule_thread:
            title, href = rule_thread
            full_url = href if href.startswith("http") else f"{SITE}/{href.lstrip('/')}"
            print(f"  读取: {title[:50]} → {full_url}")
            page.goto(full_url, wait_until="networkidle", timeout=60000)
            human_delay()
            
            if check_ban(page):
                browser.close()
                return {"error": "BANNED", "findings": findings}
            
            # 提取帖子内容
            post_content = page.query_selector(".t_fsz, .pcb, .t_msgfont, #postlist .t_f, .plc .message")
            if post_content:
                text = post_content.inner_text()
                print(f"  📄 内容 ({len(text)} chars):")
                print(text[:2000])
                findings["rule_post"] = text[:5000]
            
            page.screenshot(path=f"/tmp/mydigit_op4_rule.png")
        else:
            print("  未找到版规帖子，阅读第一个普通帖子替代")
            # 随便看一个帖子，了解帖子结构
            first_thread = page.query_selector("th a.xst")
            if first_thread:
                href = first_thread.get_attribute("href") or ""
                full_url = href if href.startswith("http") else f"{SITE}/{href.lstrip('/')}"
                page.goto(full_url, wait_until="networkidle", timeout=60000)
                human_delay()
                
                if check_ban(page):
                    browser.close()
                    return {"error": "BANNED", "findings": findings}
                
                post = page.query_selector(".t_fsz, .pcb, .message")
                if post:
                    findings["sample_post"] = post.inner_text()[:3000]
                    # 检查帖子内的附件
                    attachments = page.query_selector_all(".attach, .attl, .attachements a")
                    if attachments:
                        attach_info = [a.inner_text()[:100] for a in attachments[:5]]
                        print(f"  附件信息: {attach_info}")
                        findings["attachments"] = attach_info
                
                page.screenshot(path="/tmp/mydigit_op4_post.png")
        
        # ============================================================
        # OP 5: 访问发帖页面 — 检查编辑器所有字段 + 上传限制
        # ============================================================
        log_op(5, "访问发帖页面，检查编辑器+上传限制")
        page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid=40", wait_until="networkidle", timeout=60000)
        human_delay()
        
        if check_ban(page):
            browser.close()
            return {"error": "BANNED", "findings": findings}
        
        # 检查发帖权限
        error_el = page.query_selector("#messagetext, .alert_error")
        if error_el:
            err_text = error_el.inner_text()[:200]
            print(f"  ⚠️ 发帖权限错误: {err_text}")
            findings["post_permission_error"] = err_text
        else:
            print("  ✅ 有发帖权限")
            findings["post_permission"] = "✅ 有"
        
        # ---- 标题输入框 ----
        title_input = page.query_selector("input#subject")
        if title_input:
            maxlen = title_input.get_attribute("maxlength")
            placeholder = title_input.get_attribute("placeholder")
            print(f"  标题: maxlength={maxlen}, placeholder={placeholder}")
            findings["title_maxlength"] = int(maxlen) if maxlen else 80
        
        # ---- 编辑器（textarea / iframe / 富文本） ----
        textarea = page.query_selector("textarea#message, textarea#fastpostmessage")
        if textarea:
            ta_name = textarea.get_attribute("name")
            ta_rows = textarea.get_attribute("rows")
            print(f"  textarea: name={ta_name}, rows={ta_rows}")
            findings["editor"] = {"type": "textarea", "name": ta_name, "rows": ta_rows}
        else:
            # 可能是 iframe 富文本编辑器
            iframe = page.query_selector("iframe[id^='e_iframe'], .editor_iframe")
            if iframe:
                print(f"  富文本编辑器 iframe: {iframe.get_attribute('id')}")
                findings["editor"] = {"type": "richtext_iframe", "id": iframe.get_attribute("id")}
            else:
                print("  未找到编辑器")
                findings["editor"] = {"type": "unknown"}
        
        # ---- 主题分类 ----
        typeid_select = page.query_selector("select[name='typeid']")
        if typeid_select:
            options = typeid_select.query_selector_all("option")
            categories = []
            for opt in options:
                val = opt.get_attribute("value")
                if val and val != "0":
                    categories.append({"id": val, "name": opt.inner_text().strip()})
            print(f"  主题分类: {len(categories)} 个")
            for c in categories[:10]:
                print(f"    [{c['id']}] {c['name']}")
            findings["categories"] = categories
        
        # ---- 上传区域 ----
        upload_area = page.query_selector("#attachnotice_img, .upload_area, #uploadapp, a[href*='upload']")
        if upload_area:
            upload_html = upload_area.inner_html()[:300]
            print(f"  上传区域: 存在")
            
            # 查找上传按钮/链接
            upload_btn = page.query_selector("a[href*='upload'], #uploadapp a")
            if upload_btn:
                print(f"  上传按钮: {upload_btn.inner_text()}")
            
            # 查找上传限制提示
            upload_tip = page.query_selector("#uploadtip, .uploadtip, .tip, .notice")
            if upload_tip:
                tip_text = upload_tip.inner_text()
                print(f"  上传提示: {tip_text[:500]}")
                findings["upload_tips"] = tip_text[:1000]
        else:
            print("  上传区域: 未直接显示（可能需点击高级模式）")
            # 检查有没有"高级模式"按钮
            advanced = page.query_selector("a[href*='action=newthread'][href*='topicsubmit']")
            if advanced:
                print(f"  高级模式按钮: {advanced.inner_text()}")
                findings["editor"]["need_advanced"] = True
        
        # ---- 提取页面中所有能看到的上传/附件限制 ----
        page_source = page.content()
        
        # 搜索扩展名限制
        ext_matches = re.findall(
            r'(?:允许|支持|附件|扩展名|格式|类型)[：:\s]*[^。\n]{0,100}(?:\.\w+(?:\s*[,，、]\s*\.?\w+)*)',
            page_source
        )
        if ext_matches:
            print(f"  扩展名/格式限制: {ext_matches[:3]}")
            findings["upload_extensions"] = ext_matches[:3]
        
        # 搜索大小限制
        size_matches = re.findall(
            r'(?:大小|尺寸|限制|上限|最大)[：:\s]*[^。\n]{0,50}(?:\d+\.?\d*\s*(?:KB|MB|GB|K|M))',
            page_source
        )
        if size_matches:
            print(f"  大小限制: {size_matches[:3]}")
            findings["upload_size_limits"] = size_matches[:3]
        
        # 搜索每日上传限制
        daily_matches = re.findall(
            r'(?:每天|每日|今日)[^。\n]{0,50}(?:\d+)[^。\n]{0,50}(?:张|个|次|MB|KB)',
            page_source
        )
        if daily_matches:
            print(f"  每日限制: {daily_matches[:3]}")
            findings["daily_limits"] = daily_matches[:3]
        
        # 搜索图片尺寸限制
        dim_matches = re.findall(
            r'(?:像素|分辨率|尺寸|宽|高)[：:\s]*[^。\n]{0,50}(?:\d+\s*[xX×]\s*\d+)',
            page_source
        )
        if dim_matches:
            print(f"  图片尺寸限制: {dim_matches[:3]}")
            findings["image_dimensions"] = dim_matches[:3]
        
        page.screenshot(path="/tmp/mydigit_op5_editor.png", full_page=True)
        
        # ============================================================
        # 探索结束 — 汇总
        # ============================================================
        print(f"\n{'='*60}")
        print(f"探索完成! 共 {op_count}/{MAX_OPS} 次操作")
        print(f"发现 {len(findings)} 条信息")
        
        browser.close()
        return {"error": None, "findings": findings}


if __name__ == "__main__":
    print("=" * 60)
    print("数码之家 (mydigit.cn) — Playwright 深度探索")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"协议: 2-5秒间隔 | 最多{MAX_OPS}次操作 | 遇封停 | 只读不写")
    print("=" * 60)
    
    result = explore_mydigit()
    
    output_path = "/tmp/mydigit_playwright_exploration.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    if result.get("error") == "BANNED":
        print(f"\n⛔ 探索被反爬中断！结果已保存至 {output_path}")
    else:
        print(f"\n✅ 探索成功！结果已保存至 {output_path}")
        print(f"\n发现摘要:")
        for k, v in result.get("findings", {}).items():
            if isinstance(v, str) and len(v) > 100:
                print(f"  📌 {k}: {v[:100]}...")
            elif isinstance(v, list) and len(v) > 3:
                print(f"  📌 {k}: [{len(v)} items] {v[:3]}...")
            else:
                print(f"  📌 {k}: {v}")
