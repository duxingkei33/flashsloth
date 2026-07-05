"""FlashSloth 模块导入完整性测试"""
import sys, os
sys.path.insert(0, '/home/duxingkei/.hermes')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

errors = []
success = []

def check(name, fn):
    try:
        fn()
        success.append(f"✅ {name}")
    except Exception as e:
        errors.append(f"❌ {name}: {e}")

# 核心模块
check("Article 模型", lambda: __import__('flashsloth.core.article', fromlist=['Article']))
check("Publisher 基类", lambda: __import__('flashsloth.core.publisher', fromlist=['Publisher']))
check("Deployer 基类", lambda: __import__('flashsloth.core.deployer', fromlist=['Deployer']))
check("Signin 基类", lambda: __import__('flashsloth.core.signin', fromlist=['SigninBase']))
check("AI Provider", lambda: __import__('flashsloth.core.ai_provider', fromlist=['AIProvider']))
check("Config 模块", lambda: __import__('flashsloth.core.config', fromlist=['load_config']))
check("Storage 模块", lambda: __import__('flashsloth.core.storage', fromlist=['get_storage']))
check("Captcha 模块", lambda: __import__('flashsloth.core.captcha_handler', fromlist=['get_handler']))

# 插件导入
plugin_imports = [
    ('publisher_wordpress', 'flashsloth.plugins.publisher_wordpress'),
    ('publisher_wechat', 'flashsloth.plugins.publisher_wechat'),
    ('publisher_juejin', 'flashsloth.plugins.publisher_juejin'),
    ('publisher_rss', 'flashsloth.plugins.publisher_rss'),
    ('publisher_zhihu', 'flashsloth.plugins.publisher_zhihu'),
    ('publisher_csdn', 'flashsloth.plugins.publisher_csdn'),
    ('publisher_discuz', 'flashsloth.plugins.publisher_discuz'),
    ('publisher_github_pages', 'flashsloth.plugins.publisher_github_pages'),
    ('deployer_github_pages', 'flashsloth.plugins.deployer_github_pages'),
    ('storage_alist', 'flashsloth.plugins.storage_alist'),
    ('forum_reader', 'flashsloth.plugins.forum_reader'),
    ('browser_session', 'flashsloth.plugins.browser_session'),
    # 注: signin_discuz 需要 forum_signin.py 的 orchestrator bootstrapping（core_signin 模块），
    # 不在 admin.py 的直接导入范围内。admin.py 通过 import forum_signin 间接引入。

]
for name, mod_path in plugin_imports:
    check(name, lambda p=mod_path: __import__(p, fromlist=['']))

# SDK 适配器
sdk_imports = [
    ('sdk/adapters/mydigit', 'flashsloth.sdk.adapters.mydigit'),
    ('sdk/adapters/amobbs', 'flashsloth.sdk.adapters.amobbs'),
    ('sdk/adapters/csdn', 'flashsloth.sdk.adapters.csdn'),
    ('sdk/adapters/notion', 'flashsloth.sdk.adapters.notion'),
    ('sdk/adapters/github_pages', 'flashsloth.sdk.adapters.github_pages'),
]
for name, mod_path in sdk_imports:
    check(name, lambda p=mod_path: __import__(p, fromlist=['']))

# 验证注册后的插件数量
check("Publisher 注册 (import后)", lambda: (
    __import__('flashsloth.core.publisher', fromlist=['list_publishers']),
    [__import__(f'flashsloth.plugins.{n}', fromlist=['']) for n in
     ['publisher_wordpress','publisher_wechat','publisher_juejin',
      'publisher_rss','publisher_zhihu','publisher_csdn',
      'publisher_discuz','publisher_github_pages']],
    print(f"  已注册: {len(__import__('flashsloth.core.publisher', fromlist=['list_publishers']).list_publishers())} 个")
))

print(f"\n{'='*40}")
print(f"通过: {len(success)}  失败: {len(errors)}")
if errors:
    print(f"\n失败详情:")
    for e in errors:
        print(f"  {e}")
