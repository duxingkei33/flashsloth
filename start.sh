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

# ── 3. 持久化 uploads 目录 ────────────────────────
_UPLOAD_DIR="${DATA_DIR}/uploads"
mkdir -p "${_UPLOAD_DIR}"

# 检查 static/uploads 是否存在且为符号链接
if [ -L "static/uploads" ]; then
    # 已经是符号链接，确认指向正确
    _LINK_TARGET="$(readlink "static/uploads")"
    if [ "${_LINK_TARGET}" != "${_UPLOAD_DIR}" ]; then
        echo "🔄 更新 uploads 符号链接: ${_LINK_TARGET} → ${_UPLOAD_DIR}"
        rm -f "static/uploads"
        ln -sf "${_UPLOAD_DIR}" "static/uploads"
    fi
elif [ -d "static/uploads" ]; then
    # 是真目录，迁移到持久目录
    echo "📦 迁移 static/uploads 到持久目录..."
    rsync -a static/uploads/ "${_UPLOAD_DIR}/"
    rm -rf "static/uploads"
    ln -sf "${_UPLOAD_DIR}" "static/uploads"
    echo "✅ 迁移完成（共 $(find "${_UPLOAD_DIR}" -type f 2>/dev/null | wc -l) 个文件）"
elif [ ! -e "static/uploads" ]; then
    # 不存在，创建符号链接
    ln -sf "${_UPLOAD_DIR}" "static/uploads"
    echo "🔗 已创建 uploads 符号链接"
fi

# ── 4. 激活虚拟环境 ────────────────────────────────
if [ -d "${VENV_DIR}" ]; then
    source "${VENV_DIR}/bin/activate"
    echo "🐍 虚拟环境: ${VENV_DIR}"
fi

# ── 5. 设置生产环境变量 ──────────────────────────
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

# ── 6. 启动 Flask 应用 ────────────────────────────
echo "🌐 http://0.0.0.0:5000"
echo ""
exec python3 admin.py
