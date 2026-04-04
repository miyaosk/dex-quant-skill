#!/usr/bin/env bash
# DEX Quant Skill 龙虾一键安装
# 用法: curl -sL https://raw.githubusercontent.com/miyaosk/dex-quant-skill/main/install-claw.sh | bash
set -euo pipefail

echo "🔧 安装 dex-quant-skill..."

# 找到真实的 skills 目录
SKILLS_DIR=""
for d in /data/.openclaw/workspace/*/; do
  echo "$d" | grep -q '[$]' && continue
  [ -d "$d" ] && SKILLS_DIR="${d}skills" && break
done

if [ -z "$SKILLS_DIR" ]; then
  echo "❌ 找不到 workspace 目录"
  exit 1
fi

mkdir -p "$SKILLS_DIR"
TARGET="$SKILLS_DIR/dex-quant-skill"

if [ -d "$TARGET/.git" ]; then
  echo "📦 更新已有安装..."
  git -C "$TARGET" pull --ff-only 2>/dev/null || git -C "$TARGET" fetch --all
else
  rm -rf "$TARGET" 2>/dev/null || true
  echo "📦 下载中..."
  git clone https://github.com/miyaosk/dex-quant-skill.git "$TARGET"
fi

# 装依赖
cd "$TARGET"
pip3 install --break-system-packages httpx loguru matplotlib 2>/dev/null \
  || pip install --break-system-packages httpx loguru matplotlib 2>/dev/null \
  || pip3 install httpx loguru matplotlib 2>/dev/null \
  || true

mkdir -p strategies output
echo "✅ 安装完成: $TARGET"
