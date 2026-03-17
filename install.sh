#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/miyaosk/dex-quant-skill.git"
SKILLS=(strategy-maker backtester monitor-executor)

# ---------- 检测目标平台 ----------
detect_platform() {
    if [ -d "$HOME/.cursor" ]; then
        echo "cursor"
    elif [ -d "${CODEX_HOME:-$HOME/.codex}" ]; then
        echo "codex"
    else
        echo "cursor"
    fi
}

# ---------- 参数解析 ----------
PLATFORM="${1:-$(detect_platform)}"
INSTALL_DIR=""
CLONE_DIR=""

case "$PLATFORM" in
    cursor)
        INSTALL_DIR="$HOME/.cursor/skills"
        CLONE_DIR="$HOME/.cursor/skills/_dex-quant-skill"
        ;;
    codex)
        INSTALL_DIR="${CODEX_HOME:-$HOME/.codex}/skills"
        CLONE_DIR="${CODEX_HOME:-$HOME/.codex}/skills/_dex-quant-skill"
        ;;
    project)
        if [ -z "${2:-}" ]; then
            echo "用法: ./install.sh project /path/to/your/project"
            exit 1
        fi
        INSTALL_DIR="$2/.cursor/skills"
        CLONE_DIR="$2/.cursor/skills/_dex-quant-skill"
        ;;
    *)
        echo "用法: ./install.sh [cursor|codex|project /path]"
        echo ""
        echo "  cursor   安装到 ~/.cursor/skills/ （个人级，所有项目可用）"
        echo "  codex    安装到 ~/.codex/skills/  （Codex 平台）"
        echo "  project  安装到指定项目的 .cursor/skills/"
        exit 1
        ;;
esac

echo "========================================="
echo "  DEX Quant Skills 安装器"
echo "========================================="
echo ""
echo "平台:     $PLATFORM"
echo "安装目录: $INSTALL_DIR"
echo "克隆到:   $CLONE_DIR"
echo ""

# ---------- 创建目录 ----------
mkdir -p "$INSTALL_DIR"

# ---------- 克隆或更新仓库 ----------
if [ -d "$CLONE_DIR/.git" ]; then
    echo "→ 仓库已存在，拉取最新..."
    git -C "$CLONE_DIR" pull --ff-only
else
    if [ -d "$CLONE_DIR" ]; then
        echo "→ 清理旧目录..."
        rm -rf "$CLONE_DIR"
    fi
    echo "→ 克隆仓库..."
    git clone "$REPO_URL" "$CLONE_DIR"
fi

echo ""

# ---------- 安装 Python 依赖 ----------
echo "→ 安装 Python 依赖..."
pip3 install --quiet httpx loguru numpy pandas yfinance 2>/dev/null || true
echo ""

# ---------- 创建 symlinks ----------
for skill in "${SKILLS[@]}"; do
    target="$INSTALL_DIR/$skill"
    source="$CLONE_DIR/$skill"

    if [ -L "$target" ]; then
        rm "$target"
    elif [ -d "$target" ]; then
        echo "⚠️  $skill/ 已存在且不是 symlink，跳过（手动删除后重试）"
        continue
    fi

    ln -s "$source" "$target"
    echo "✅ $skill → $(readlink "$target")"
done

# ---------- shared schemas symlink ----------
shared_target="$INSTALL_DIR/_dex-quant-shared"
shared_source="$CLONE_DIR/shared"

if [ -L "$shared_target" ]; then
    rm "$shared_target"
fi
ln -s "$shared_source" "$shared_target"
echo "✅ shared → $(readlink "$shared_target")"

echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "已安装的 Skills:"
for skill in "${SKILLS[@]}"; do
    echo "  · $skill"
done
echo ""
echo "服务器地址: https://quant.qa1.dex.hashkeydev.com"
echo ""

if [ "$PLATFORM" = "codex" ]; then
    echo "请重启 Codex 以加载新 Skills。"
elif [ "$PLATFORM" = "cursor" ]; then
    echo "请重启 Cursor 以加载新 Skills。"
fi

echo ""
echo "测试方法:"
echo "  1. 对 AI 说: \"帮我做一个 BTC 的 MACD 金叉死叉策略\""
echo "  2. AI 会自动生成策略脚本"
echo "  3. 说 \"帮我回测下 2025 年 1-3 月\""
echo "  4. AI 会运行脚本生成信号，发到服务器回测"
echo ""
