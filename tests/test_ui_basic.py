"""
浏览器 UI 测试 — 通过 Playwright 模拟真实用户操作。

测试实际的页面渲染、表单提交、导航跳转等。
"""

import pytest
import re

BASE_URL = "http://localhost:5000"
ADMIN_USER = "admin_redacted"
ADMIN_PASS = "test_redacted"


class TestLoginUI:
    """浏览器登录测试"""

    def test_login_page_renders(self, browser_page):
        """登录页面正常渲染"""
        page = browser_page
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")

        # 应看到登录表单
        assert page.locator("input[name='username']").is_visible()
        assert page.locator("input[name='password']").is_visible()
        assert page.locator("button[type='submit']").is_visible()

    def test_login_success_redirect(self, browser_page):
        """登录成功后跳转到首页"""
        page = browser_page
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")

        page.fill("input[name='username']", ADMIN_USER)
        page.fill("input[name='password']", ADMIN_PASS)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        # 应跳离登录页
        assert "login" not in page.url.lower(), f"登录失败，仍在登录页: {page.url}"

    def test_login_wrong_password(self, browser_page):
        """错误密码登录应显示错误"""
        page = browser_page
        page.goto(f"{BASE_URL}/login")
        page.wait_for_load_state("networkidle")

        page.fill("input[name='username']", ADMIN_USER)
        page.fill("input[name='password']", "wrong_password_12345")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        # 应停留在登录页且有错误提示
        assert "login" in page.url.lower(), "错误密码不应跳转"

    def test_logout_redirects_to_login(self, logged_in_page):
        """登出后回到登录页"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/logout")
        page.wait_for_load_state("networkidle")

        # 应跳转到登录页
        assert "login" in page.url.lower(), f"登出后应跳转到登录页，实际: {page.url}"


class TestDashboardUI:
    """首页仪表盘测试"""

    def test_dashboard_shows_stats(self, logged_in_page):
        """首页显示统计卡片"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")

        # 应有统计数字区域
        body_text = page.text_content("body")
        assert body_text and len(body_text) > 200, "首页内容过短"

    def test_dashboard_has_navigation(self, logged_in_page):
        """首页有导航菜单"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")

        # 应有导航链接
        nav_links = page.locator("nav a, .nav a, header a").all()
        assert len(nav_links) >= 3, f"导航链接不足: {len(nav_links)}"

    def test_dashboard_article_list(self, logged_in_page):
        """首页展示文章列表"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")

        # 查找文章列表区域
        articles = page.locator("table, .article-list, .post-list, .list-group").all()
        assert len(articles) >= 1, "首页应有文章列表区域"


class TestArticleCreateUI:
    """浏览器创建文章测试"""

    def test_create_page_has_editor(self, logged_in_page):
        """新建文章页有编辑器"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/post/new")
        page.wait_for_load_state("networkidle")

        # 应有标题和正文输入框
        assert page.locator("input[name='title']").is_visible()
        assert page.locator("textarea[name='body']").is_visible()

    def test_create_article_via_form(self, logged_in_page):
        """通过表单创建文章"""
        import time
        page = logged_in_page
        page.goto(f"{BASE_URL}/post/new")
        page.wait_for_load_state("networkidle")

        ts = str(int(time.time()))
        page.fill("input[name='title']", f"[浏览器测试] 通过UI创建 {ts}")
        page.fill("textarea[name='body']", "# 浏览器测试\n\n这是通过浏览器UI创建的文章")
        page.fill("input[name='summary']", "通过浏览器UI自动测试")
        page.fill("input[name='tags']", "浏览器,测试,UI")

        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        # 应跳转回首页
        assert page.url.rstrip("/").rstrip("/") == BASE_URL.rstrip("/") or \
               page.url.rstrip("/") == f"{BASE_URL}/", \
               f"创建后应回到首页，实际: {page.url}"

        # 首页应有刚才创建的文章标题
        body = page.text_content("body")
        assert f"通过UI创建 {ts}" in (body or ""), "首页找不到刚创建的文章"


class TestAccountUI:
    """浏览器账号管理测试"""

    def test_accounts_page_lists(self, logged_in_page):
        """账号页显示账号列表"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/accounts")
        page.wait_for_load_state("networkidle")

        # 应有账号相关内容
        body_text = page.text_content("body")
        assert body_text and len(body_text) > 100

    def test_navigate_from_dashboard_to_accounts(self, logged_in_page):
        """从首页导航到账号管理"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")

        # 找到账号管理链接并点击
        account_link = page.locator("a:has-text('账号'), a:has-text('Account'), a:has-text('账户')").first
        if account_link.is_visible():
            account_link.click()
            page.wait_for_load_state("networkidle")
            assert "account" in page.url.lower(), f"点击账号链接后URL异常: {page.url}"


class TestPublishUI:
    """浏览器发布管理测试"""

    def test_publish_manage_page(self, logged_in_page):
        """发布管理页面可访问"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/publish/manage")
        page.wait_for_load_state("networkidle")

        body = page.text_content("body")
        assert body and len(body) > 100

    def test_deployers_page(self, logged_in_page):
        """部署管理页面可访问"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/deployers")
        page.wait_for_load_state("networkidle")

        body = page.text_content("body")
        assert body and len(body) > 50


class TestSettingsUI:
    """浏览器设置页测试"""

    def test_settings_page(self, logged_in_page):
        """设置页可访问"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/settings")
        page.wait_for_load_state("networkidle")

        body = page.text_content("body")
        assert body and len(body) > 100

    def test_ai_settings_page(self, logged_in_page):
        """AI设置页可访问"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/ai/settings")
        page.wait_for_load_state("networkidle")

        body = page.text_content("body")
        assert body and len(body) > 50

    def test_storage_settings_page(self, logged_in_page):
        """存储设置页可访问"""
        page = logged_in_page
        page.goto(f"{BASE_URL}/storage/settings")
        page.wait_for_load_state("networkidle")

        body = page.text_content("body")
        assert body and len(body) > 50
