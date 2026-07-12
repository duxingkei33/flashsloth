"""FlashSloth 功能测试套件"""
import sys, os, json, tempfile, unittest
sys.path.insert(0, '/home/duxingkei/.hermes')
sys.path.insert(0, '/home/duxingkei/.hermes/flashsloth')

from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, list_publishers, get_publisher
from flashsloth.core.deployer import Deployer, list_deployers

# ─── 注册测试用 Publisher ───────────────
@register
class TestPublisher(Publisher):
    name = "test_platform"
    display_name = "测试平台"
    config_fields = [
        {"key": "api_key", "label": "API Key", "type": "password", "required": True},
        {"key": "site_url", "label": "站点", "type": "text", "required": True},
    ]

    def __init__(self, config=None):
        super().__init__(config)
        self.published = []

    def publish(self, article, **kwargs):
        self.published.append(article)
        return {"success": True, "url": "https://test.com/post/1",
                "error": "", "id": "1", "message": "test post"}

    def retract(self, article, publish_log=None):
        if self.published:
            self.published.pop()
            return {"success": True, "error": "", "message": "已撤回"}
        return {"success": False, "error": "无记录可撤回", "message": ""}

    def test_connection(self):
        return {"success": True, "error": "", "status": "OK"}

# ─── 注册测试用 Deployer ───────────────
from flashsloth.core.deployer import register as dep_register
@dep_register
class TestDeployer(Deployer):
    name = "test_deployer"
    display_name = "测试部署器"
    config_fields = [
        {"key": "repo", "label": "仓库", "type": "text", "required": True},
    ]
    deployed = False

    def deploy(self):
        self.deployed = True
        return {"success": True, "url": "https://test.com", "error": "",
                "message": "部署成功"}

    def test_connection(self):
        return {"success": True, "error": "", "status": "OK"}


class TestArticle(unittest.TestCase):
    """文章模型测试"""

    def test_create_basic(self):
        a = Article(title="测试文章", body="# Hello", tags=["test"])
        self.assertEqual(a.title, "测试文章")
        self.assertEqual(a.body, "# Hello")
        self.assertEqual(a.tags, ["test"])

    def test_create_with_all_fields(self):
        a = Article(
            title="Full Article", body="Content", summary="Sum",
            tags=["a", "b"], source="manual",
            cover="https://x.com/img.jpg",
            slug="my-post", date="2026-01-01",
            metadata={"author": "me"}
        )
        self.assertEqual(a.summary, "Sum")
        self.assertEqual(a.cover, "https://x.com/img.jpg")
        self.assertEqual(a.metadata["author"], "me")

    def test_empty_title(self):
        a = Article(title="", body="Content")
        self.assertEqual(a.title, "")


class TestPublisherOps(unittest.TestCase):
    """发布器测试"""

    def setUp(self):
        self.pub = TestPublisher({"api_key": "test-key", "site_url": "https://test.com"})

    def test_publisher_name(self):
        self.assertEqual(self.pub.name, "test_platform")

    def test_publisher_display_name(self):
        self.assertEqual(self.pub.display_name, "测试平台")

    def test_publish_article(self):
        a = Article(title="测试", body="内容")
        result = self.pub.publish(a)
        self.assertTrue(result["success"])
        self.assertEqual(result["url"], "https://test.com/post/1")
        self.assertEqual(len(self.pub.published), 1)

    def test_retract_article(self):
        a = Article(title="测试", body="内容")
        self.pub.publish(a)
        result = self.pub.retract(a)
        self.assertTrue(result["success"])
        self.assertEqual(len(self.pub.published), 0)

    def test_retract_empty(self):
        result = self.pub.retract(None)
        self.assertFalse(result["success"])

    def test_test_connection(self):
        result = self.pub.test_connection()
        self.assertTrue(result["success"])

    def test_validate_config_missing(self):
        pub = TestPublisher({})
        missing = pub.validate_config()
        self.assertIn('api_key', missing)
        self.assertIn('site_url', missing)


class TestDeployerOps(unittest.TestCase):
    """部署器测试"""

    def setUp(self):
        self.dep = TestDeployer({"repo": "user/repo"})

    def test_deployer_name(self):
        self.assertEqual(self.dep.name, "test_deployer")

    def test_deploy_success(self):
        result = self.dep.deploy()
        self.assertTrue(result["success"])
        self.assertTrue(self.dep.deployed)

    def test_test_connection(self):
        result = self.dep.test_connection()
        self.assertTrue(result["success"])


class TestRegistry(unittest.TestCase):
    """注册表测试"""

    def test_list_publishers_includes_test(self):
        pubs = list_publishers()
        names = [p["name"] for p in pubs]
        self.assertIn("test_platform", names)

    def test_get_publisher(self):
        pub = get_publisher("test_platform", {"api_key": "k"})
        self.assertIsNotNone(pub)
        self.assertEqual(pub.name, "test_platform")

    def test_get_publisher_unknown(self):
        with self.assertRaises(KeyError):
            get_publisher("nonexistent", {})

    def test_list_deployers_includes_test(self):
        deps = list_deployers()
        names = [d["name"] for d in deps]
        self.assertIn("test_deployer", names)


class TestDiscuzFormatter(unittest.TestCase):
    """Discuz 内容格式转换测试"""

    def setUp(self):
        from flashsloth.plugins.publisher_discuz import DiscuzPublisher
        self.pub = DiscuzPublisher({"site_url": "https://test.com", "login_mode": "cookie", "cookie": "test=1"})

    def test_markdown_bold_to_html(self):
        result = self.pub._format_for_discuz("这是**粗体**文字")
        self.assertIn("<strong>", result)
        self.assertIn("</strong>", result)

    def test_markdown_italic_to_html(self):
        result = self.pub._format_for_discuz("这是*斜体*文字")
        self.assertIn("<em>", result)
        self.assertIn("</em>", result)

    def test_markdown_code_to_html(self):
        result = self.pub._format_for_discuz("这是`代码`文字")
        self.assertIn("<code>", result)
        self.assertIn("</code>", result)

    def test_markdown_heading_to_html(self):
        result = self.pub._format_for_discuz("# 标题1\n\n## 标题2\n\n### 标题3")
        self.assertIn("<h1>", result)
        self.assertIn("<h2>", result)
        self.assertIn("<h3>", result)

    def test_html_img_to_bbcode(self):
        result = self.pub._format_for_discuz('<img src="https://example.com/img.jpg" alt="test">')
        self.assertIn("[img]", result)
        self.assertIn("[/img]", result)
        self.assertNotIn("<img", result)

    def test_markdown_img_to_bbcode(self):
        result = self.pub._format_for_discuz('![alt](https://example.com/img.jpg)')
        self.assertIn("[img]", result)
        self.assertIn("[/img]", result)

    def test_html_link_to_url_bbcode(self):
        result = self.pub._format_for_discuz('<a href="https://example.com">点击这里</a>')
        self.assertIn("[url=", result)
        self.assertIn("[/url]", result)

    def test_local_img_path_absolute(self):
        """本地 /static/ 路径转为绝对 URL"""
        result = self.pub._format_for_discuz('<img src="/static/uploads/img.jpg">')
        # 没有 public_url 配置时，只转为 [img]/static/uploads/img.jpg[/img]
        self.assertIn("[img]", result)

    def test_paragraph_wrapping(self):
        result = self.pub._format_for_discuz("第一段\n\n第二段")
        self.assertIn("<p>", result)
        self.assertIn("</p>", result)
        # 两个段落
        self.assertEqual(result.count("<p>"), 2)


class TestSDKAdapter(unittest.TestCase):
    """SDK 适配器测试"""

    def test_sdk_import(self):
        from flashsloth.sdk import PlatformAdapter, Article as SDKArticle, register, list_adapters
        self.assertTrue(hasattr(PlatformAdapter, 'publish'))
        self.assertTrue(hasattr(PlatformAdapter, 'sign_in'))

    def test_adapter_list(self):
        # 导入适配器模块触发注册
        import flashsloth.sdk.adapters.mydigit  # noqa
        import flashsloth.sdk.adapters.amobbs  # noqa
        import flashsloth.sdk.adapters.csdn  # noqa
        import flashsloth.sdk.adapters.github_pages  # noqa
        import flashsloth.sdk.adapters.notion  # noqa
        from flashsloth.sdk import list_adapters
        adapters = list_adapters()
        names = [a["name"] for a in adapters]
        self.assertIn("mydigit", names, "mydigit adapter should be registered")
        self.assertIn("amobbs", names, "amobbs adapter should be registered")


if __name__ == "__main__":
    unittest.main(verbosity=2)
