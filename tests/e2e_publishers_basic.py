"""
E2E 发布器基础验证脚本 — 测试编译 + 注册 + API
运行: cd ~/.hermes/flashsloth && source venv/bin/activate && PYTHONPATH=$HOME/.hermes python tests/e2e_publishers_basic.py
"""
import sys, os, json, logging, importlib

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("e2e_basic")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ══════════════════════════════════════
# 先导入所有 publisher 模块（注册到 _registry）
# ══════════════════════════════════════
PUBLISHER_MODULES = [
    "flashsloth.plugins.publisher_zhihu",
    "flashsloth.plugins.publisher_juejin",
    "flashsloth.plugins.publisher_bilibili",
    "flashsloth.plugins.publisher_wechat",
    "flashsloth.plugins.publisher_twitter",
    "flashsloth.plugins.publisher_csdn",
    "flashsloth.plugins.publisher_oshwhub",
    "flashsloth.plugins.publisher_xianyu",
    "flashsloth.plugins.publisher_wordpress",
]
for mod_name in PUBLISHER_MODULES:
    importlib.import_module(mod_name)

from flashsloth.core.article import Article
from flashsloth.core.publisher import list_publishers, _registry
from flashsloth.core.compiler import Compiler

EXPECTED = {
    "zhihu": "知乎",
    "juejin": "掘金",
    "bilibili": "Bilibili 专栏",
    "wechat": "微信公众号",
    "twitter": "Twitter/X",
    "csdn": "CSDN",
    "oshwhub": "OSHWHub",
    "xianyu": "闲鱼",
    "wordpress": "WordPress",
}


def test_registry():
    pubs = list_publishers()
    names = {p["name"]: p["display_name"] for p in pubs}
    ok = 0
    for name, display in EXPECTED.items():
        if name in names:
            if names[name] == display:
                log.info(f"  ✅ {name:12s} → {display}")
            else:
                log.info(f"  ⚠️ {name:12s} → {names[name]} (期望 {display})")
            ok += 1
        else:
            log.info(f"  ❌ {name:12s} 缺失")
    log.info(f"\n📊 注册: {ok}/{len(EXPECTED)} 通过")
    return ok == len(EXPECTED)


def test_compilation():
    article = Article(
        title="E2E 测试文章",
        body="# Hello\n\nThis is a **test** article.",
        summary="Test summary",
        tags=["test"],
    )
    compiler = Compiler()
    try:
        result = compiler.compile(source=article, targets=["discuz", "csdn"])
        ok = bool(result and "discuz" in result and "csdn" in result)
        log.info(f"  ✅ 多平台编译: {'通过' if ok else '失败'}")
        for plat, content in result.items():
            log.info(f"     {plat:10s}: {len(content.body)}b, success={content.success}")
        return ok
    except Exception as e:
        log.error(f"  ❌ 编译异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_health():
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:5000/api/signin/config", timeout=5)
        data = json.loads(resp.read())
        ok = data.get("success", False)
        log.info(f"  ✅ /api/signin/config → {'OK' if ok else '失败'}")
        return ok
    except Exception as e:
        log.warning(f"  ⚠️ /api/signin/config 不可达: {e}")
        return False


if __name__ == "__main__":
    log.info("=" * 50)
    log.info("FlashSloth 发布器 E2E 基础验证")
    log.info("=" * 50)

    log.info("\n🔧 测试 1/3: 注册列表")
    c1 = test_registry()

    log.info("\n🔧 测试 2/3: 文章编译")
    c2 = test_compilation()

    log.info("\n🔧 测试 3/3: API 健康检查")
    c3 = test_api_health()

    log.info("\n" + "=" * 50)
    ok = sum([c1, c2, c3])
    log.info(f"📊 结果: {ok}/3 通过")
    if c1 and c2 and c3:
        log.info("✅ 全部通过！")
    log.info("=" * 50)
