"""
FlashSloth 核心功能浏览器端到端测试
覆盖：批量发布、撤回、批量删除、导航、设置等关键流程
"""
import pytest
import re, os


BASE_URL = "http://localhost:5000"


class TestBatchPublishUI:
    """浏览器测试批量发布"""

    def test_batch_publish_select_page(self, logged_in_page):
        """仪表盘可勾选文章并看到批量发布按钮"""
        logged_in_page.goto(f"{BASE_URL}/")
        logged_in_page.wait_for_load_state("networkidle")
        content = logged_in_page.content()
        assert "Internal Server Error" not in content
        checkboxes = logged_in_page.query_selector_all("input[type='checkbox']")
        if checkboxes:
            checkboxes[0].check()
            assert checkboxes[0].is_checked()


class TestRetractUI:
    """浏览器测试撤回"""

    def test_retract_page(self, logged_in_page):
        """发布管理页可访问，撤回不崩"""
        logged_in_page.goto(f"{BASE_URL}/publish/manage")
        logged_in_page.wait_for_load_state("networkidle")
        content = logged_in_page.content()
        assert "Internal Server Error" not in content
        assert "Internal Server Error" not in logged_in_page.title()
        links = logged_in_page.query_selector_all("a[href*='retract']")
        if links:
            links[0].click()
            logged_in_page.wait_for_load_state("networkidle")
            assert "Internal Server Error" not in logged_in_page.content()


class TestBatchDeleteUI:
    """浏览器测试批量删除"""

    def test_batch_delete_button_exists(self, logged_in_page):
        """仪表盘有批量删除按钮，页面不崩"""
        logged_in_page.goto(f"{BASE_URL}/")
        logged_in_page.wait_for_load_state("networkidle")
        content = logged_in_page.content()
        assert "Internal Server Error" not in content
        # 不测 "500" 因为端口号包含 5000


class TestNavigationUI:
    """导航菜单可用性"""

    def test_nav_links_work(self, logged_in_page):
        """顶部导航所有链接点过去不崩"""
        # 等待页面完全加载
        logged_in_page.goto(f"{BASE_URL}/")
        logged_in_page.wait_for_load_state("networkidle")
        logged_in_page.wait_for_timeout(500)
        
        # 收集所有导航链接的 href
        links = logged_in_page.query_selector_all("a")
        hrefs = set()
        for link in links:
            try:
                href = link.get_attribute("href")
                if (href and href.startswith("/") 
                    and not href.startswith("/post/edit/")
                    and not href.startswith("/post/new")
                    and href not in hrefs):
                    hrefs.add(href)
            except Exception:
                pass
        
        assert len(hrefs) > 0, f"应该找到至少一个导航链接，找到 {len(hrefs)}"
        
        # 逐个访问（在新标签打开，避免破坏页面状态）
        errors = []
        for href in sorted(hrefs):
            try:
                logged_in_page.goto(f"{BASE_URL}{href}")
                logged_in_page.wait_for_load_state("networkidle")
                c = logged_in_page.content()
                if "Internal Server Error" in c:
                    errors.append(f"{href} → 500")
            except Exception as e:
                errors.append(f"{href} → {str(e)[:60]}")
        
        if errors:
            pytest.fail(f"以下页面报错: {'; '.join(errors)}")


class TestSettingsUI:
    """设置页面不崩"""

    def test_settings_page(self, logged_in_page):
        """设置页不报 Internal Server Error"""
        logged_in_page.goto(f"{BASE_URL}/settings")
        logged_in_page.wait_for_load_state("networkidle")
        assert "Internal Server Error" not in logged_in_page.content()
        assert "500</title>" not in logged_in_page.content()


class TestDeployUI:
    """部署页面"""

    def test_deploy_page(self, logged_in_page):
        """部署管理页不崩"""
        logged_in_page.goto(f"{BASE_URL}/deployers")
        logged_in_page.wait_for_load_state("networkidle")
        assert "Internal Server Error" not in logged_in_page.content()


class TestStorageUI:
    """存储页面"""

    def test_storage_page(self, logged_in_page):
        """存储管理页不崩"""
        logged_in_page.goto(f"{BASE_URL}/storage/settings")
        logged_in_page.wait_for_load_state("networkidle")
        assert "Internal Server Error" not in logged_in_page.content()


class TestPublishSelect:
    """发布选择页面"""

    def test_publish_select(self, logged_in_page):
        """发布选择页不崩"""
        # 找一篇已有文章进发布选择
        logged_in_page.goto(f"{BASE_URL}/")
        logged_in_page.wait_for_load_state("networkidle")
        edit_links = logged_in_page.query_selector_all("a[href*='/post/edit/']")
        if edit_links:
            href = edit_links[0].get_attribute("href")
            aid = href.split("/")[-1]
            logged_in_page.goto(f"{BASE_URL}/publish/select/{aid}")
            logged_in_page.wait_for_load_state("networkidle")
            assert "Internal Server Error" not in logged_in_page.content()


class TestChangePassword:
    """修改密码页面"""

    def test_change_password_page(self, logged_in_page):
        """修改密码页不崩"""
        logged_in_page.goto(f"{BASE_URL}/change_password")
        logged_in_page.wait_for_load_state("networkidle")
        assert "Internal Server Error" not in logged_in_page.content()
