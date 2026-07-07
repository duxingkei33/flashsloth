#!/usr/bin/env python3
"""
闲鱼自动回复 Sidecar 状态检查脚本

用法:
  python3 check_xianyu_auto_reply.py          # 仅检查状态
  python3 check_xianyu_auto_reply.py --start  # 尝试启动 Docker 并检查

输出 JSON:
  {"running": true/false, "healthy": true/false, "api": true/false, "error": "..."}
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error


XIANYU_DIR = os.path.expanduser("~/.hermes/flashsloth/xianyu-auto-reply")
HEALTH_URL = "http://localhost:8089/health"
DOCKER_COMPOSE = "docker compose -f docker-compose.yml -f docker-compose.flashsloth.yml"


def check_api() -> dict:
    """检查 xianyu-auto-reply API 是否可达"""
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        if resp.status == 200:
            return {"api": True, "status": "healthy"}
        return {"api": False, "status": f"HTTP {resp.status}"}
    except urllib.error.URLError as e:
        return {"api": False, "status": f"连接失败: {e.reason}"}
    except Exception as e:
        return {"api": False, "status": str(e)}


def check_docker_containers() -> dict:
    """检查 Docker 容器运行状态"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=xianyu-", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"docker": False, "containers": [], "error": result.stderr.strip()}

        containers = {}
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            name = parts[0]
            status = parts[1] if len(parts) > 1 else "unknown"
            containers[name] = {"status": status, "healthy": "healthy" in status.lower()}

        return {"docker": True, "containers": containers, "error": ""}
    except FileNotFoundError:
        return {"docker": False, "containers": [], "error": "Docker CLI not found"}
    except subprocess.TimeoutExpired:
        return {"docker": False, "containers": [], "error": "Docker command timed out"}
    except Exception as e:
        return {"docker": False, "containers": [], "error": str(e)}


def start_docker_service():
    """尝试启动 Docker 服务和 xianyu-auto-reply"""
    print("⏳ 尝试启动 Docker 服务...")

    # 尝试启动 dockerd
    dockerd_proc = subprocess.Popen(
        ["sudo", "dockerd", "--iptables=false", "--bip=172.18.0.1/16"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # 等待 Docker 就绪
    for i in range(30):
        time.sleep(2)
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            print("✅ Docker 服务已启动")
            break
    else:
        dockerd_proc.kill()
        print("❌ Docker 启动超时")
        return False

    # 启动 xianyu-auto-reply
    print("⏳ 启动 xianyu-auto-reply 容器...")
    result = subprocess.run(
        f"cd {XIANYU_DIR} && {DOCKER_COMPOSE} up -d --build",
        shell=True, capture_output=True, text=True, timeout=600,
    )
    if result.returncode == 0:
        print("✅ xianyu-auto-reply 启动成功")
        return True
    else:
        print(f"❌ 启动失败: {result.stderr}")
        return False


def main():
    result = {
        "running": False,
        "healthy": False,
        "api": False,
        "containers": {},
        "error": "",
    }

    # 检查 Docker 容器
    docker_status = check_docker_containers()
    result["containers"] = docker_status.get("containers", {})

    if not docker_status.get("docker"):
        result["error"] = docker_status.get("error", "Docker 不可用")
    else:
        expected = {"xianyu-mysql", "xianyu-redis", "xianyu-backend-web",
                     "xianyu-websocket", "xianyu-scheduler", "xianyu-frontend"}
        running = set(docker_status.get("containers", {}).keys())
        result["running"] = expected.issubset(running)

    # 检查 API
    api_status = check_api()
    result["api"] = api_status.get("api", False)
    result["healthy"] = api_status.get("api", False)

    # 尝试启动
    if "--start" in sys.argv and not result["healthy"]:
        print("⚠️ 服务未运行，尝试启动...")
        if start_docker_service():
            # 再次检查
            time.sleep(5)
            docker_status = check_docker_containers()
            api_status = check_api()
            result["containers"] = docker_status.get("containers", {})
            result["running"] = docker_status.get("docker", False)
            result["api"] = api_status.get("api", False)
            result["healthy"] = api_status.get("api", False)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
