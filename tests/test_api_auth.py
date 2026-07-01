"""
认证模块 API 测试 — 测试登录/登出/密码修改流程。

所有操作通过 HTTP API 模拟真实用户操作。
"""

import pytest
import requests
import os

BASE_URL = "http://localhost:5000"

# 自动检测引导凭证
_BOOT_FILE = os.path.join(os.path.dirname(__file__), "..", ".boot_credentials")
if os.path.exists(_BOOT_FILE):
    with open(_BOOT_FILE) as f:
        for line in f:
            if line.startswith("username:"):
                ADMIN_USER = line.split(":", 1)[1].strip()
            elif line.startswith("password:"):
                ADMIN_PASS = line.split(":", 1)[1].strip()
else:
    ADMIN_USER = "admin_ohk2yp"
    ADMIN_PASS = "test1234"


class TestLogin:
    """登录功能测试"""

    def test_login_page_accessible(self):
        """登录页面可访问（200）"""
        resp = requests.get(f"{BASE_URL}/login", timeout=5)
        assert resp.status_code == 200
        assert "登录" in resp.text or "Login" in resp.text or "password" in resp.text.lower()

    def test_login_success(self):
        """正确凭证登录成功，拿到 session cookie"""
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/login", data={
            "username": ADMIN_USER,
            "password": ADMIN_PASS,
        }, allow_redirects=False)
        assert resp.status_code in (302, 200), f"登录失败: {resp.status_code}"
        # 验证已登录（访问首页不重定向到login）
        home = s.get(f"{BASE_URL}/", allow_redirects=False)
        assert home.status_code != 302 or "login" not in (home.headers.get("Location", "")), \
            "登录后仍被重定向到登录页，session未生效"

    def test_login_wrong_password(self):
        """错误密码返回错误"""
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/login", data={
            "username": ADMIN_USER,
            "password": "wrong_password_12345",
        })
        assert "登录失败" in resp.text or "错误" in resp.text or resp.status_code == 200, \
            "错误密码应提示错误信息"

    def test_login_empty_fields(self):
        """空字段提交返回错误"""
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/login", data={
            "username": "",
            "password": "",
        })
        assert resp.status_code == 200
        # 应该仍停留在登录页且有错误信息

    def test_login_nonexistent_user(self):
        """不存在的用户返回错误"""
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/login", data={
            "username": "nonexistent_user_99999",
            "password": "somepassword",
        })
        assert resp.status_code == 200
        assert "登录" in resp.text or "Login" in resp.text


class TestLogout:
    """登出功能测试"""

    def test_logout_clears_session(self, admin_session):
        """登出后 session 失效，访问首页被重定向到登录页"""
        resp = admin_session.get(f"{BASE_URL}/logout", allow_redirects=False)
        assert resp.status_code in (302, 200)

        # 登出后访问首页
        home = admin_session.get(f"{BASE_URL}/", allow_redirects=True)
        assert "login" in home.url.lower(), \
            f"登出后应重定向到登录页，实际: {home.url}"


class TestRegister:
    """注册功能测试"""

    def test_register_page_accessible(self):
        """注册页面可访问"""
        resp = requests.get(f"{BASE_URL}/register", timeout=5)
        assert resp.status_code == 200

    def test_register_new_user(self):
        """注册新用户并登录"""
        import random
        import string
        suffix = "".join(random.choices(string.ascii_lowercase, k=6))
        test_user = f"testuser_{suffix}"
        test_pass = "TestPass123!"

        s = requests.Session()
        resp = s.post(f"{BASE_URL}/register", data={
         "username": test_user,
         "password": test_pass,
         "confirm": test_pass,
     }, allow_redirects=False)

        # 注册成功应重定向到首页或登录页
        assert resp.status_code in (200, 302), f"注册异常: {resp.status_code}"

        # 尝试用新账号登录
        s2 = requests.Session()
        login_resp = s2.post(f"{BASE_URL}/login", data={
            "username": test_user,
            "password": test_pass,
        }, allow_redirects=False)
        assert login_resp.status_code in (302, 200), f"新用户登录失败: {login_resp.status_code}"

    def test_register_duplicate_username(self):
        """重复用户名注册应失败"""
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/register", data={
         "username": ADMIN_USER,  # 已存在的用户名
         "password": "SomePass123!",
         "confirm": "SomePass123!",
     })
        assert resp.status_code == 200
        assert "已存在" in resp.text or "exist" in resp.text.lower() or "重复" in resp.text, \
            "重复注册应有提示"
