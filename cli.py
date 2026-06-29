#!/usr/bin/env python3
"""
FlashSloth CLI — 命令行发布工具
用法:
  python -m flashsloth.cli publish --article <file> --to wordpress,wechat
  python -m flashsloth.cli build
  python -m flashsloth.cli status
"""
import sys, os, argparse, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flashsloth.core.article import Article
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.config import load_config, get_publisher_config
# 导入 Publisher 插件触发注册
import flashsloth.plugins.publisher_wordpress  # noqa
import flashsloth.plugins.publisher_wechat     # noqa
import flashsloth.plugins.publisher_juejin     # noqa
import flashsloth.plugins.publisher_rss        # noqa
import flashsloth.plugins.publisher_zhihu      # noqa
import flashsloth.plugins.publisher_csdn       # noqa
import flashsloth.plugins.publisher_discuz     # noqa


def cmd_publish(args):
    """发布文章到指定平台"""
    config = load_config()

    # 读取文章
    if args.article:
        with open(args.article) as f:
            article = Article.from_markdown(f.read())
    elif args.stdin:
        article = Article.from_markdown(sys.stdin.read())
    else:
        article = Article(title="测试文章", body="这是 FlashSloth 的测试发布。")
        if not args.force:
            print("⚠️  无文章输入，使用测试文章。加 --force 确认。")
            return

    print(f"\n📄 发布文章: {article.title}")
    print(f"   正文: {len(article.body)} 字")
    print(f"   标签: {', '.join(article.tags) or '无'}")

    # 确定发布目标
    targets = args.to or config.get("publishers", {}).keys()

    results = {}
    for name in targets:
        if name == "rss":
            continue  # RSS 由 builder 统一生成
        print(f"\n🚀 发布到 [{name}] ...")
        try:
            pub_config = get_publisher_config(config, name)
            publisher = get_publisher(name, pub_config)
            result = publisher.publish(article)
            results[name] = result
            if result["success"]:
                print(f"   ✅ 成功: {result.get('url', result.get('id', 'OK'))}")
                if result.get("note"):
                    print(f"   💡 {result['note']}")
            else:
                print(f"   ❌ 失败: {result['error']}")
        except Exception as e:
            results[name] = {"success": False, "error": str(e)}
            print(f"   ❌ 异常: {e}")

    return results


def cmd_build(args):
    """构建静态站点"""
    from flashsloth.plugins.publisher_rss import RSSPublisher
    config = load_config()

    # 读取文章
    posts_dir = config.get("provider", {}).get("markdown", {}).get("watch_dir", "blog/docs/posts/")
    articles = []
    if os.path.exists(posts_dir):
        for f in sorted(os.listdir(posts_dir)):
            if f.endswith(".md"):
                with open(os.path.join(posts_dir, f)) as fh:
                    articles.append(Article.from_markdown(fh.read()))

    print(f"📚 共 {len(articles)} 篇文章")

    # 生成 RSS
    rss_cfg = get_publisher_config(config, "rss")
    if rss_cfg.get("enabled", True):
        rss = RSSPublisher(rss_cfg)
        result = rss._generate_feed(articles)
        print(f"📡 RSS: {'✅' if result['success'] else '❌'} {result.get('error', '')}")

    # 调 MkDocs 构建
    os.system("cd blog && mkdocs build")
    print("🏗️  站点构建完成")


def cmd_status(args):
    """查看当前配置和 Publisher 状态"""
    config = load_config()
    print(f"\n{'='*50}")
    print(f"  FlashSloth 🦥⚡ 状态")
    print(f"{'='*50}")

    print(f"\n📦 已注册 Publisher:")
    for p in list_publishers():
        cfg = get_publisher_config(config, p["name"])
        enabled = cfg.get("enabled", p["name"] == "rss")
        missing = [f["key"] for f in p["config_fields"] if f.get("required") and not cfg.get(f["key"])]
        status = "✅ 已配置" if (enabled and not missing) else "⚠️  待配置"
        if missing:
            status += f" (缺: {', '.join(missing)})"
        print(f"  {p['display_name']:>12s}  [{status}]")

    print()


def main():
    parser = argparse.ArgumentParser(description="FlashSloth — 树懒的速度，闪电的发布")
    sub = parser.add_subparsers(dest="command")

    p_pub = sub.add_parser("publish", help="发布文章到各平台")
    p_pub.add_argument("--article", "-a", help="Markdown 文件路径")
    p_pub.add_argument("--stdin", action="store_true", help="从 stdin 读入")
    p_pub.add_argument("--to", nargs="+", help="发布目标，如 wordpress wechat")
    p_pub.add_argument("--force", action="store_true", help="强制发布测试文章")

    p_build = sub.add_parser("build", help="构建静态站点 + RSS")
    p_status = sub.add_parser("status", help="查看状态")

    args = parser.parse_args()
    if args.command == "publish":
        cmd_publish(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
