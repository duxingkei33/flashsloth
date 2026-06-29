"""
GitHub Pages Deployer — 将静态站点部署到 GitHub Pages
通过 git commit + push 到 Pages 仓库完成部署
"""
import os, subprocess, json
from datetime import datetime
from flashsloth.core.deployer import Deployer, register


@register
class GitHubPagesDeployer(Deployer):
    name = "github_pages"
    display_name = "GitHub Pages"
    description = "部署静态站点到 GitHub Pages（git push 到 Pages 仓库）"
    config_fields = [
        {
            "key": "repo_dir",
            "label": "仓库目录",
            "type": "text",
            "required": True,
            "default": "/opt/data/contenthub",
            "placeholder": "GitHub Pages 仓库的本地路径",
        },
        {
            "key": "site_url",
            "label": "站点地址",
            "type": "text",
            "required": False,
            "default": "https://duxingkei33.github.io",
            "placeholder": "https://duxingkei33.github.io",
        },
        {
            "key": "branch",
            "label": "分支",
            "type": "text",
            "required": False,
            "default": "main",
            "placeholder": "main",
        },
        {
            "key": "commit_prefix",
            "label": "提交前缀",
            "type": "text",
            "required": False,
            "default": "deploy",
            "placeholder": "deploy",
        },
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.repo_dir = os.path.expanduser(
            config.get("repo_dir", "/opt/data/contenthub")
        )
        self.site_url = config.get("site_url", "https://duxingkei33.github.io")
        self.branch = config.get("branch", "main")
        self.commit_prefix = config.get("commit_prefix", "deploy")

    def deploy(self) -> dict:
        """执行 git commit + push 部署"""
        missing = self.validate_config()
        if missing:
            return {
                "success": False,
                "error": f"缺少配置: {', '.join(missing)}",
                "url": "",
            }

        if not os.path.isdir(self.repo_dir):
            return {
                "success": False,
                "error": f"仓库目录不存在: {self.repo_dir}",
                "url": "",
            }

        try:
            # 检查是否有变更
            result = self._run_git("status", "--porcelain")
            if not result.strip():
                return {
                    "success": True,
                    "url": self.site_url,
                    "error": "",
                    "message": "无变更，无需部署",
                }

            changed_count = len([l for l in result.split("\n") if l.strip()])
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

            # git add
            self._run_git("add", "-A")

            # git commit
            commit_msg = f"{self.commit_prefix}: {changed_count} file(s) @ {timestamp}"
            self._run_git("commit", "-m", commit_msg)

            # git push
            push_out = self._run_git("push", "origin", self.branch)

            # 获取最新 commit
            commit_hash = self._run_git("rev-parse", "--short", "HEAD").strip()

            return {
                "success": True,
                "url": self.site_url,
                "error": "",
                "message": f"部署完成: {changed_count} 文件, commit {commit_hash}",
                "commit": commit_hash,
                "changed": changed_count,
            }

        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": f"Git 操作失败: {e.stderr or e.output[:500]}",
                "url": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"部署异常: {e}",
                "url": "",
            }

    def test_connection(self) -> dict:
        """测试仓库是否可访问"""
        if not os.path.isdir(self.repo_dir):
            return {"success": False, "error": "仓库目录不存在", "status": "失败"}
        try:
            self._run_git("status")
            remote = self._run_git("remote", "get-url", "origin").strip()
            return {
                "success": True,
                "error": "",
                "status": f"仓库正常: {remote}",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": "连接失败"}

    def _run_git(self, *args) -> str:
        """在 repo_dir 中执行 git 命令"""
        result = subprocess.run(
            ["git"] + list(args),
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result.stdout
