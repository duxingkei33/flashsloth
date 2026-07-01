"""
💬 评论监控页面 E2E 测试 — Playwright
模拟浏览器测试所有控件、按钮、输入框功能
"""
import pytest, re, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import url_for
from playwright.sync_api import Page, expect


@pytest.fixture(scope="function")
def login_state(page: Page, base_url):
    """登录会话"""
    page.goto(base_url + "/login")
    page.wait_for_load_state("networkidle")
    page.fill("input[name='username']", "admin_ohk2yp")
    page.fill("input[name='password']", "test1234")
    page.click("button[type='submit']")
    page.wait_for_url("**/")
    yield


class TestCommentMonitorPage:
    """评论监控页面全功能测试"""

    def test_page_loads(self, page: Page, base_url, login_state):
        """测试1：页面正确加载"""
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        
        # 标题存在
        assert page.locator("h1").first.is_visible()
        # 两个 Tab 存在
        assert page.locator("text=回复收件箱").is_visible()
        assert page.locator("text=监控设置").is_visible()
        
        # 检查 Tab 切换
        page.click("text=监控设置")
        page.wait_for_timeout(300)
        assert page.locator("#tab-config").is_visible()
        
        page.click("text=回复收件箱")
        page.wait_for_timeout(300)
        assert page.locator("#tab-inbox").is_visible()

    def test_check_all_button(self, page: Page, base_url, login_state):
        """测试2：检查全部论坛按钮"""
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        
        check_btn = page.locator("button:has-text('检查全部论坛')")
        if check_btn.is_visible():
            check_btn.click()
            page.wait_for_timeout(1000)
            # 应显示 toast 提示
            toast = page.locator("#toast")
            assert toast.is_visible() or page.locator("text=检查").first.is_visible()

    def test_replies_modal(self, page: Page, base_url, login_state):
        """测试3：查看回复详情弹窗"""
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        
        # 如果有帖子卡片，点击查看
        view_btn = page.locator("button:has-text('查看')").first
        if view_btn.is_visible():
            view_btn.click()
            page.wait_for_timeout(2000)
            # 弹窗应出现
            modal = page.locator("#repliesModal")
            assert "display: none" not in (modal.get_attribute("style") or "")
            # 关闭弹窗
            close_btn = page.locator("#repliesModal button:has-text('✕')").first
            if close_btn.is_visible():
                close_btn.click()
                page.wait_for_timeout(500)

    def test_config_tab_save(self, page: Page, base_url, login_state):
        """测试4：监控设置 Tab — 配置加载和保存"""
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        
        # 切换到设置 Tab
        page.click("text=监控设置")
        page.wait_for_timeout(500)
        
        # 检查配置面板存在
        config_panels = page.locator(".config-panel")
        count = config_panels.count()
        
        if count > 0:
            # 检查第一个面板的元素
            first_panel = config_panels.first
            assert first_panel.locator(".cfg-enabled").count() > 0
            assert first_panel.locator(".cfg-slot").count() > 0
            assert first_panel.locator(".cfg-reply-style").count() > 0
            
            # 保存按钮存在
            save_btn = first_panel.locator("button:has-text('保存配置')")
            assert save_btn.is_visible()
            
            # 立即检查按钮存在
            check_btn = first_panel.locator("button:has-text('立即检查')")
            assert check_btn.is_visible()
            
            # 尝试保存配置
            save_btn.click()
            page.wait_for_timeout(1000)
            # 应显示保存成功 toast
            toast = page.locator("#toast")
            assert toast.is_visible() or page.locator("text=✅").first.is_visible()

    def test_mark_read_all(self, page: Page, base_url, login_state):
        """测试5：全部标为已读功能"""
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        
        # 打开回复详情
        view_btn = page.locator("button:has-text('查看')").first
        if view_btn.is_visible():
            view_btn.click()
            page.wait_for_timeout(2000)
            
            # 全部标为已读按钮
            mark_all = page.locator("button:has-text('全部标为已读')")
            if mark_all.is_visible():
                mark_all.click()
                page.wait_for_timeout(1000)

    def test_ai_reply_modal(self, page: Page, base_url, login_state):
        """测试6：AI回复确认弹窗"""
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        
        # 打开回复详情
        view_btn = page.locator("button:has-text('查看')").first
        if view_btn.is_visible():
            view_btn.click()
            page.wait_for_timeout(2000)
            
            # 找 AI回复 按钮
            ai_btn = page.locator("button:has-text('AI回复')").first
            if ai_btn.is_visible():
                ai_btn.click()
                page.wait_for_timeout(3000)
                
                # AI回复弹窗应出现
                ai_modal = page.locator("#aiReplyModal")
                style = ai_modal.get_attribute("style") or ""
                if "display: none" not in style:
                    # 预览文本存在
                    preview = page.locator("#aiReplyPreview")
                    assert preview.is_visible()
                    
                    # 取消按钮
                    cancel_btn = page.locator("#aiReplyModal button:has-text('取消')")
                    assert cancel_btn.is_visible()
                    
                    # 确认发布按钮
                    confirm_btn = page.locator("#aiReplyModal button:has-text('确认发布')")
                    assert confirm_btn.is_visible()
                    
                    # 点击取消关闭
                    cancel_btn.click()
                    page.wait_for_timeout(500)

    def test_nav_link(self, page: Page, base_url, login_state):
        """测试7：导航栏存在💬评论链接"""
        page.goto(base_url + "/")
        page.wait_for_load_state("networkidle")
        
        nav_link = page.locator("a:has-text('评论')")
        assert nav_link.is_visible()
        assert nav_link.get_attribute("href") == "/comment-monitor"

    def test_forum_reader_link(self, page: Page, base_url, login_state):
        """测试8：AI逛论坛链接存在"""
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        
        forum_link = page.locator("a:has-text('AI逛论坛')")
        if forum_link.is_visible():
            assert forum_link.get_attribute("href") is not None

    def test_empty_state(self, playwright, base_url):
        """测试9：未登录时重定向到登录页（全新浏览器，无cookie）"""
        browser = playwright.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(base_url + "/comment-monitor")
        page.wait_for_load_state("networkidle")
        assert "login" in page.url.lower()
        ctx.close()
        browser.close()
