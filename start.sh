#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# FlashSloth 生产环境启动脚本
#
# 数据分离：
#   - 生产数据库在 ~/.hermes/flashsloth_data/flashsloth.db
#   - 与 git 仓库完全隔离，测试不会污染生产数据
# ═══════════════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
DATA_DIR="${HOME}/.hermes/flashsloth_data"

echo "═══════════════════════════════════════════════"
echo " 🦥 FlashSloth — 生产模式启动"
echo "═══════════════════════════════════════════════"

# ── 1. 确保持久数据目录存在 ─────────────────────────
mkdir -p "${DATA_DIR}"

# ── 2. 如果持久目录没有 DB，但项目根有旧 DB，复制过去 ──
if [ ! -f "${DATA_DIR}/flashsloth.db" ] && [ -f "flashsloth.db" ]; then
    echo "📦 迁移已有数据库到持久目录..."
    cp flashsloth.db "${DATA_DIR}/flashsloth.db"
    echo "✅ 迁移完成"
fi

# ── 3. 激活虚拟环境 ────────────────────────────────
if [ -d "${VENV_DIR}" ]; then
    source "${VENV_DIR}/bin/activate"
    echo "🐍 虚拟环境: ${VENV_DIR}"
fi

# ── 4. 设置生产环境变量 ──────────────────────────
export FLASHSLOTH_DB_PATH="${DATA_DIR}/flashsloth.db"
echo "🗄️  数据库: ${FLASHSLOTH_DB_PATH}"

# 固定 Secret Key，防止重启后 session 失效
_SECRET_FILE="${DATA_DIR}/.secret_key"
if [ ! -f "${_SECRET_FILE}" ]; then
    python3 -c "import secrets; print(secrets.token_hex(32))" > "${_SECRET_FILE}"
    echo "🔑 已生成固定密钥"
fi
export FLASHSLOTH_SECRET="$(cat "${_SECRET_FILE}")"
echo "🔐 FLASHSLOTH_SECRET 已固定（重启不丢 session）"

# ── 5. 启动 Flask 应用 ────────────────────────────
echo "🌐 http://0.0.0.0:5000"
echo ""
exec python3 admin.py
