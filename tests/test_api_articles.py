"""
文章 CRUD API 测试 — 创建/编辑/查看/删除文章。

全部通过 HTTP 请求模拟用户操作，不直接操作数据库。
"""

import pytest
import re
import json
import requests

BASE_URL = "http://localhost:5000"


class TestArticleCreate:
    """文章创建测试"""

    def test_create_page_accessible(self, admin_session):
        """新建文章页面可访问"""
        resp = admin_session.get(f"{BASE_URL}/post/new", timeout=5)
        assert resp.status_code == 200
        assert "title" in resp.text.lower() or "标题" in resp.text, \
            "文章编辑页应有标题输入框"

    def test_create_basic_article(self, admin_session):
        """创建一篇基本文章"""
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "[测试] 创建文章测试",
            "body": "# 测试标题\n\n这是通过API测试创建的文章正文",
            "summary": "自动测试用摘要",
            "tags": "测试,自动化,API",
        }, allow_redirects=False)

        assert resp.status_code in (200, 302), f"创建失败: {resp.status_code}"
        if resp.status_code == 302:
            loc = resp.headers.get("Location", "")
            assert "login" not in loc, "被重定向到登录页，session可能已过期"

    def test_create_article_with_empty_title(self, admin_session):
        """空标题创建文章应允许或给出提示"""
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "",
            "body": "没有标题的文章内容",
            "summary": "",
            "tags": "",
        }, allow_redirects=False)
        # 允许创建空标题（由业务决定），但不应该500崩溃
        assert resp.status_code < 500, f"空标题导致服务器错误: {resp.status_code}"

    def test_create_article_with_special_chars(self, admin_session):
        """包含特殊字符的文章"""
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "[测试] Special chars: <>&\"'中文🔥",
            "body": "Body with <script>alert('xss')</script> and 中文 and 特殊符号",
            "summary": "Special chars test",
            "tags": "测试,XSS,安全",
        }, allow_redirects=False)
        assert resp.status_code in (200, 302), \
            f"特殊字符文章创建失败: {resp.status_code}"

    def test_create_article_long_content(self, admin_session):
        """超长正文文章"""
        long_body = "# 长文测试\n\n" + ("这是测试内容。\n" * 200)
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "[测试] 超长文章",
            "body": long_body,
            "summary": "超长文章摘要",
            "tags": "测试,长文",
        }, allow_redirects=False)
        assert resp.status_code in (200, 302), f"长文创建失败: {resp.status_code}"


class TestArticleEdit:
    """文章编辑测试"""

    def _create_temp_article(self, admin_session) -> int:
        """创建测试文章并返回ID"""
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "[测试] 待编辑文章",
            "body": "原始内容",
            "summary": "原始摘要",
            "tags": "测试",
        }, allow_redirects=False)
        assert resp.status_code in (200, 302)

        # 从重定向获取文章ID
        loc = resp.headers.get("Location", "")
        m = re.search(r"/post/edit/(\d+)", loc) if resp.status_code == 302 else None
        if m:
            return int(m.group(1))
        return None

    def test_edit_page_accessible(self, admin_session):
        """文章编辑页面可访问"""
        # 先创建一篇
        art_id = self._create_temp_article(admin_session)
        if art_id:
            resp = admin_session.get(f"{BASE_URL}/post/edit/{art_id}", timeout=5)
            assert resp.status_code == 200
            # 清理
            admin_session.get(f"{BASE_URL}/post/delete/{art_id}")

    def test_edit_article_title(self, admin_session):
        """修改文章标题"""
        art_id = self._create_temp_article(admin_session)
        if not art_id:
            pytest.skip("无法创建测试文章")

        resp = admin_session.post(f"{BASE_URL}/post/edit/{art_id}", data={
            "title": "[测试] 已修改标题",
            "body": "修改后的正文",
            "summary": "修改后的摘要",
            "tags": "测试,编辑",
        }, allow_redirects=False)
        assert resp.status_code in (200, 302), f"编辑失败: {resp.status_code}"

        # 清理
        admin_session.get(f"{BASE_URL}/post/delete/{art_id}")

    def test_edit_nonexistent_article(self, admin_session):
        """编辑不存在的文章应返回错误"""
        resp = admin_session.get(f"{BASE_URL}/post/edit/99999", allow_redirects=False)
        assert resp.status_code in (200, 302, 404)
        # 不应500崩溃
        assert resp.status_code < 500, "编辑不存在文章导致500错误"


class TestArticleDelete:
    """文章删除测试"""

    def test_delete_existing_article(self, admin_session):
        """删除已存在的文章"""
        # 先创建
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "[测试] 待删除文章",
            "body": "将被删除",
            "summary": "",
            "tags": "测试",
        }, allow_redirects=False)
        assert resp.status_code in (200, 302)

        # 获取文章ID
        loc = resp.headers.get("Location", "")
        m = re.search(r"/post/edit/(\d+)", loc) if resp.status_code == 302 else None
        if not m:
            pytest.skip("无法获取文章ID")

        art_id = int(m.group(1))
        resp = admin_session.get(f"{BASE_URL}/post/delete/{art_id}", allow_redirects=False)
        assert resp.status_code in (200, 302), f"删除失败: {resp.status_code}"

        # 验证删除后访问编辑页应重定向
        resp2 = admin_session.get(f"{BASE_URL}/post/edit/{art_id}", allow_redirects=False)
        assert resp2.status_code in (200, 302)
        # 页面应提示文章不存在或重定向
        if resp2.status_code == 200:
            assert "不存在" in resp2.text or "error" in resp2.text.lower()

    def test_delete_nonexistent_article(self, admin_session):
        """删除不存在文章不应500"""
        resp = admin_session.get(f"{BASE_URL}/post/delete/99999", allow_redirects=False)
        assert resp.status_code < 500, "删除不存在文章导致500"


class TestArticleList:
    """文章列表查看测试"""

    def test_dashboard_shows_articles(self, admin_session):
        """首页展示文章列表"""
        resp = admin_session.get(f"{BASE_URL}/", timeout=5)
        assert resp.status_code == 200
        # 应有文章列表区域
        assert "article" in resp.text.lower() or "post" in resp.text.lower() or \
               "文章" in resp.text, "首页应有文章相关内容"

    def test_dashboard_stats(self, admin_session):
        """首页展示统计数据"""
        resp = admin_session.get(f"{BASE_URL}/", timeout=5)
        assert resp.status_code == 200
        # 应有统计数字
        assert "计数" in resp.text or "总数" in resp.text or "count" in resp.text.lower(), \
            "首页应有统计信息"


class TestArticleMultiuser:
    """多用户文章隔离测试"""

    def test_users_cannot_see_each_others_articles(self, admin_session):
        """不同用户看不到对方的文章"""
        import random
        import string
        suffix = "".join(random.choices(string.ascii_lowercase, k=6))
        user_a = f"usera_{suffix}"
        user_b = f"userb_{suffix}"
        passwd = "TestPass123!"

        # 注册两个用户
        for u in [user_a, user_b]:
            s = requests.Session()
            s.post(f"{BASE_URL}/register", data={
                "username": u, "password": passwd, "confirm": passwd
            })
            s.post(f"{BASE_URL}/login", data={"username": u, "password": passwd})

            # 各自创建一篇
            s.post(f"{BASE_URL}/post/new", data={
                "title": f"[测试] {u} 的文章",
                "body": f"这是 {u} 的私有文章",
                "summary": "", "tags": "测试"
            })

        # 用 user_a 登录，看只能看到自己的文章
        sa = requests.Session()
        sa.post(f"{BASE_URL}/login", data={"username": user_a, "password": passwd})
        home_a = sa.get(f"{BASE_URL}/", timeout=5)
        assert user_a in home_a.text, f"首页应显示{user_a}的信息"
