#!/bin/bash
# Video-transcript-skill 安装脚本（由 AI Agent 执行，非交互）
# 用法:
#   bash scripts/setup.sh              # 第一步：装依赖 + 探测 Obsidian vault 列表
#   bash scripts/setup.sh "<vault_dir>" # 第二步：写入用户选定的笔记存放目录
set -e

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_DIR="$HOME/.config/video-transcript"
CONFIG_FILE="$CONFIG_DIR/config.json"

echo "== Video-transcript-skill 安装 =="

# 1. 系统检查
if [ "$(uname)" != "Darwin" ]; then
  echo "❌ 当前版本仅支持 macOS（Windows 适配计划中）"
  exit 1
fi

PY=""
for CANDIDATE in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  CANDIDATE_PATH="$(command -v "$CANDIDATE" || true)"
  if [ -n "$CANDIDATE_PATH" ] && [ "$("$CANDIDATE_PATH" -c 'import sys; print(1 if sys.version_info >= (3,9) else 0)')" = "1" ]; then
    PY="$CANDIDATE_PATH"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ 未找到 Python 3.9+。建议安装: brew install python@3.13"
  exit 1
fi
PY_VER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "✅ python3 $PY_VER ($PY)"

# 2. 创建 venv 并安装依赖
if [ ! -x "$SKILL_DIR/.venv/bin/python" ]; then
  echo "📦 创建虚拟环境 .venv ..."
  "$PY" -m venv "$SKILL_DIR/.venv"
fi
echo "📦 安装依赖 Playwright + yt-dlp + imageio-ffmpeg ..."
"$SKILL_DIR/.venv/bin/pip" install -q --upgrade pip playwright yt-dlp imageio-ffmpeg
echo "📦 安装 Playwright Chromium 运行时 ..."
"$SKILL_DIR/.venv/bin/python" -m playwright install chromium
echo "✅ 依赖安装完成"

mkdir -p "$CONFIG_DIR"
PROFILE_DIR="$CONFIG_DIR/browser-profile"
mkdir -p "$PROFILE_DIR"
chmod 700 "$PROFILE_DIR"
echo "✅ 已准备抖音专用浏览器 Profile: $PROFILE_DIR"

# 3. 写入 vault 配置（如果提供了参数）
if [ -n "$1" ]; then
  VAULT_DIR="$1"
  mkdir -p "$VAULT_DIR"
  "$SKILL_DIR/.venv/bin/python" - "$CONFIG_FILE" "$VAULT_DIR" <<'EOF'
import json, sys
with open(sys.argv[1], "w") as f:
    json.dump({"vault_dir": sys.argv[2]}, f, ensure_ascii=False, indent=2)
EOF
  echo "✅ 笔记存放目录已写入 $CONFIG_FILE: $VAULT_DIR"
  echo ""
  echo "== 下一步 =="
  echo "请让用户在【自己的终端】运行以下命令录入 API Key（输入不回显，Key 不经过对话）:"
  echo "  bash $SKILL_DIR/scripts/setup-keys.sh"
  exit 0
fi

# 4. 未提供参数：探测 Obsidian vault 列表，供 Agent 让用户选择
echo ""
echo "== 探测到的 Obsidian vault 列表（JSON）=="
"$SKILL_DIR/.venv/bin/python" <<'EOF'
import json, os
from pathlib import Path
obs = Path.home() / "Library/Application Support/obsidian/obsidian.json"
vaults = []
if obs.exists():
    try:
        data = json.loads(obs.read_text())
        vaults = [v["path"] for v in data.get("vaults", {}).values() if "path" in v]
    except Exception:
        pass
print(json.dumps({"vaults": vaults}, ensure_ascii=False, indent=2))
if not vaults:
    print("（未检测到 Obsidian vault，用户可指定任意本地目录存放笔记）")
EOF
echo ""
echo "== Agent 下一步 =="
echo "1) 将上述 vault 列表呈现给用户，让用户选一个，并确认子目录（默认: <vault>/I-抖音文案）"
echo "2) 再次运行: bash $SKILL_DIR/scripts/setup.sh \"<用户选定的完整目录>\""
echo "3) 首次提取抖音链接时会打开专用可见浏览器，请在该窗口中登录一次"
