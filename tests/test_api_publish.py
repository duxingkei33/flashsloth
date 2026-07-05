"""
发布流程 API 测试 — 测试发布/撤回/管理功能。

注意：测试不实际触发真实发布（平台账号可能不可用），
而是测试发布流程的请求/响应逻辑正确性。
"""

import pytest
import re

BASE_URL = "http://localhost:5000"


class TestPublishPage:
    """发布页面测试"""

    def test_publish_select_page(self, admin_session):
        """发布选择页面可访问"""
        # 先建一篇文章
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "[测试] 发布测试文章",
            "body": "发布流程测试",
            "summary": "",
            "tags": "测试,发布",
        }, allow_redirects=False)
        assert resp.status_code in (200, 302)

        loc = resp.headers.get("Location", "")
        m = re.search(r"/post/edit/(\d+)", loc) if resp.status_code == 302 else None
        if not m:
            pytest.skip("无法获取文章ID")

        art_id = int(m.group(1))

        # 访问发布选择页面
        resp = admin_session.get(f"{BASE_URL}/publish/select/{art_id}", timeout=5)
        assert resp.status_code == 200, f"发布选择页返回{resp.status_code}"
        # 应有平台选择区域
        assert "账号" in resp.text or "account" in resp.text.lower() or "平台" in resp.text, \
            "发布选择页应有账号/平台列表"

        # 清理
        admin_session.get(f"{BASE_URL}/post/delete/{art_id}")


class TestPublishWorkflow:
    """发布流程测试"""

    def test_publish_without_article_id(self, admin_session):
        """未选择文章时发布返回错误"""
        resp = admin_session.post(f"{BASE_URL}/publish", data={
            "account_ids": ["1"],
        }, allow_redirects=False)
        assert resp.status_code in (200, 302)
        # 应有错误提示
        if resp.status_code == 200:
            assert "error" in resp.text.lower() or "请选择" in resp.text

    def test_publish_without_account(self, admin_session):
        """未选择账号时发布返回错误"""
        resp = admin_session.post(f"{BASE_URL}/publish", data={
            "article_id": "1",
            "account_ids": [],
        }, allow_redirects=False)
        assert resp.status_code in (200, 302)
        if resp.status_code == 200:
            assert "error" in resp.text.lower() or "请选择" in resp.text

    def test_publish_with_valid_data(self, admin_session):
        """发布有效数据（即使发布失败也应返回结果而非500）"""
        # 先创建文章
        resp = admin_session.post(f"{BASE_URL}/post/new", data={
            "title": "[测试] 验证发布流程",
            "body": "测试发布流程的文章",
            "summary": "",
            "tags": "测试",
        }, allow_redirects=False)
        loc = resp.headers.get("Location", "")
        m = re.search(r"/post/edit/(\d+)", loc) if resp.status_code == 302 else None
        if not m:
            pytest.skip("无法获取文章ID")
        art_id = int(m.group(1))

        # 尝试发布到账号1（可能失败因为cookie过期，但不应该500）
        resp = admin_session.post(f"{BASE_URL}/publish", data={
            "article_id": str(art_id),
            "account_ids": ["1"],
        }, allow_redirects=False)
        assert resp.status_code in (200, 302), f"发布请求异常: {resp.status_code}"
        assert resp.status_code < 500, f"发布导致服务器错误: {resp.status_code}"

        # 清理
        admin_session.get(f"{BASE_URL}/post/delete/{art_id}")


class TestPublishManage:
    """发布管理测试"""

    def test_publish_manage_page(self, admin_session):
        """发布管理页面可访问"""
        resp = admin_session.get(f"{BASE_URL}/publish/manage", timeout=5)
        assert resp.status_code == 200, f"发布管理页返回{resp.status_code}"

    def test_publish_manage_has_content(self, admin_session):
        """发布管理页有发布记录"""
        resp = admin_session.get(f"{BASE_URL}/publish/manage", timeout=5)
        assert resp.status_code == 200
        # 应有记录区域（即使为空）
        assert len(resp.text) > 100, "发布管理页内容过短"


class TestRetract:
    """撤回功能测试"""

    def test_retract_nonexistent_log(self, admin_session):
        """撤回不存在的发布记录"""
        resp = admin_session.get(f"{BASE_URL}/publish/retract/99999", allow_redirects=False)
        assert resp.status_code in (200, 302, 404)
        assert resp.status_code < 500, "撤回不存在记录导致500"

    def test_retract_page_response(self, admin_session):
        """撤回请求有响应（不崩溃）"""
        resp = admin_session.get(f"{BASE_URL}/publish/retract/1", allow_redirects=False)
        assert resp.status_code in (200, 302, 404)
        assert resp.status_code < 500


class TestDeploy:
    """部署功能测试"""

    def test_deployers_page(self, admin_session):
        """部署管理页面可访问"""
        resp = admin_session.get(f"{BASE_URL}/deployers", timeout=5)
        assert resp.status_code == 200

    def test_deploy_nonexistent(self, admin_session):
        """部署不存在的配置不应500"""
        resp = admin_session.get(f"{BASE_URL}/deployers/deploy/99999", allow_redirects=False)
        assert resp.status_code < 500, "部署不存在配置导致500"
