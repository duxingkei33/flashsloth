"""
账号管理 API 测试 — 测试账号的添加/编辑/删除/查看流程。

所有操作通过 HTTP API 模拟用户操作。
"""

import pytest
import re
import json

BASE_URL = "http://localhost:5000"


class TestAccountsPage:
    """账号列表页面测试"""

    def test_accounts_page_accessible(self, admin_session):
        """账号管理页面可访问"""
        resp = admin_session.get(f"{BASE_URL}/accounts", timeout=5)
        assert resp.status_code == 200
        assert "账号" in resp.text or "account" in resp.text.lower(), \
            "账号页面应有账号相关内容"

    def test_accounts_list_has_content(self, admin_session):
        """账号列表有内容（从备份恢复的账号）"""
        resp = admin_session.get(f"{BASE_URL}/accounts", timeout=5)
        assert resp.status_code == 200
        # 检查是否列出了账号
        assert "discuz" in resp.text.lower() or "CSDN" in resp.text or "GitHub" in resp.text, \
            "账号列表应显示已配置的账号"


class TestAccountAdd:
    """账号添加测试"""

    @pytest.fixture
    def sample_account_data(self):
        return {
            "platform": "discuz",
            "account_name": f"test_discuz_{int(__import__('time').time())}",
            "site_url": "https://www.example.com",
            "username": "testuser",
            "password": "testpass",
            "cookie": "",
        }

    def test_add_account_form(self, admin_session):
        """添加账号页面有表单"""
        resp = admin_session.get(f"{BASE_URL}/accounts")
        assert resp.status_code == 200
        # 检查是否有添加表单
        assert "form" in resp.text.lower() or "添加" in resp.text or "add" in resp.text.lower()

    def test_add_discuz_account(self, admin_session, sample_account_data):
        """添加 Discuz 账号（不实际测试连接，仅验证请求不崩溃）"""
        resp = admin_session.post(f"{BASE_URL}/accounts/add", data={
            "platform": sample_account_data["platform"],
            "account_name": sample_account_data["account_name"],
            "site_url": sample_account_data["site_url"],
            "username": sample_account_data["username"],
            "password": sample_account_data["password"],
        }, allow_redirects=False)
        assert resp.status_code in (200, 302), f"添加账号异常: {resp.status_code}"
        assert resp.status_code < 500, f"添加账号导致服务器错误: {resp.status_code}"

    def test_add_account_empty_fields(self, admin_session):
        """空字段添加账号"""
        resp = admin_session.post(f"{BASE_URL}/accounts/add", data={
            "platform": "",
            "account_name": "",
            "site_url": "",
            "username": "",
            "password": "",
        }, allow_redirects=False)
        assert resp.status_code in (200, 302), f"空字段添加返回异常: {resp.status_code}"
        assert resp.status_code < 500, "空字段导致500错误"


class TestAccountEdit:
    """账号编辑测试"""

    def test_edit_existing_account(self, admin_session):
        """编辑已有账号"""
        # 查看账号列表，获取第一个账号ID
        resp = admin_session.get(f"{BASE_URL}/accounts")
        # 从HTML中提取账号ID
        m = re.search(r'/accounts/edit/(\d+)', resp.text)
        if not m:
            pytest.skip("没有可编辑的账号")

        aid = int(m.group(1))
        edit_resp = admin_session.get(f"{BASE_URL}/accounts/edit/{aid}", timeout=5)
        assert edit_resp.status_code == 200, f"编辑页返回{edit_resp.status_code}"

        # 提交编辑
        update_resp = admin_session.post(f"{BASE_URL}/accounts/edit/{aid}", data={
            "account_name": f"已编辑_{int(__import__('time').time())}",
            "site_url": "https://www.example.com",
            "username": "edited_user",
            "password": "",
        }, allow_redirects=False)
        assert update_resp.status_code in (200, 302), f"编辑提交异常: {update_resp.status_code}"
        assert update_resp.status_code < 500

    def test_edit_nonexistent_account(self, admin_session):
        """编辑不存在的账号"""
        resp = admin_session.get(f"{BASE_URL}/accounts/edit/99999", allow_redirects=False)
        assert resp.status_code < 500, "编辑不存在账号导致500"


class TestAccountDelete:
    """账号删除测试"""

    def test_delete_existing_account(self, admin_session):
        """删除已有账号"""
        # 先添加一个测试账号
        ts = int(__import__('time').time())
        add_resp = admin_session.post(f"{BASE_URL}/accounts/add", data={
            "platform": "discuz",
            "account_name": f"delete_test_{ts}",
            "site_url": "https://example.com",
            "username": "test",
            "password": "test",
        }, allow_redirects=False)

        # 获取账号ID
        resp = admin_session.get(f"{BASE_URL}/accounts")
        m = re.search(rf'delete_test_{ts}.*?/accounts/delete/(\d+)', resp.text, re.DOTALL)
        if not m:
            # 尝试其他方式找ID
            m = re.search(r'/accounts/delete/(\d+)', resp.text)
        if not m:
            pytest.skip("无法获取新添加账号的ID")

        aid = int(m.group(1))
        del_resp = admin_session.get(f"{BASE_URL}/accounts/delete/{aid}", allow_redirects=False)
        assert del_resp.status_code in (200, 302), f"删除异常: {del_resp.status_code}"
        assert del_resp.status_code < 500

    def test_delete_nonexistent_account(self, admin_session):
        """删除不存在账号"""
        resp = admin_session.get(f"{BASE_URL}/accounts/delete/99999", allow_redirects=False)
        assert resp.status_code < 500, "删除不存在账号导致500"


class TestAccountTest:
    """账号连接测试"""

    def test_test_connection_existing(self, admin_session):
        """测试已有账号连接（可能失败，但不应该500）"""
        # 获取第一个账号ID
        resp = admin_session.get(f"{BASE_URL}/accounts")
        m = re.search(r'/accounts/edit/(\d+)', resp.text)
        if not m:
            pytest.skip("没有可测试的账号")

        aid = int(m.group(1))
        test_resp = admin_session.post(
            f"{BASE_URL}/api/accounts/test/{aid}", timeout=10
        )
        assert test_resp.status_code < 500, f"测试连接导致500: {test_resp.status_code}"

    def test_test_connection_nonexistent(self, admin_session):
        """测试不存在的账号"""
        test_resp = admin_session.post(
            f"{BASE_URL}/api/accounts/test/99999", timeout=5
        )
        assert test_resp.status_code < 500
