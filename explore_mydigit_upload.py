"""
数码之家 — 专门探上传格式限制
"""
import json, time, sys, os, re
SITE = "https://www.mydigit.cn"
COOKIE_STR = "security_session_verify=f914cba344c390591e5da3fd9a180323; VhUn_2132_saltkey=IrvJJvVg; VhUn_2132_lastvisit=1782748430; VhUn_2132_lastact=1782752032%09member.php%09logging; VhUn_2132_ulastactivity=1782752032%7C0; VhUn_2132_auth=cfadIKXWJI7YytmyzLevcaMGKn3dQTZ9tLjFhAogPKqJ8UYL6Ug95miAjsDdVbHHUft7NVN9EAgf0xfoZHVrHPul2BSZ; VhUn_2132_lastcheckfeed=1722267%7C1782752032; VhUn_2132_checkfollow=1; VhUn_2132_lip=103.97.178.234%2C1782752032"

FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright
import time as _time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled','--no-sandbox'])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN"
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    """)
    for c in COOKIE_STR.split("; "):
        if "=" in c:
            k, v = c.split("=", 1)
            ctx.add_cookies([{"name": k.strip(), "value": v.strip(), "domain": ".mydigit.cn", "path": "/"}])
    
    page = ctx.new_page()
    print("[1] 访问发帖页...")
    page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid=40", wait_until="networkidle", timeout=60000)
    _time.sleep(3)
    
    # 截图整个页面
    page.screenshot(path="/tmp/mydigit_upload_page.png", full_page=True)
    print("  已截图: /tmp/mydigit_upload_page.png")
    
    # 获取页面源码
    html = page.content()
    
    # 查找所有上传相关的 JS 配置
    upload_configs = re.findall(r'upload\s*[=:]\s*\{[^}]+?\}', html, re.DOTALL)
    for i, cfg in enumerate(upload_configs[:5]):
        print(f"\n  上传配置[{i}]: {cfg[:300]}")
    
    # 查找 swfupload 配置
    swf_configs = re.findall(r'swfupload[^}]+?\}', html, re.DOTALL)
    for i, cfg in enumerate(swf_configs[:3]):
        print(f"\n  SWF配置[{i}]: {cfg[:300]}")
    
    # 查找 filetype / extension 配置
    filetypes = re.findall(r'(?:file_type|filetype|ext[_\s]?type|accept|accept_ext|allow_ext|extension)[^;。\n]{0,200}', html, re.IGNORECASE)
    if filetypes:
        print(f"\n  文件类型配置: {filetypes[:5]}")
    
    # 查找 ext 数组
    ext_arrays = re.findall(r'ext\s*[=:]\s*\{[^}]+\}', html)
    for a in ext_arrays[:3]:
        print(f"\n  ext对象: {a[:200]}")
    
    ext_lists = re.findall(r"(?:extensions|ext)\s*[=:]\s*\['[^\]]+'\]", html)
    for l in ext_lists[:3]:
        print(f"\n  ext列表: {l[:200]}")
    
    # 查找所有 .xxx 扩展名格式提示
    all_exts = re.findall(r'\.(?:jpg|jpeg|png|gif|bmp|zip|rar|pdf|doc|docx|txt|7z|tar|gz|xls|xlsx|ppt|pptx|mp4|avi|mkv|mp3|wav|flac)', html, re.IGNORECASE)
    unique_exts = list(set(all_exts))
    print(f"\n  页面中出现的扩展名: {sorted(unique_exts)}")
    
    # 特别搜索上传弹出框里的内容
    # 查找 <div id='uploadapp'> 或类似上传区域
    upload_div = page.query_selector("#uploadapp, #attachnotice, .upload_area")
    if upload_div:
        print(f"\n  上传区域HTML:")
        print(upload_div.inner_html()[:1000])
    
    # 查找 "允许" "支持" "格式" 等关键词附近的文本
    allow_text = re.findall(r'[^。\n]{0,10}(?:允许|支持|格式|类型)[^。\n]{0,100}(?:\.\w+)', html)
    if allow_text:
        print(f"\n  允许的格式提示: {allow_text[:5]}")
    
    # 找 swf 上传 URL
    upload_urls = re.findall(r'"(https?://[^"]*(?:upload|swfupload|attach)[^"]*)"', html)
    print(f"\n  上传URLs: {upload_urls[:3]}")
    
    # 查找 uid 和 hash
    uids = re.findall(r'uid["\']?\s*[:=]\s*["\']?(\d+)["\']?', html)
    hashes = re.findall(r'hash["\']?\s*[:=]\s*["\']?([a-f0-9]+)["\']?', html)
    print(f"\n  uid: {uids[:3]}")
    print(f"  hash: {hashes[:3]}")
    
    # 检查上传按钮的 accept 属性
    file_inputs = page.query_selector_all("input[type='file']")
    for fi in file_inputs:
        accept = fi.get_attribute("accept")
        print(f"\n  文件输入框 accept: {accept}")
    
    # 检查上传按钮周边文字
    upload_btns = page.query_selector_all("a[href*='upload'], #uploadapp a, .upload_btn, .attach_btn")
    for btn in upload_btns:
        print(f"\n  上传按钮: '{btn.inner_text()}' href={btn.get_attribute('href')}")
    
    browser.close()
