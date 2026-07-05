#!/usr/bin/env python3
"""
FlashSloth 全生命周期管理脚本

职责：
  1. 启动/停止/重启 FlashSloth 本地服务（端口 5000）
  2. 管理 frpc 隧道（独立守护，不因 FS 重启而重启）
  3. E2E 全链路验证：本地5000 → frpc → VPS:5001

使用方式：
  python3 fs_mgr.py start      # 启动 FS + 确保 frpc 在运行
  python3 fs_mgr.py stop       # 停止 FS（不碰 frpc）
  python3 fs_mgr.py restart    # 重启 FS
  python3 fs_mgr.py status     # 查看状态
  python3 fs_mgr.py test       # 全链路测试（本地+VPS+签到）
  python3 fs_mgr.py tunnel     # 仅确保隧道运行

原则：
  - frpc 是独立守护，不因 FS 操作而受影响
  - 任何 VPS/frpc 相关操作前，先检查现有隧道状态
  - 全链路验证必须走 VPS 外网地址
"""
import os, sys, time, json, subprocess, signal, socket, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
FRPC_BIN = os.path.expanduser("~/.hermes/bin/frpc")
FRPC_CONFIG = os.path.join(ROOT, "frpc.toml")
FS_CMD = f"cd {ROOT} && PYTHONPATH={os.path.dirname(ROOT)} python3 admin.py"
PID_FILE = os.path.join(ROOT, ".fs.pid")
TUNNEL_PID_FILE = os.path.join(ROOT, ".frpc.pid")
VPS_URL = "http://103.97.178.234:5001"
LOCAL_URL = "http://localhost:5000"

# ─── 工具函数 ─────────────────────────────────────

def log(msg):
    print(f"[FS-MGR] {msg}")

def find_pid(pattern, fallback_file=None):
    """查找进程 PID"""
    # 先尝试 pgrep
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = [int(p) for p in result.stdout.strip().split()]
            return pids[0] if pids else None
    except:
        pass
    # 回退到 pid 文件
    if fallback_file and os.path.isfile(fallback_file):
        with open(fallback_file) as f:
            try:
                pid = int(f.read().strip())
                if os.path.isdir(f"/proc/{pid}"):
                    return pid
            except:
                pass
    return None

def is_port_open(port, host="127.0.0.1", timeout=2):
    """检查端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    finally:
        sock.close()

def http_get(url, timeout=10):
    """HTTP GET 请求"""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)

# ─── frps 管理 API ────────────────────────────────

FRPS_AUTH = "admin:Vps@211211"
FRPS_BASE = "http://103.97.178.234:7500"

def _frps_api(path, method="GET"):
    """调用 frps 管理 API"""
    url = FRPS_BASE + path
    b64 = __import__('base64').b64encode(FRPS_AUTH.encode()).decode()
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Basic {b64}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode()
            try:
                return json.loads(body)
            except:
                return {"raw": body, "status": r.status}
    except urllib.error.HTTPError as e:
        return {"error": str(e.code)}
    except Exception as e:
        return {"error": str(e)}

def list_vps_proxies():
    """列出 VPS 侧所有代理"""
    data = _frps_api("/api/proxy/tcp")
    proxies = data.get("proxies", [])
    result = []
    for p in proxies:
        conf = p.get("conf") or {}
        result.append({
            "name": p["name"],
            "status": p.get("status", "?"),
            "port": str(conf.get("remotePort", "?")),
            "client": p.get("clientID", "?")[:12] if p.get("clientID") else "?",
        })
    return result

# ─── 隧道管理 ──────────────────────────────────────

def ensure_tunnel():
    """确保 frpc 隧道在运行（不动已有的运行中隧道）"""
    # 先检查是否已有 frpc 运行
    existing = find_pid("frpc.*frpc.toml", TUNNEL_PID_FILE)
    if existing:
        log(f"✅ 隧道已运行 (PID {existing})")
        return True
    
    log("🔄 启动 frpc 隧道...")
    try:
        proc = subprocess.Popen(
            [FRPC_BIN, "-c", FRPC_CONFIG],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
        # 写 PID 文件
        with open(TUNNEL_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        time.sleep(3)
        
        # 验证 VPS 端口可达
        status, _ = http_get(VPS_URL)
        if status in (200, 302):
            log(f"✅ 隧道已启动 (PID {proc.pid})，VPS 响应 {status}")
            return True
        else:
            log(f"⚠️ 隧道已启动但 VPS 返回 {status}（可能 frps 服务端有僵尸代理）")
            return False
    except Exception as e:
        log(f"❌ 隧道启动失败: {e}")
        return False

# ─── FS 服务管理 ───────────────────────────────────

def start_fs():
    """启动 FlashSloth 服务"""
    existing = find_pid("python3.*admin.py", PID_FILE)
    if existing:
        if is_port_open(5000):
            log(f"✅ FS 服务已在运行 (PID {existing})")
            return True
        else:
            log(f"⚠️ PID {existing} 存在但端口 5000 未响应，重启...")
            stop_fs()

    log("🔄 启动 FlashSloth...")
    try:
        proc = subprocess.Popen(
            ["python3", "admin.py"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            env={**os.environ, "PYTHONPATH": os.path.dirname(ROOT)},
        )
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
        time.sleep(4)
        
        if is_port_open(5000):
            log(f"✅ FS 服务已启动 (PID {proc.pid})")
            return True
        else:
            log("❌ FS 启动失败，端口 5000 未开放")
            return False
    except Exception as e:
        log(f"❌ FS 启动异常: {e}")
        return False

def stop_fs():
    """停止 FlashSloth 服务（不动隧道）"""
    pid = find_pid("python3.*admin.py", PID_FILE)
    if not pid:
        log("ℹ️  FS 服务未运行")
        return True
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(2)
        if find_pid("python3.*admin.py"):
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)
        log(f"✅ FS 服务已停止 (PID {pid})")
        if os.path.isfile(PID_FILE):
            os.remove(PID_FILE)
        return True
    except Exception as e:
        log(f"⚠️ 停止异常: {e}")
        return False

# ─── 全链路测试 ────────────────────────────────────

def run_e2e_test():
    """全链路端到端验证"""
    print("\n" + "="*60)
    print("  🔍 FlashSloth 全链路测试")
    print("="*60)
    errors = []

    # 1. 本地服务
    print(f"\n📡 1/4 本地服务  {LOCAL_URL}")
    if is_port_open(5000):
        status, _ = http_get(LOCAL_URL)
        print(f"   ✅ 端口开放，HTTP {status}")
    else:
        print(f"   ❌ 端口 5000 未开放")
        errors.append("本地服务未启动")

    # 2. frpc 隧道
    print(f"\n🔗 2/4 frpc 隧道")
    tunnel_pid = find_pid("frpc.*frpc.toml", TUNNEL_PID_FILE)
    if tunnel_pid:
        print(f"   ✅ 本地隧道进程 (PID {tunnel_pid})")
    else:
        print(f"   ❌ 本地隧道未运行")
        errors.append("frpc 未运行")
    
    # 3. VPS 端
    print(f"\n🌐 3/4 VPS 服务  {VPS_URL}")
    status, body = http_get(VPS_URL)
    if status in (200, 302):
        print(f"   ✅ VPS 响应 HTTP {status}")
    else:
        print(f"   ❌ VPS 不可达 (HTTP {status})")
        errors.append("VPS 不可达")
        # 诊断：列出 VPS 侧代理
        print(f"\n   📋 VPS 端代理列表:")
        for p in list_vps_proxies():
            marker = " ⬅️ 当前FS" if p["name"] in ("fastsloth2", "fastsloth3") else ""
            print(f"      {p['name']:30s} port={p['port']:5s} status={p['status']:8s}{marker}")

    # 4. 签到测试
    print(f"\n✅ 4/4 签到系统")
    try:
        result = subprocess.run(
            ["python3", "plugins/forum_signin.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONPATH": os.path.dirname(ROOT)},
        )
        output = result.stdout.strip()
        plugins = [l for l in output.split("\n") if "插件" in l]
        results = [l for l in output.split("\n") if l.startswith("✅") or l.startswith("❌") or l.startswith("ℹ️")]
        for line in plugins:
            print(f"   📦 {line.strip()}")
        for line in results:
            print(f"   {line.strip()}")
    except Exception as e:
        print(f"   ⚠️ 签到测试异常: {e}")

    # 汇总
    print(f"\n{'='*60}")
    if errors:
        print(f"❌ {len(errors)} 个问题:")
        for e in errors:
            print(f"   - {e}")
    else:
        print("✅ 所有检查通过！")
    print(f"{'='*60}\n")
    return len(errors) == 0

# ─── 主入口 ───────────────────────────────────────

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"

    if action == "start":
        ensure_tunnel()
        start_fs()
    elif action == "stop":
        stop_fs()
    elif action == "restart":
        stop_fs()
        time.sleep(1)
        start_fs()
    elif action == "tunnel":
        ensure_tunnel()
    elif action == "test":
        run_e2e_test()
    elif action == "status":
        # FS 状态
        fs_pid = find_pid("python3.*admin.py", PID_FILE)
        fs_ok = is_port_open(5000)
        print(f"FS 服务: {'✅ 运行中' if fs_ok else '❌ 未运行'} (PID {fs_pid or 'N/A'})")
        # 隧道状态
        t_pid = find_pid("frpc.*frpc.toml", TUNNEL_PID_FILE)
        print(f"frpc 隧道: {'✅ 运行中' if t_pid else '❌ 未运行'} (PID {t_pid or 'N/A'})")
        # VPS
        vps_status, _ = http_get(VPS_URL)
        print(f"VPS 端口: {'✅' if vps_status in (200,302) else '❌'} (HTTP {vps_status})")
        # 代理列表
        print("\nVPS 代理列表:")
        for p in list_vps_proxies():
            marker = " ⬅️" if p["name"] in ("fastsloth2", "fastsloth3") else ""
            print(f"  {p['name']:30s} port={str(p['port']):5s} status={p['status']:8s}{marker}")
    else:
        print(f"用法: {sys.argv[0]} [start|stop|restart|status|test|tunnel]")
