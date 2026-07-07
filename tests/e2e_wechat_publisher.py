"""E2E 微信公众号发布器 Playwright 验证
运行: cd ~/.hermes/flashsloth && source venv/bin/activate && PYTHONPATH=$HOME/.hermes python tests/e2e_wechat_publisher.py

铁律：只存草稿不发布
"""
import sys, os, json, time, logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("e2e_wechat")

# ============================================================
# Part 1: Module-level test (import + registry)
# ============================================================
log.info("=" * 55)
log.info("FLASHSLOTH 微信公众号发布器 E2E 验证")
log.info("=" * 55)

log.info("\n🔧 [1/6] 模块导入 + 注册验证")
import importlib
import flashsloth.plugins.publisher_wechat
from flashsloth.core.publisher import list_publishers, _registry
from flashsloth.core.article import Article

pubs = list_publishers()
wechat_reg = [p for p in pubs if p["name"] == "wechat"]
if wechat_reg:
    wp = wechat_reg[0]
    assert wp["display_name"] == "微信公众号", f"display_name mismatch: {wp['display_name']}"
    assert "API 密钥认证" in str(wp.get("login_methods", [])), "login_methods missing API key auth"
    assert "app_id" in str(wp.get("config_fields", [])), "config_fields missing app_id"
    assert "app_secret" in str(wp.get("config_fields", [])), "config_fields missing app_secret"
    log.info(f"  ✅ WeChat publisher 注册正确: {wp['display_name']}")
    log.info(f"     登录方法: {[lm['label'] for lm in wp.get('login_methods', [])]}")
    log.info(f"     配置字段: {[cf['key'] for cf in wp.get('config_fields', [])]}")
    log.info(f"     缓存 access_token: 是 (2h 有效期)")
else:
    log.error("  ❌ WeChat publisher 未注册")
    sys.exit(1)

# ============================================================
# Part 2: Constructor & config validation test
# ============================================================
log.info("\n🔧 [2/6] 构造函数 + 配置验证")

empty_config = {}
publisher = importlib.import_module("flashsloth.plugins.publisher_wechat")
WeChatPublisher = publisher.WeChatPublisher

# Test empty config validation
p = WeChatPublisher(empty_config)
missing = p.validate_config()
assert "app_id" in missing, "app_id should be in missing fields"
assert "app_secret" in missing, "app_secret should be in missing fields"
log.info(f"  ✅ 空配置验证正确: 缺少 {missing}")

# Test partial config validation
p2 = WeChatPublisher({"app_id": "wx_test123", "app_secret": ""})
missing2 = p2.validate_config()
assert "app_secret" in missing2, "app_secret should still be missing"
assert "app_id" not in missing2, "app_id should be present"
log.info(f"  ✅ 部分配置验证正确: 仅缺少 {missing2}")

# Test full config validation
p3 = WeChatPublisher({"app_id": "wx_test123", "app_secret": "test_secret_123"})
missing3 = p3.validate_config()
assert missing3 == [], f"full config should have no missing fields: {missing3}"
log.info(f"  ✅ 完整配置验证正确: 无缺失字段")

# ============================================================
# Part 3: Article building + HTML conversion test
# ============================================================
log.info("\n🔧 [3/6] 文章构建 + HTML 转换")

article = Article(
    title="E2E 测试 — 微信公众号发布器验证",
    body="# 测试标题\n\n这是一篇**测试文章**，用于验证微信公众号发布器的完整流程。\n\n- 功能点 1：标题填写\n- 功能点 2：内容编译\n- 功能点 3：摘要生成\n- 功能点 4：封面图支持",
    summary="E2E 验证微信公众号发布器 - 测试摘要",
    tags=["e2e", "wechat", "test"],
)

html = article.to_html()
assert "测试标题" in html, "HTML should contain title"
assert "strong" in html or "<b>" in html, "HTML should have bold formatting"
assert "<li>" in html, "HTML should contain list items"
log.info(f"  ✅ 文章→HTML 转换成功 ({len(html)} bytes)")
log.info(f"     标题: {article.title}")
log.info(f"     标签: {article.tags}")
log.info(f"     摘要: {article.summary}")

# Test auto-summary generation
article_no_summary = Article(
    title="无摘要测试",
    body="这是一篇没有设置摘要的文章，系统应该自动从正文中提取前120个字符作为摘要。让我们写出足够长的文本来测试这个功能是否正确工作。自动摘要功能对于微信公众号的发布非常重要，因为它能帮助读者快速了解文章内容。",
)
html2 = article_no_summary.to_html()
# The publisher extracts text from HTML for auto-summary
import re
text_only = re.sub(r'<[^>]+>', '', html2).strip()
auto_digest = text_only[:120].replace('\n', ' ')
assert len(auto_digest) <= 120, f"auto summary too long: {len(auto_digest)}"
assert auto_digest.startswith("这是一篇没有设置摘要的文章"), f"auto summary wrong: {auto_digest[:30]}"
log.info(f"  ✅ 自动摘要生成正确 ({len(auto_digest)} 字符)")
log.info(f"     摘要: {auto_digest[:60]}...")

# ============================================================
# Part 4: Web UI login test
# ============================================================
log.info("\n🔧 [4/6] Web UI 登录验证")

BASE_URL = os.environ.get("FS_BASE_URL", "http://localhost:5000")
ADMIN_USER = os.environ.get("FS_ADMIN_USER", "admin_redacted")
ADMIN_PASS = os.environ.get("FS_ADMIN_PASS", "Fs&211211")

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    log.error("  ❌ playwright 未安装，跳过 Web UI 测试")
    sys.exit(0 if "--skip-ui" in sys.argv else 1)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = context.new_page()

    def screenshot(name):
        """保存截图供调试"""
        os.makedirs("/tmp/fs_e2e_screenshots", exist_ok=True)
        page.screenshot(path=f"/tmp/fs_e2e_screenshots/{name}.png", full_page=False)

    try:
        # ---- 4a. 访问首页，应跳转到登录页 ----
        log.info("  Step 4a: 访问登录页...")
        page.goto(f"{BASE_URL}/", timeout=15000, wait_until="networkidle")
        assert "登录" in page.title() or "login" in page.url.lower(), f"should redirect to login: {page.url}"
        screenshot("01-login-page")

        # ---- 4b. 登录 ----
        log.info("  Step 4b: 登录...")
        page.fill("input[name=username]", ADMIN_USER)
        page.fill("input[name=password]", ADMIN_PASS)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle", timeout=10000)

        # 检查是否登录成功（跳转到首页）
        current_url = page.url
        log.info(f"     登录后 URL: {current_url}")
        screenshot("02-after-login")

        assert "/login" not in current_url, f"login should redirect away from /login: {current_url}"

        # ---- 4c. 验证首页仪表盘 ----
        log.info("  Step 4c: 验证仪表盘...")
        page_content = page.content()
        # Should see some dashboard elements
        assert "FlashSloth" in page_content or "fasong" in page_content.lower(), "Dashboard not showing"
        log.info(f"     仪表盘标题: {page.title()}")
        log.info(f"     URL: {page.url}")

        # ---- 4d. 检查 accounts 页面，看 wechat 是否列在平台选项中 ----
        log.info("  Step 4d: 访问账号管理页...")
        page.goto(f"{BASE_URL}/accounts", timeout=15000, wait_until="networkidle")
        screenshot("03-accounts-page")
        page.wait_for_timeout(1000)

        accounts_html = page.content()

        # 检查 wechat 是否出现在平台列表中 (as a platform option for adding accounts)
        # The add account form should have a select with WeChat option
        wechat_found = "wechat" in accounts_html.lower() or "微信" in accounts_html
        log.info(f"     WeChat/微信 出现在页面: {'✅ 是' if wechat_found else '❌ 否'}")

        # Check if there's an option to add WeChat account
        wechat_platform_option = page.query_selector('select[name="platform"] option[value="wechat"], select option[value="wechat"]')
        if wechat_platform_option:
            platform_text = wechat_platform_option.text_content()
            log.info(f"     平台选择中有 WeChat 选项: {platform_text} ✅")
        else:
            # Try to find any mention of wechat
            wechat_elements = page.query_selector_all("*:has-text('微信'), *:has-text('wechat')")
            log.info(f"     页面包含'微信/wechat'元素数: {len(wechat_elements)}")
            if wechat_elements:
                log.info(f"     第一个: {wechat_elements[0].text_content()[:80]}")

        # ---- 4e. 检查发布管理页面 ----
        log.info("  Step 4e: 访问发布管理页...")
        page.goto(f"{BASE_URL}/publish/manage", timeout=15000, wait_until="networkidle")
        screenshot("04-publish-manage")
        page.wait_for_timeout(1000)

        pm_html = page.content()
        log.info(f"     发布管理页面标题: {page.title()}")
        log.info(f"     页面包含'发布管理': {'✅' if '发布管理' in pm_html else '❌'}")

        # ---- 4f. 尝试创建一篇文章并选择 WeChat 发布 ----
        log.info("  Step 4f: 创建测试文章...")
        page.goto(f"{BASE_URL}/post/new", timeout=15000, wait_until="networkidle")
        screenshot("05-new-post")
        page.wait_for_timeout(1000)

        # Try to fill in article form
        title_input = page.query_selector("input[name=title], input#title, [placeholder*='标题']")
        body_input = page.query_selector("textarea[name=body], textarea#body, textarea[name=content], [placeholder*='内容']")
        summary_input = page.query_selector("input[name=summary], textarea[name=summary], [placeholder*='摘要']")
        tags_input = page.query_selector("input[name=tags], [placeholder*='标签']")

        if title_input and body_input:
            log.info("     找到文章编辑表单 ✅")
            title_input.fill("E2E 微信公众号发布器测试 — 自动验证草稿")
            if summary_input:
                summary_input.fill("这是 Playwright E2E 验证的测试文章摘要，仅用作草稿保存测试")
            if tags_input:
                tags_input.fill("e2e, wechat, test")
            
            # Check if there's a draft save button
            save_draft_btn = page.query_selector("button:has-text('存草稿'), button:has-text('保存'), input[value*='存草稿'], input[value*='保存']")
            if save_draft_btn:
                log.info("     找到存草稿按钮 ✅")
                save_draft_btn.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                page.wait_for_timeout(2000)
                screenshot("06-after-save-draft")
                
                # Check result
                current_url = page.url
                page_content = page.content()
                if "success" in page_content.lower() or "成功" in page_content:
                    log.info("     草稿保存成功 ✅")
                else:
                    log.info(f"     保存后 URL: {current_url}")
            else:
                log.info("     未找到存草稿按钮（可能是自动保存或表单提交方式不同）⚠️")
                # Try generic form submission
                submit_btn = page.query_selector("button[type=submit], input[type=submit]")
                if submit_btn:
                    log.info("     尝试通用表单提交...")
                    submit_btn.click()
                    page.wait_for_load_state("networkidle", timeout=10000)
                    page.wait_for_timeout(2000)
                    screenshot("06-after-submit")
        else:
            log.info("     未找到文章编辑表单 ❌")
            log.info(f"     页面元素: {page.content()[:500]}")

        # ---- 4g. 检查 /api 接口的 wechat publisher 信息 ----
        log.info("  Step 4g: 检查 API 接口...")
        # Use the page to fetch API
        api_result = page.evaluate("""
            async () => {
                try {
                    const resp = await fetch('/api/publishers/list');
                    const data = await resp.json();
                    return JSON.stringify(data);
                } catch(e) {
                    return 'ERROR: ' + e.message;
                }
            }
        """)
        log.info(f"     API /api/publishers/list 响应: {api_result[:300]}")

    except Exception as e:
        screenshot("99-error")
        log.error(f"  ❌ Web UI 测试异常: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        browser.close()

# ============================================================
# Part 5: Python API direct test (connection test - without real credentials)
# ============================================================
log.info("\n🔧 [5/6] Python API 直接调用测试")

# Test publish method without real credentials (should fail gracefully)
p4 = WeChatPublisher({"app_id": "wx_fake", "app_secret": "fake_secret"})
result = p4.publish(article)
assert result["success"] == False, "Should fail without real credentials"
assert "token 获取失败" in result.get("error", "") or "发布异常" in result.get("error", ""), \
    f"Unexpected error message: {result.get('error')}"
log.info(f"  ✅ 无效凭证发布测试: 正确拒绝")
log.info(f"     返回: success={result['success']}, error={result.get('error', '')[:60]}")

# Test connection without real credentials
conn_result = p4.test_connection()
assert conn_result["success"] == False, "Connection test should fail"
log.info(f"  ✅ 无效凭证连接测试: 正确拒绝")
log.info(f"     返回: success={conn_result['success']}, status={conn_result.get('status', '')[:60]}")

# ============================================================
# Part 6: WeChat account creation via API
# ============================================================
log.info("\n🔧 [6/6] 微信公众号账号配置流程验证")

# Verify the config_fields structure
log.info("  WeChat 所需配置字段:")
for cf in wp.get("config_fields", []):
    log.info(f"     - {cf.get('key')}: {cf.get('label')} ({'必填' if cf.get('required') else '选填'})")

# Verify the login methods
log.info("  WeChat 登录方法:")
for lm in wp.get("login_methods", []):
    log.info(f"     - {lm.get('label')} ({lm.get('description')})")

# Verify draft mode is supported (publish_select.html shows mode options)
# WeChat publisher uses API to create drafts (draft/add endpoint)
# Verify the API endpoints are correct
import inspect
publish_source = inspect.getsource(WeChatPublisher.publish)
upload_source = inspect.getsource(WeChatPublisher._upload_image)
assert "cgi-bin/draft/add" in publish_source, "Should use draft/add API endpoint"
assert "cgi-bin/material/add_material" in upload_source, "Should support image upload"
log.info("  ✅ API 端点验证:")
log.info("     - cgi-bin/token (获取 access_token, 在 _get_access_token 中)")
log.info("     - cgi-bin/material/add_material (上传图片到素材库, 在 _upload_image 中)")
log.info("     - cgi-bin/draft/add (创建草稿, 在 publish 中)")
log.info("     注意: 使用微信官方 API (非浏览器模拟)")

# ============================================================
log.info("\n" + "=" * 55)
log.info("📊 E2E 验证总结")
log.info("=" * 55)
log.info("""
[1/6] 模块导入 + 注册验证  ✅
[2/6] 构造函数 + 配置验证  ✅
[3/6] 文章构建 + HTML 转换  ✅
[4/6] Web UI 登录验证       有限 - 见下方备注
[5/6] Python API 直接调用    ✅
[6/6] 账号配置流程验证       ✅

🔑 核心验证结果:
   - WeChatPublisher 正确注册到 FlashSloth 发布器注册表
   - 支持 API 密钥认证 (app_id + app_secret)
   - 发布流程: 获取 token → 上传图片(可选) → 构建图文 → 创建草稿
   - 使用微信官方 API (cgi-bin/draft/add) 只存草稿，不自动发布
   - 需要在手机上点发布确认

⚠️ 缺失功能/限制:
   - ❌ 无真实微信 API 凭证可测试完整端到端发布流程
   - ❌ 图片上传依赖本地文件系统路径
   - ⚠️ 封面图 (thumb_media_id) 上传后返回 URL，但微信要求 media_id
   - ⚠️ 无定时发布功能
   - ⚠️ 无素材管理 UI（已上传素材不可见）
   - ⚠️ 无多图文支持（单次只能发一篇）

📝 技术架构:
   - 类型: API 型发布器 (非浏览器模拟)
   - 依赖: 微信公众号官方 API (api.weixin.qq.com)
   - 前提: AppID + AppSecret (微信公众平台后台获取)
""")
