#!/usr/bin/env bash
# AI 资讯聚合 · 一键启动脚本（Linux / macOS）
# 用法：./start.sh
# 做了什么：检查 Python 3.11+ → 创建/复用 .venv → 安装依赖 → 启动服务
set -euo pipefail

cd "$(dirname "$0")"

echo "=== AI 资讯聚合 · 启动 ==="

# ---------- 1. 检查 python3 ----------
if ! command -v python3 >/dev/null 2>&1; then
    echo "错误：未找到 python3，请先安装 Python 3.11 或更高版本。"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "  macOS: brew install python@3.12"
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "错误：当前 Python 版本为 $PYVER，需要 3.11 或更高版本，请升级后再试。"
    exit 1
fi
echo "[1/5] Python 版本检查通过：$(python3 --version)"

# ---------- 2. 加载 .env（可选） ----------
if [ -f .env ]; then
    echo "[2/5] 加载 .env 配置"
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
else
    echo "[2/5] 未找到 .env，使用默认配置（端口 8000、数据目录 ./data、抓取间隔 4 小时）"
    echo "      如需修改：cp .env.example .env 后编辑"
fi
PORT="${PORT:-8000}"
# DATA_DIR 是给人看的目录；程序实际读 DB_PATH，这里做一次映射（DB_PATH 显式设置时优先）
if [ -z "${DB_PATH:-}" ] && [ -n "${DATA_DIR:-}" ]; then
    export DB_PATH="$DATA_DIR/news.db"
fi
DATA_DIR="${DATA_DIR:-./data}"
FETCH_INTERVAL_HOURS="${FETCH_INTERVAL_HOURS:-4}"

# ---------- 3. 配置校验（非法配置直接报错退出，不静默带病运行） ----------
config_ok=1
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "错误：PORT='$PORT' 非法，端口必须是 1-65535 的数字。请检查 .env。"
    config_ok=0
fi
if ! [[ "$FETCH_INTERVAL_HOURS" =~ ^[0-9]+$ ]] || [ "$FETCH_INTERVAL_HOURS" -lt 1 ]; then
    echo "错误：FETCH_INTERVAL_HOURS='$FETCH_INTERVAL_HOURS' 非法，必须是 ≥1 的整数（小时）。请检查 .env。"
    config_ok=0
fi
if ! mkdir -p "$DATA_DIR" 2>/dev/null; then
    echo "错误：数据目录 '$DATA_DIR' 无法创建（路径非法或权限不足）。请检查 .env 的 DATA_DIR。"
    config_ok=0
elif ! touch "$DATA_DIR/.write_test" 2>/dev/null; then
    echo "错误：数据目录 '$DATA_DIR' 不可写。请检查目录权限或换 DATA_DIR。"
    config_ok=0
else
    rm -f "$DATA_DIR/.write_test"
fi
if [ "$config_ok" -ne 1 ]; then
    exit 1
fi
echo "[3/5] 配置校验通过（端口 $PORT、数据目录 $DATA_DIR、抓取间隔 ${FETCH_INTERVAL_HOURS}h）"

# ---------- 4. 虚拟环境 + 依赖 ----------
if [ ! -d .venv ]; then
    echo "[4/5] 创建虚拟环境 .venv ..."
    python3 -m venv .venv
else
    echo "[4/5] 复用已有虚拟环境 .venv"
fi

# requirements.txt 变化时才重装，避免每次启动都联网检查
hash_file=".venv/.requirements.sha256"
if command -v sha256sum >/dev/null 2>&1; then
    cur_hash=$(sha256sum requirements.txt | awk '{print $1}')
else
    cur_hash=$(shasum -a 256 requirements.txt | awk '{print $1}')
fi
if [ ! -f "$hash_file" ] || [ "$(cat "$hash_file")" != "$cur_hash" ]; then
    echo "      安装/更新依赖（requirements.txt 有变化）..."
    .venv/bin/pip install --quiet -r requirements.txt
    echo "$cur_hash" > "$hash_file"
else
    echo "      依赖无变化，跳过安装"
fi

# ---------- 5. 启动 ----------
echo "[5/5] 启动服务 ..."
echo ""
echo "  热榜：  http://localhost:${PORT}/hot"
echo "  时间线：http://localhost:${PORT}/timeline"
echo "  设置：  http://localhost:${PORT}/settings  （摘要功能需先在这里填模型 key）"
echo ""
echo "  按 Ctrl+C 停止服务。数据保存在 ./data/news.db，备份拷走就行。"
echo ""
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
