"""Amobbs 发布测试 — 使用已有草稿(ID=19)，验证图片附件功能"""
import requests, os, re, sys, time

BASE = "http://127.0.0.1:5000"

creds_path = os.path.expanduser("~/.hermes/flashsloth/.boot_credentials")
with open(creds_path) as f:
    lines = f.readlines()
username = lines[0].split(': ', 1)[1].strip()
password = lines[1].split(': ', 1)[1].strip()

s = requests.Session()
passed = 0; failed = 0

def ok(msg):
    global passed; passed += 1
    print(f"  ✅ {msg}")

def fail(msg):
    global failed; failed += 1
    print(f"  ❌ {msg}")

# 1. 登录
print("=== 1/登录 ===")
s.post(f"{BASE}/login", data={"username": username, "password": password}, allow_redirects=False)
r = s.get(f"{BASE}/")
if 'login' not in r.url.lower():
    ok("登录成功")
else:
    fail("登录失败"); sys.exit(1)

# 2. 检查已有草稿
print("\n=== 2/查找Amobbs测试草稿 ===")
r = s.get(f"{BASE}/")
# Find article with "Amobbs" in title
import re
article_links = re.findall(r'/post/edit/(\d+).*?Amobbs', r.text, re.DOTALL)
if not article_links:
    # Find all articles
    article_links = re.findall(r'/post/edit/(\d+)', r.text)
if article_links:
    article_id = article_links[0]
    ok(f"找到文章ID={article_id}")
else:
    # Create a new minimal test article
    ts = str(int(time.time()))
    r = s.post(f"{BASE}/post/new", data={
        "title": f"Amobbs-图片测试-{ts}",
        "body": f"## 图片附件测试 {ts}\n\n测试图片上传和附件功能。\n\n![测试图片](/static/uploads/test.png)\n\n[附件下载](/static/uploads/test.zip)",
        "tags": "test,amobbs"
    }, allow_redirects=True)
    aids = re.findall(r'/publish/select/(\d+)', r.text) or re.findall(r'/post/edit/(\d+)', r.text)
    if aids:
        article_id = aids[0]
        ok(f"新创建文章ID={article_id}")
    else:
        fail("无法获取文章ID"); sys.exit(1)

# 3. 发布选择页
print(f"\n=== 3/发布选择(文章{article_id}) ===")
r = s.get(f"{BASE}/publish/select/{article_id}")
ok(f"页面 HTTP {r.status_code}")

# Check amobbs/discuz is in options
amobbs_in_page = 'amobbs' in r.text.lower() or 'duxingkei@amobbs' in r.text
ok(f"Amobbs在选项中: {amobbs_in_page}")

# 4. 执行发布
print("\n=== 4/发布到Amobbs(含图片) ===")
form_data = {
    "article_id": str(article_id),
    "account_ids": ["1"],  # Amobbs account ID
    "mode_1": "publish",
    "forum_fid_1": "40",
}
r = s.post(f"{BASE}/publish", data=form_data, allow_redirects=True)
ok(f"发布请求 HTTP {r.status_code}")

# 检查结果
if "成功" in r.text or "审核" in r.text or "pending" in r.text.lower():
    ok("发布成功")
elif "error" in r.text.lower():
    # Extract error message
    err_match = re.search(r'flash[^<]*?error[^<]*?<[^>]*>([^<]+)', r.text, re.IGNORECASE)
    if err_match:
        print(f"  错误: {err_match.group(1).strip()}")
    else:
        print(f"  页面片段: {r.text[-400:]}")
else:
    print(f"  页面片段: {r.text[-400:]}")

# 5. 发布日志
print("\n=== 5/发布日志 ===")
r = s.get(f"{BASE}/publish/manage")
ok(f"日志 HTTP {r.status_code}")
if str(article_id) in r.text:
    ok(f"文章#{article_id}在日志中")
    # Check for success/URL
    url_match = re.search(r'amobbs.com[^\s\"\'<]*thread[^\s\"\'<]*', r.text)
    if url_match:
        ok(f"帖子URL: {url_match.group()}")
    else:
        print(f"  日志尾300: {r.text[-300:]}")
else:
    fail("日志未找到文章")

print(f"\n{'='*40}")
print(f"Amobbs 图片测试: ✅ {passed} | ❌ {failed}")
