#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/miyaosk/dex-quant-skill.git"
SKILLS=(strategy-designer backtest-coder backtest-reviewer signal-runtime-builder execution-guard)

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

if [ "$PLATFORM" = "codex" ]; then
    echo "请重启 Codex 以加载新 Skills。"
elif [ "$PLATFORM" = "cursor" ]; then
    echo "请重启 Cursor 以加载新 Skills。"
    echo ""
    echo "在对话中使用:"
    echo "  · 直接描述策略需求，Agent 会自动调用 strategy-designer"
    echo "  · 说"生成回测代码"，Agent 会调用 backtest-coder"
    echo "  · 说"评审一下回测结果"，Agent 会调用 backtest-reviewer"
    echo "  · 说"部署信号监控"，Agent 会调用 signal-runtime-builder"
    echo "  · 说"执行这个信号"，Agent 会调用 execution-guard"
fi
echo ""
