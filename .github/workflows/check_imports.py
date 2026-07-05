"""CI import check — verifies all modules load correctly"""
import sys, os
# The check script is at .github/workflows/check_imports.py
# flashsloth package is two dirs up at the repo root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # .github/workflows/
REPO_ROOT = os.path.dirname(SCRIPT_DIR)  # .github/
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", ".."))  # repo root

from flashsloth.core.article import Article
from flashsloth.core.publisher import list_publishers
from flashsloth.core.deployer import list_deployers
from flashsloth.core.captcha_handler import CaptchaHandler, CaptchaProvider

import flashsloth.plugins.publisher_discuz
import flashsloth.plugins.publisher_csdn
import flashsloth.plugins.publisher_wechat
import flashsloth.plugins.publisher_zhihu
import flashsloth.plugins.publisher_github_pages
import flashsloth.plugins.publisher_rss
import flashsloth.plugins.publisher_wordpress
import flashsloth.plugins.publisher_juejin

pubs = list_publishers()
assert len(pubs) >= 6, f"Expected >=6 publishers, got {len(pubs)}"
print(f"OK: {len(pubs)} publishers registered")
for p in pubs:
    print(f"  - {p['name']}: {p['display_name']}")
