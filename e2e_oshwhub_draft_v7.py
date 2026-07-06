"""
OSHWHub 存草稿 E2E 验证 — 独立 Playwright 脚本 (子进程模式)
运行: source venv/bin/activate && PYTHONPATH=$HOME/.hermes python e2e_oshwhub_draft_v7.py
"""
import json, sys, os, logging, sqlite3, subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_oshwhub")

# 读账号
db_path = os.path.join(os.path.dirname(__file__), "flashsloth.db")
conn = sqlite3.connect(db_path)
row = conn.execute("SELECT config_json FROM platform_accounts WHERE platform='oshwhub' LIMIT 1").fetchone()
conn.close()
cfg = json.loads(row[0])
USERNAME = cfg.get("username", "")
PASSWORD = cfg.get("password", "")
SITE = "https://oshwhub.com"
logger.info(f"用户名: {USERNAME[:4]}***")

# 封面
cover_path = "/tmp/oshwhub_test_cover.png"
from PIL import Image, ImageDraw
img = Image.new("RGB", (800, 600), color=(41, 128, 185))
draw = ImageDraw.Draw(img)
draw.text((400, 280), "E2E Cover", fill="white", anchor="mm")
img.save(cover_path)

TEST_BODY = "<h2>ESP32-S3 摄像头采集性能调优</h2><p>本文介绍 ESP32-S3 配合 OV2640 摄像头进行图像采集的关键优化点。</p>"

# 从模板生成子进程脚本
template_path = os.path.join(os.path.dirname(__file__), "pw_oshwhub_e2e_template.py")
pw_script_path = "/tmp/pw_oshwhub_e2e.py"
with open(template_path) as f:
    template = f.read()
script = template.replace("__SITE__", SITE).replace("__USERNAME__", USERNAME).replace("__PASSWORD__", PASSWORD).replace("__COVER__", cover_path).replace("__BODY__", TEST_BODY)
with open(pw_script_path, "w") as f:
    f.write(script)

# 运行子进程
logger.info("启动 Playwright 子进程...")
result = subprocess.run(
    [sys.executable, pw_script_path],
    capture_output=True, text=True, timeout=180,
    env={**os.environ, "PYTHONPATH": os.path.dirname(__file__)}
)
print(result.stdout)
if result.stderr:
    tail = result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr
    if tail.strip():
        print(f"STDERR: {tail}")
print(f"Exit: {result.returncode}")

# 清理
for p in [cover_path, pw_script_path]:
    try: os.unlink(p)
    except: pass
