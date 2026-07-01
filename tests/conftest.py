"""
pytest 共享 fixtures — 所有测试通过 HTTP API 而非直接操作数据库。

关键原则：
  - 测试登录/创建文章等操作必须通过 Flask 路由（HTTP）
  - 数据库 fixture 仅用于 setup/teardown（清理测试数据），不用于断言
  - 所有断言基于 HTTP 响应码和响应体 JSON
"""

import pytest
import requests
import sqlite3
import os
import json

BASE_URL = "http://localhost:5000"

# 自动检测引导凭证（首次启动时 admin.py 生成的随机密码）
_BOOT_FILE = os.path.join(os.path.dirname(__file__), "..", ".boot_credentials")
if os.path.exists(_BOOT_FILE):
    with open(_BOOT_FILE) as f:
        for line in f:
            if line.startswith("username:"):
                ADMIN_USER = line.split(":", 1)[1].strip()
            elif line.startswith("password:"):
                ADMIN_PASS = line.split(":", 1)[1].strip()
else:
    ADMIN_USER = "admin_redacted"
    ADMIN_PASS = "test_redacted"

# ── 数据库路径（仅用于 setup/teardown） ────────────────────
# 优先使用 FLASHSLOTH_DB_PATH 环境变量（与 admin.py 一致），
# 否则默认项目根目录的 flashsloth.db（dev 模式）
_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "flashsloth.db")
DB_PATH = os.environ.get("FLASHSLOTH_DB_PATH") or _DEFAULT_DB


# ═══════════════════════════════════════════════════════════
# Session 级 fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def base_url() -> str:
    """应用基地址"""
    return BASE_URL


@pytest.fixture(scope="session")
def admin_session():
    """已登录 admin 的 requests.Session — 通过真实登录 API 获取"""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/login", data={
        "username": ADMIN_USER,
        "password": ADMIN_PASS,
    }, allow_redirects=False)

    # 登录成功应返回 302 重定向到首页
    assert resp.status_code in (302, 200), \
        f"登录失败 (status={resp.status_code}): {resp.text[:200]}"

    # 验证确实已登录：访问首页应返回 200 不是 302→login
    home = s.get(f"{BASE_URL}/", allow_redirects=False)
    assert home.status_code in (200, 302), \
        f"登录后首页返回 {home.status_code}，登录可能未生效"

    return s


@pytest.fixture(scope="session")
def csrf_session(admin_session):
    """带有 CSRF token 的 session（如果应用使用 CSRF）"""
    # 获取首页/设置页提取 csrf token
    resp = admin_session.get(f"{BASE_URL}/settings")
    import re
    token = re.search(
        r'name="csrf_token"[^>]*value="([^"]+)"',
        resp.text
    )
    if token:
        admin_session.headers["X-CSRF-Token"] = token.group(1)
    return admin_session


# ═══════════════════════════════════════════════════════════
# 函数级 fixtures — 每个测试独立清理
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def clean_test_articles(admin_session):
    """测试前记录已有文章ID，测试后清理本次测试创建的文章

    注意：只清理通过 API 可识别的测试标记文章
    """
    # setup: 获取当前文章列表
    resp = admin_session.get(f"{BASE_URL}/api/articles")
    existing_ids = set()
    if resp.status_code == 200:
        try:
            data = resp.json()
            for art in data.get("articles", []):
                existing_ids.add(art["id"])
        except Exception:
            pass

    yield  # 测试执行

    # teardown: 删除本次测试创建的文章（通过 API）
    resp = admin_session.get(f"{BASE_URL}/api/articles")
    if resp.status_code != 200:
        return
    try:
        data = resp.json()
        for art in data.get("articles", []):
            if art["id"] not in existing_ids:
                admin_session.post(
                    f"{BASE_URL}/article/delete/{art['id']}"
                )
    except Exception:
        pass


@pytest.fixture
def test_article(admin_session):
    """通过 API 创建一篇测试文章，返回文章 ID

    yield id, 测试结束后自动删除
    """
    resp = admin_session.post(f"{BASE_URL}/article/create", data={
        "title": "[测试] 自动化测试文章",
        "body": "# 测试内容\n\n这是通过API创建的测试文章",
        "summary": "自动化测试用",
        "tags": '["测试", "自动化"]',
        "source": "automated_test",
    }, allow_redirects=False)

    assert resp.status_code in (200, 302), \
        f"创建文章失败: {resp.status_code} {resp.text[:200]}"

    # 获取刚创建的文章 ID
    art_id = None
    if resp.status_code == 302:
        # 重定向到编辑页，从 Location 提取 ID
        loc = resp.headers.get("Location", "")
        import re
        m = re.search(r"/article/edit/(\d+)", loc)
        if m:
            art_id = int(m.group(1))
    else:
        try:
            data = resp.json()
            art_id = data.get("id")
        except Exception:
            pass

    if art_id is None:
        # fallback: 查最新文章
        r2 = admin_session.get(f"{BASE_URL}/api/articles")
        if r2.status_code == 200:
            try:
                articles = r2.json().get("articles", [])
                if articles:
                    art_id = articles[-1]["id"]
            except Exception:
                pass

    assert art_id is not None, "无法确定创建的文章ID"

    yield art_id

    # teardown: 删除测试文章
    admin_session.post(f"{BASE_URL}/article/delete/{art_id}")


# ═══════════════════════════════════════════════════════════
# Playwright 相关 fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def playwright_browser():
    """启动 Playwright Chromium 浏览器实例"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def browser_page(playwright_browser):
    """每个测试函数一个独立的浏览器标签页"""
    context = playwright_browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture(scope="function")
def logged_in_page(browser_page):
    """已登录 admin 的浏览器页面"""
    page = browser_page
    page.goto(f"{BASE_URL}/login")
    page.fill("input[name='username']", ADMIN_USER)
    page.fill("input[name='password']", ADMIN_PASS)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    # 确认已登录（不在登录页了）
    assert "login" not in page.url.lower(), f"浏览器登录失败，仍在登录页: {page.url}"
    return page
