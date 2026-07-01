#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# FlashSloth 自动化测试运行脚本
#
# 用法：
#   ./tests/run.sh              # 运行全部测试
#   ./tests/run.sh --api        # 只跑 API 测试
#   ./tests/run.sh --ui         # 只跑浏览器 UI 测试
#   ./tests/run.sh --verbose    # 详细输出
#   ./tests/run.sh --list       # 列出测试
# ═══════════════════════════════════════════════════

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"

echo "═══════════════════════════════════════════════"
echo " FlashSloth 自动化测试套件"
echo "═══════════════════════════════════════════════"
echo "项目路径: ${PROJECT_DIR}"
echo ""

# ── 1. 检查虚拟环境 ────────────────────────────────
if [ ! -d "${VENV_DIR}" ]; then
    echo "❌ 虚拟环境不存在: ${VENV_DIR}"
    echo "   请先运行: python3 -m venv ${VENV_DIR}"
    exit 1
fi
source "${VENV_DIR}/bin/activate"

# ── 2. 检查 Flask 服务 ─────────────────────────────
echo "🔍 检查 FlashSloth 服务..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/ 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "000" ]; then
    echo "❌ FlashSloth 服务未运行！请先启动:"
    echo "   cd ${PROJECT_DIR} && source .venv/bin/activate && python3 admin.py"
    echo ""
    echo "⚠️  或者在后台启动后重试。"
    exit 1
fi
echo "✅ FlashSloth 服务运行中 (HTTP ${HTTP_CODE})"
echo ""

# ── 3. 解析参数 ────────────────────────────────────
PYTEST_ARGS=(
    "-v"
    "--tb=short"
    "--color=yes"
)

UI_FLAG=false
API_FLAG=false
VERBOSE=false
LIST_FLAG=false

for arg in "$@"; do
    case "$arg" in
        --api)       API_FLAG=true ;;
        --ui)        UI_FLAG=true ;;
        --verbose)   VERBOSE=true ;;
        --list)      LIST_FLAG=true ;;
        --help|-h)
            echo "参数:"
            echo "  --api        只跑 API 测试"
            echo "  --ui         只跑浏览器 UI 测试"
            echo "  --verbose    详细输出（含print）"
            echo "  --list       列出测试用例"
            exit 0
            ;;
    esac
done

if [ "$VERBOSE" = true ]; then
    PYTEST_ARGS+=("-s")
fi

if [ "$API_FLAG" = true ] && [ "$UI_FLAG" = true ]; then
    # 都选了 = 跑全部
    API_FLAG=false
    UI_FLAG=false
fi

# ── 4. 构建 pytest 参数 ────────────────────────────
TEST_TARGET="tests/"

if [ "$API_FLAG" = true ]; then
    TEST_TARGET="tests/"
    PYTEST_ARGS+=("-k" "not ui")
    echo "🔬 测试模式: API 测试 (跳过浏览器测试)"
elif [ "$UI_FLAG" = true ]; then
    TEST_TARGET="tests/"
    PYTEST_ARGS+=("-k" "ui")
    echo "🔬 测试模式: 浏览器 UI 测试"
else
    echo "🔬 测试模式: 全部测试"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 5. 列出或执行测试 ─────────────────────────────
if [ "$LIST_FLAG" = true ]; then
    echo "📋 测试用例列表:"
    python3 -m pytest "${TEST_TARGET}" --collect-only -q 2>&1 || true
    echo ""
    echo "总计: $(python3 -m pytest "${TEST_TARGET}" --collect-only -q 2>&1 | tail -1)"
else
    echo "🚀 开始测试..."
    echo ""
    python3 -m pytest "${TEST_TARGET}" "${PYTEST_ARGS[@]}"
    RESULT=$?
    echo ""
    if [ $RESULT -eq 0 ]; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "✅ 全部测试通过！"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    else
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "❌ 部分测试失败 (exit code: ${RESULT})"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
    exit $RESULT
fi
