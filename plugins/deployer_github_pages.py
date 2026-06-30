"""
GitHub Pages Deployer — 将静态站点部署到 GitHub Pages
支持 Token 认证，通过 git push 到 Pages 仓库完成部署
"""
import os, subprocess, json, requests
from datetime import datetime
from flashsloth.core.deployer import Deployer, register


@register
class GitHubPagesDeployer(Deployer):
    name = "github_pages"
    display_name = "GitHub Pages"
    description = "部署静态站点到 GitHub Pages（git push 到 Pages 仓库）"
    config_fields = [
        {
            "key": "github_username",
            "label": "GitHub 用户名",
            "type": "text",
            "required": True,
            "placeholder": "duxingkei33",
        },
        {
            "key": "github_token",
            "label": "GitHub Token (Personal Access Token)",
            "type": "password",
            "required": True,
            "placeholder": "ghp_xxxxxxxxxxxx",
        },
        {
            "key": "repo",
            "label": "仓库 (owner/repo)",
            "type": "text",
            "required": True,
            "default": "duxingkei33/duxingkei33.github.io",
            "placeholder": "用户名/仓库名",
        },
        {
            "key": "repo_dir",
            "label": "本地仓库目录",
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
        self.github_username = config.get("github_username", "")
        self.github_token = config.get("github_token", "")
        self.repo = config.get("repo", "")
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
            # 1. 配置 git remote 使用 Token 认证
            self._configure_auth()

            # 2. 检查是否有变更
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

            # 先 pull（rebase）避免远程落后导致 push 失败
            try:
                self._run_git("pull", "--rebase", "origin", self.branch)
            except subprocess.CalledProcessError:
                pass  # 第一次部署没有 upstream 或 rebase 冲突都跳过

            # git push
            push_out = self._run_git("push", "origin", self.branch)

            # 获取最新 commit
            commit_hash = self._run_git("rev-parse", "--short", "HEAD").strip()

            # 4. 清理认证缓存
            self._clean_auth()

            return {
                "success": True,
                "url": self.site_url,
                "error": "",
                "message": f"部署完成: {changed_count} 文件, commit {commit_hash}。GitHub Pages 需要 1-2 分钟生效。",
                "commit": commit_hash,
                "changed": changed_count,
            }

        except subprocess.CalledProcessError as e:
            self._clean_auth()
            return {
                "success": False,
                "error": f"Git 操作失败: {e.stderr or e.output[:500]}",
                "url": "",
            }
        except Exception as e:
            self._clean_auth()
            return {
                "success": False,
                "error": f"部署异常: {e}",
                "url": "",
            }

    def test_connection(self) -> dict:
        """测试：
        1. 仓库目录是否存在
        2. GitHub Token 是否有效
        """
        # 测试 Token
        if self.github_token and self.github_username:
            try:
                resp = requests.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"token {self.github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=10,
                )
                if resp.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Token 无效 (HTTP {resp.status_code})",
                        "status": "认证失败",
                    }
                gh_user = resp.json().get("login", "")
                if gh_user.lower() != self.github_username.lower():
                    return {
                        "success": False,
                        "error": f"Token 的用户 ({gh_user}) 与配置的用户名 ({self.github_username}) 不匹配",
                        "status": "用户不匹配",
                    }
            except requests.RequestException as e:
                return {
                    "success": False,
                    "error": f"GitHub API 连接失败: {e}",
                    "status": "连接失败",
                }

        # 测试仓库目录
        if not os.path.isdir(self.repo_dir):
            return {
                "success": False,
                "error": "仓库目录不存在",
                "status": "目录不存在",
            }

        # 测试 repo 配置
        try:
            self._configure_auth()
            self._run_git("status")
            remote = self._run_git("remote", "get-url", "origin").strip()
            self._clean_auth()
            return {
                "success": True,
                "error": "",
                "status": f"Token 有效，仓库正常: {self.repo}",
            }
        except Exception as e:
            self._clean_auth()
            return {"success": False, "error": str(e), "status": "连接失败"}

    def _configure_auth(self):
        """配置 git remote URL 使用 Token 认证"""
        authenticated_url = (
            f"https://{self.github_username}:{self.github_token}"
            f"@github.com/{self.repo}.git"
        )
        # 使用 set-url 覆盖
        current = self._run_git("remote", "get-url", "origin").strip()
        if current != authenticated_url:
            self._run_git("remote", "set-url", "origin", authenticated_url)
            # 缓存旧的 URL 用于清理
            self._old_remote = current
        else:
            self._old_remote = None

    def _clean_auth(self):
        """恢复 remote URL（移掉 Token）"""
        if hasattr(self, '_old_remote') and self._old_remote:
            try:
                self._run_git("remote", "set-url", "origin", self._old_remote)
            except Exception:
                pass
            self._old_remote = None

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
