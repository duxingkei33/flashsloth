# -*- coding: utf-8 -*-
"""OSHWHub E2E subprocess – verify article creation (with button debugging)"""
import json, time, sys, os, re, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pw")

SITE = "__SITE__"
USERNAME = "__USERNAME__"
PASSWORD = "__PASSWORD__"
COVER = "__COVER__"
BODY = "__BODY__"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugins.oshwhub_login import OshwhubPlaywrightLogin

login = OshwhubPlaywrightLogin(site_url=SITE)
result = login.login(USERNAME, PASSWORD, captcha_provider="manual")
if not result.get("logged_in"):
    logger.error(f"❌ 登录失败: {result.get('error', '')}")
    if result.get("needs_captcha"):
        logger.error(f"  需要验证码: {result.get('captcha_type', 'unknown')}")
    login.close()
    sys.exit(1)

logger.info("✅ 登录成功")
page = login.page

try:
    # 1. Navigate to article/create
    logger.info("[1] /article/create ...")
    page.goto(f"{SITE}/article/create", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    if "login" in page.url.lower():
        logger.error(f"redirected: {page.url}"); login.close(); sys.exit(1)
    logger.info(f"  URL: {page.url[:80]}")
    page.screenshot(path="/tmp/oshwhub_e2e_a_create.png")

    # 2. Fill title
    logger.info("[2] 标题...")
    ti = page.locator("#title").first
    test_title = f"【E2E存草稿】ESP32-S3-{int(time.time())}"
    ti.fill(test_title)
    logger.info(f"  {test_title[:40]}...")

    # 3. Fill intro
    ii = page.locator("#introduction").first
    if ii.count() > 0: ii.fill("ESP32-S3 摄像头采集优化经验分享。")

    # 4. Cover
    if COVER:
        fi = page.locator("input[type='file']").first
        if fi.count() > 0:
            fi.set_input_files(COVER); time.sleep(3)
            logger.info("  封面 OK")
            # 关闭 ant-modal（Escape 触发 Ant Design 原生关闭）
            page.keyboard.press("Escape"); time.sleep(0.8)

    # 5. Category radio
    radios = page.locator("input[type='radio']")
    if radios.count() >= 1:
        radios.first.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); }")
        time.sleep(0.5)

    # 6. TinyMCE body
    try:
        page.wait_for_selector(".tox-tinymce", timeout=5000)
        page.evaluate("(() => { const ed = tinymce?.activeEditor; if (ed) ed.setContent(" + json.dumps(BODY) + "); })()")
    except:
        pass

    # 7. Agreement
    page.evaluate("""() => {
        const cb = document.querySelector('#is_permit');
        if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true}));
            const acb = cb.closest('.ant-checkbox');
            if (acb) acb.classList.add('ant-checkbox-checked'); }
    }""")

    page.screenshot(path="/tmp/oshwhub_e2e_b_before_save.png")

    # 8. Debug: list all buttons on the page
    logger.info("[3] 列出页面按钮...")
    all_buttons = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button')).map(b =>
            ({ text: b.innerText.trim(), visible: b.offsetParent !== null,
              classes: b.className.slice(0,60), type: b.type || '' })
        );
    }""")
    for b in all_buttons:
        if b['text']:
            logger.info(f"  btn: [{b['text']}] visible={b['visible']} cls={b['classes']}")

    # Close any overlay/modal — use Escape instead of DOM remove
    page.keyboard.press("Escape"); time.sleep(0.8)
    # Also try clicking close button as fallback
    try:
        close_btn = page.locator('.ant-modal-close').first
        if close_btn.count() > 0 and close_btn.is_visible():
            close_btn.click(); time.sleep(0.5)
    except:
        pass

    after_url = page.url
    # Try save/submit buttons - prioritize '保 存' (存草稿)
    save_done = False
    
    # First, try the exact save button by text
    for btn_text in ['保 存', '保存', '存草稿', '存入草稿']:
        try:
            btn = page.locator(f"button:has-text('{btn_text}')").first
            if btn.count() > 0:
                logger.info(f"  找到按钮: [{btn_text}], visible={btn.is_visible()}")
                if btn.is_visible():
                    page.keyboard.press("Escape"); time.sleep(0.5)
                    btn.click(force=True, timeout=5000)
                    time.sleep(3)
                    if page.url != after_url:
                        after_url = page.url
                        logger.info(f"  URL changed to: {after_url}")
                    save_done = True
                    break
        except Exception as e:
            logger.warning(f"  尝试 [{btn_text}] 失败: {e}")

    # Fallback: filter from button list
    if not save_done:
        keywords = ['保存', '发布', '发作品', '提交', '存草稿', '存为草稿', '下一步']
        for b_btn in all_buttons:
            txt = b_btn['text'].replace(' ', '')
            if not txt or not b_btn['visible']:
                continue
            if any(k in txt for k in keywords):
                logger.info(f"  尝试点击 (fallback): [{txt}]")
                try:
                    btn = page.locator(f"button:has-text('{b_btn['text']}')").first
                    if btn.count() > 0:
                        page.keyboard.press("Escape"); time.sleep(0.5)
                        btn.click(force=True, timeout=5000)
                        time.sleep(3)
                        if page.url != after_url:
                            after_url = page.url
                        save_done = True
                        break
                except Exception as e:
                    logger.warning(f"  点击 [{txt}] 失败: {e}")

    if not save_done:
        logger.warning("  ⚠️ 未找到保存按钮，尝试直接提交表单...")
        # Try keyboard shortcut or form submit
        page.keyboard.press("Control+Enter")
        time.sleep(3)
        page.evaluate("document.querySelector('form')?.requestSubmit()")
        time.sleep(3)

    after_url = page.url
    logger.info(f"  URL after save: {after_url}")
    page.screenshot(path="/tmp/oshwhub_e2e_c_after_save.png")

    # Check for success/error messages
    for msg_sel in ['.ant-message', '.ant-notification', '.el-message', '[class*="toast"]', '[class*="notice"]']:
        try:
            el = page.locator(msg_sel).first
            if el.count() > 0 and el.is_visible():
                logger.info(f"  Message: {el.inner_text()[:200]}")
        except:
            pass

    # 9. Try to find the article in user's list
    logger.info("[4] 寻找草稿箱...")

    article_id = None
    m = re.search(r'/article/([a-zA-Z0-9_]+)', after_url)
    if m:
        article_id = m.group(1)
        logger.info(f"  Article ID from URL: {article_id}")

    draft_urls = [
        f"{SITE}/user/articles?type=draft",
        f"{SITE}/user/articles",
        f"{SITE}/user/center/articles?type=draft",
        f"{SITE}/user/center/articles",
        f"{SITE}/my/articles",
        f"{SITE}/my/articles?type=draft",
    ]

    found = False
    for url in draft_urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            content = page.content()
            if test_title[:15] in content or (article_id and article_id in content):
                logger.info(f"  ✅ 在 {url} 找到文章！")
                found = True
                break
            logger.info(f"  ℹ️ {url}: not found (title: {page.title()[:40]})")
        except Exception as e:
            logger.info(f"  ℹ️ {url}: {e}")

    if not found:
        logger.warning("  ⚠️ 未在已知URL找到草稿")
        body_text = page.inner_text("body")[:300]
        logger.info(f"  body: {body_text[:200]}")
        page.screenshot(path="/tmp/oshwhub_e2e_d_final.png")

        # Try to find user links from homepage
        page.goto(f"{SITE}/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        content = page.content()
        user_links = re.findall(r'href=[\'"](/user/[^\'"]+)[\'"]', content)
        logger.info(f"  首页用户链接: {user_links[:10]}")
        page.screenshot(path="/tmp/oshwhub_e2e_e_index.png")

    logger.info("=" * 50)
    logger.info("✨ 完成")

except Exception as e:
    logger.error(f"❌ {e}")
    import traceback; traceback.print_exc()
    try: page.screenshot(path="/tmp/oshwhub_e2e_error.png")
    except: pass
finally:
    login.close()
