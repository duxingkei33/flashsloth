"""
无浏览器版数码之家探索 — 用 requests 模拟
读取版规、公告、附件限制等公开信息
"""
import re, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["FLASHSLOT_SKIP_AUTH"] = "1"

import requests

SITE = "https://www.mydigit.cn"
COOKIE = "security_session_verify=f914cba344c390591e5da3fd9a180323; VhUn_2132_saltkey=IrvJJvVg; VhUn_2132_lastvisit=1782748430; VhUn_2132_lastact=1782752032%09member.php%09logging; VhUn_2132_ulastactivity=1782752032%7C0; VhUn_2132_auth=cfadIKXWJI7YytmyzLevcaMGKn3dQTZ9tLjFhAogPKqJ8UYL6Ug95miAjsDdVbHHUft7NVN9EAgf0xfoZHVrHPul2BSZ; VhUn_2132_lastcheckfeed=1722267%7C1782752032; VhUn_2132_checkfollow=1; VhUn_2132_lip=103.97.178.234%2C1782752032"

sess = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
for c in COOKIE.split("; "):
    if "=" in c:
        k, v = c.split("=", 1)
        sess.cookies.set(k.strip(), v.strip(), domain=".mydigit.cn")

findings = {}

# 1. 首页 — 登录状态
print("=" * 60)
print("[1] 访问首页")
r = sess.get(f"{SITE}/forum.php", headers=headers, timeout=30)
print(f"  HTTP {r.status_code}, 长度: {len(r.text)}")

# 检查登录
if "duxingkei" in r.text:
    print("  ✅ 已登录 (发现用户名)")
    findings["login"] = "✅ 已登录"
else:
    print("  ⚠️ 未检测到登录状态")
    findings["login"] = "⚠️ 未检测到登录"

# 2. 公告页
print("=" * 60)
print("[2] 论坛公告")
r2 = sess.get(f"{SITE}/forum.php?mod=announcement", headers=headers, timeout=30)
print(f"  HTTP {r2.status_code}")
if "公告" in r2.text or "announcement" in r2.url:
    ann_text = re.search(r'<div[^>]*class="mn"[^>]*>(.*?)</div>', r2.text, re.DOTALL)
    if ann_text:
        text = re.sub(r"<[^>]+>", " ", ann_text.group(1)).strip()[:1000]
        print(f"  📢 公告: {text}")
        findings["announcement"] = text

# 3. 板块列表 — 获取 fid=40 的版块规则
print("=" * 60)
print("[3] 板块 fid=40 详情")
r3 = sess.get(f"{SITE}/forum.php?mod=forumdisplay&fid=40", headers=headers, timeout=30)
print(f"  HTTP {r3.status_code}")

# 检查板块规则区域
for pattern in [r'<div[^>]*class="rules"[^>]*>(.*?)</div>',
                r'<div[^>]*id="forumrules"[^>]*>(.*?)</div>',
                r'<div[^>]*class="bn"[^>]*>(.*?)</div>']:
    m = re.search(pattern, r3.text, re.DOTALL)
    if m:
        rules = re.sub(r"<[^>]+>", " ", m.group(1)).strip()[:2000]
        print(f"  板块规则: {rules}")
        findings["forum_rules"] = rules
        break

# 获取置顶帖子（版规帖）
sticky_posts = re.findall(r'<th[^>]*class="common[^"]*"[^>]*>.*?<a[^>]*href="([^"]*thread[^"]*)"[^>]*>(.*?)</a>', r3.text, re.DOTALL)
print(f"  置顶帖子: {len(sticky_posts)} 个")
findings["sticky_count"] = len(sticky_posts)
for url, title in sticky_posts[:8]:
    t = re.sub(r"<[^>]+>", "", title).strip()
    print(f"    📌 {t}")

# 4. 尝试读取第一个版规帖
print("=" * 60)
print("[4] 读取版规帖子")
# 找含有"规"字的置顶帖
for url, title in sticky_posts:
    t = re.sub(r"<[^>]+>", "", title).strip()
    if any(kw in t for kw in ["规", "公告", "须知", "指南", "帮助", "教程", "必读", "限制", "上传"]):
        full_url = url if url.startswith("http") else f"{SITE}/{url.lstrip('/')}"
        print(f"  读取: {t} → {full_url}")
        r4 = sess.get(full_url, headers=headers, timeout=30)
        # 提取帖子正文
        content_patterns = [
            r'<td[^>]*class="t_f"[^>]*>(.*?)</td>',
            r'<div[^>]*class="pcb"[^>]*>(.*?)<div[^>]*class="psth"',
            r'<div[^>]*class="message"[^>]*>(.*?)<div[^>]*class="status"',
            r'<div[^>]*class="t_fsz"[^>]*>(.*?)<div[^>]*class="pstl"',
        ]
        post_text = ""
        for p in content_patterns:
            m = re.search(p, r4.text, re.DOTALL)
            if m:
                post_text = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
                break
        if not post_text:
            # Fallback: 取整个帖子区
            m = re.search(r'<div[^>]*id="postlist"[^>]*>(.*?)<div[^>]*id="post_new"', r4.text, re.DOTALL)
            if m:
                post_text = re.sub(r"<[^>]+>", " ", m.group(1)).strip()[:3000]
        if post_text:
            print(f"  📄 内容 ({len(post_text)} chars):")
            print(post_text[:2000])
            findings[f"post_{t[:20]}"] = post_text[:3000]
        else:
            print("  ⚠️ 无法提取帖子内容")
        break

# 5. 访问发帖页 — 检查编辑器限制
print("=" * 60)
print("[5] 发帖页面 — 检查编辑器限制")
r5 = sess.get(f"{SITE}/forum.php?mod=post&action=newthread&fid=40", headers=headers, timeout=30)
print(f"  HTTP {r5.status_code}")

# 标题长度
title_max = re.search(r'name="subject"[^>]*maxlength="(\d+)"', r5.text)
title_max2 = re.search(r'id="subject"[^>]*maxlength="(\d+)"', r5.text)
if title_max:
    print(f"  标题最大长度: {title_max.group(1)}")
    findings["title_maxlength"] = int(title_max.group(1))
elif title_max2:
    print(f"  标题最大长度: {title_max2.group(1)}")
    findings["title_maxlength"] = int(title_max2.group(1))
else:
    print("  标题输入框: 未找到 maxlength 属性")
    findings["title_maxlength"] = "80 (未找到, 使用Discuz默认)"

# 上传限制 — 查找上传区域的限制说明
upload_limits = re.findall(r'(?:允许|支持|附件|扩展名|格式|类型|大小|尺寸|限制|上限|最大)[：:\s]*[^。<]{0,200}', r5.text)
if upload_limits:
    print(f"  上传相关提示: {upload_limits[:5]}")
    findings["upload_hints"] = upload_limits[:5]

# 查找文件扩展名列表
ext_patterns = re.findall(r'\.(?:jpg|jpeg|png|gif|bmp|zip|rar|pdf|doc|txt|7z|tar|gz)(?:\s*[,，、]\s*\.?(?:jpg|jpeg|png|gif|bmp|zip|rar|pdf|doc|txt|7z|tar|gz))*', r5.text)
if ext_patterns:
    print(f"  发现扩展名: {ext_patterns[:3]}")
    findings["extensions"] = ext_patterns[:3]

# 大小限制
size_patterns = re.findall(r'(\d+\.?\d*)\s*(KB|MB|GB|K|M)', r5.text, re.IGNORECASE)
if size_patterns:
    print(f"  大小限制: {size_patterns[:5]}")
    findings["size_limits"] = size_patterns[:5]

# 图片尺寸限制
dims = re.findall(r'(\d+)\s*[xX×]\s*(\d+)', r5.text)
if dims:
    print(f"  图片尺寸: {dims[:3]}")
    findings["image_dimensions"] = dims[:3]

# 检查表单字段
formhash = re.search(r'name="formhash"[^>]+value="([^"]+)"', r5.text)
print(f"  formhash: {formhash.group(1) if formhash else '未找到'}")

# 检查是否需要主题分类
typeid = re.search(r'name="typeid"', r5.text)
print(f"  主题分类: {'需要' if typeid else '不需要'}")

# 检查是否有发帖权限
if "您没有权限" in r5.text or "403" in r5.text[:500]:
    print("  ⚠️ 无发帖权限!")
    findings["post_permission"] = "无发帖权限"
else:
    print("  ✅ 有发帖权限")
    findings["post_permission"] = "✅ 有发帖权限"

# 检查是否有额外编辑器字段（比如标签 tags）
tags = re.search(r'name="tags"', r5.text)
if tags:
    print("  📌 有标签字段")
    findings["has_tags"] = True

# 检查是否有阅读权限/售价等
readperm = re.search(r'readperm', r5.text)
price = re.search(r'price', r5.text)
if readperm:
    print("  📌 有阅读权限设置")
    findings["has_readperm"] = True
if price:
    print("  📌 有售价设置")
    findings["has_price"] = True

# 6. 看看帖子详情页的附件信息
print("=" * 60)
print("[6] 检查附件/图片上传提示")
# 从首页获取一个最近的帖子看看附件
recent_threads = re.findall(r'href="(thread-\d+-1-1\.html)"[^>]*>(.*?)</a>', r3.text, re.DOTALL)
for url, title in recent_threads[:3]:
    t = re.sub(r"<[^>]+>", "", title).strip()
    full_url = f"{SITE}/{url}"
    print(f"  读取帖子: {t[:50]}")
    r6 = sess.get(full_url, headers=headers, timeout=30)
    
    # 检查附件信息
    attach_info = re.findall(r'(?:附件|下载|大小|售价|积分)[^。<)]{0,100}', r6.text)
    if attach_info:
        print(f"    附件信息: {attach_info[:3]}")
        findings["attachment_info"] = attach_info[:3]
    
    # 检查图片是否附带尺寸限制
    img_info = re.findall(r'<img[^>]*file=[^>]*>', r6.text)
    if img_info:
        print(f"    帖内图片数: {len(img_info)}")
        findings["post_images"] = len(img_info)
    break  # 只看一个帖子

# 保存结果
print("\n" + "=" * 60)
print("探索结果摘要:")
for k, v in findings.items():
    print(f"\n  📌 {k}:")
    if isinstance(v, str) and len(v) > 200:
        print(f"    {v[:200]}...")
    else:
        print(f"    {v}")

output = {"timestamp": __import__("time").strftime("%Y-%m-%d %H:%M:%S"), "findings": {k: v for k, v in findings.items()}}
with open("/tmp/mydigit_request_exploration.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)
print(f"\n✅ 探索结果保存至 /tmp/mydigit_request_exploration.json")
