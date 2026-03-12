#!/usr/bin/env bash
set -euo pipefail

SKILLS=(strategy-designer backtest-coder backtest-reviewer signal-runtime-builder execution-guard)

PLATFORM="${1:-cursor}"
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
            echo "用法: ./uninstall.sh project /path/to/your/project"
            exit 1
        fi
        INSTALL_DIR="$2/.cursor/skills"
        CLONE_DIR="$2/.cursor/skills/_dex-quant-skill"
        ;;
    *)
        echo "用法: ./uninstall.sh [cursor|codex|project /path]"
        exit 1
        ;;
esac

echo "正在卸载 DEX Quant Skills..."
echo ""

for skill in "${SKILLS[@]}"; do
    target="$INSTALL_DIR/$skill"
    if [ -L "$target" ]; then
        rm "$target"
        echo "✅ 已移除 $skill"
    elif [ -d "$target" ]; then
        echo "⚠️  $skill 不是 symlink，跳过"
    fi
done

shared_target="$INSTALL_DIR/_dex-quant-shared"
if [ -L "$shared_target" ]; then
    rm "$shared_target"
    echo "✅ 已移除 shared"
fi

if [ -d "$CLONE_DIR" ]; then
    rm -rf "$CLONE_DIR"
    echo "✅ 已移除仓库克隆"
fi

echo ""
echo "卸载完成。请重启 Cursor/Codex。"
