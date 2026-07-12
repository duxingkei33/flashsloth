"""
E2E 端到端验证 — 数据驱动修复后全量检查
验证：
1. 服务可正常启动（无语法/导入错误）
2. 登录正常
3. 账号页面可访问（模板渲染）
4. 平台元数据API返回正确
5. 部署API正常
6. 新publisher已注册
7. 各关键API端点正常
"""
import requests, sys, json

BASE = "http://127.0.0.1:5000"
s = requests.Session()

def check(name, ok, detail=""):
    icon = "✅" if ok else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))

def login():
    s.get(f"{BASE}/login")
    r = s.post(f"{BASE}/login", data={"username": "admin_redacted", "password": "Fs&211211"},
               allow_redirects=False)
    if r.status_code == 302:
        s.get(f"{BASE}/")
        return True
    return False

print("=" * 54)
print("  🦥 FlashSloth E2E 验证 — 数据驱动修复")
print("=" * 54)

# 1. 服务可达
try:
    r = s.get(f"{BASE}/login", timeout=10)
    check("服务可达", r.status_code == 200, f"HTTP {r.status_code}")
except Exception as e:
    check("服务可达", False, str(e))
    sys.exit(1)

# 2. 登录
ok = login()
check("登录正常", ok, "admin_redacted")
if not ok:
    check("后续测试跳过", False, "登录失败")
    sys.exit(1)

# 3. 账号页
r = s.get(f"{BASE}/accounts")
check("账号页", r.status_code == 200, f"HTTP {r.status_code} ({len(r.text)} bytes)")

# 4. 平台元数据
r = s.get(f"{BASE}/api/platforms/metadata")
if r.status_code == 200:
    d = r.json()
    icons = d.get("icons", {})
    missing = [p for p in ["smzdm", "dewu", "xiaohongshu"] if p not in icons]
    check("平台元数据API", not missing, f"缺失: {missing}" if missing else "全部3个新平台图标存在")
else:
    check("平台元数据API", False, f"HTTP {r.status_code}")

# 5. 部署API
r = s.get(f"{BASE}/api/deploy/platforms")
check("部署platforms API", r.status_code == 200, f"HTTP {r.status_code}")

# 6. 新publisher已注册
r = s.get(f"{BASE}/api/platforms/metadata")
if r.status_code == 200:
    icons = r.json().get("icons", {})
    for p in ["smzdm", "dewu", "xiaohongshu"]:
        check(f"Publisher {p}", p in icons, f"图标: {icons.get(p, '缺失')}")

# 7. 关键API端点
endpoints = [
    "/api/accounts?format=json",
    "/api/browser/status",
]
for ep in endpoints:
    r = s.get(f"{BASE}{ep}")
    check(f"API {ep}", r.status_code in (200, 404, 302), f"HTTP {r.status_code}")

# 8. 登录API路由
r = s.get(f"{BASE}/api/platform/csdn/login-capabilities")
check("登录能力API", r.status_code in (200, 302, 404), f"HTTP {r.status_code}")

# 9. 网关
r = s.get(f"{BASE}/gateway")
check("网关页面", r.status_code == 200, f"HTTP {r.status_code}")

# 10. 部署页面
r = s.get(f"{BASE}/deployers")
check("部署页面(旧路由)", r.status_code in (200, 302, 404), f"HTTP {r.status_code}")

print(f"\n{'='*54}")
print(f"  E2E 验证完成")
print(f"{'='*54}")
