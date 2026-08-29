#!/bin/bash
# 一次性导出 Chrome cookie 到本地文件（必须在用户自己的终端运行，不能由 Agent 沙箱执行）
# 之后每次提取直接用该文件，不再触发钥匙串弹窗；cookie 过期时重跑本脚本即可
set -e

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$SKILL_DIR/.venv/bin/python"
OUT="$HOME/.config/video-transcript/cookies.txt"

if [ ! -x "$VENV_PY" ]; then
  echo "❌ 未找到 $VENV_PY，请先运行 scripts/setup.sh"
  exit 1
fi

FFMPEG="$("$VENV_PY" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"

echo "== 导出 Chrome cookie（一次性）=="
echo "过程中若弹出钥匙串密码框（Chrome Safe Storage），请输入密码并点「始终允许」"
echo "（弹窗可能出现多次，属正常现象，逐个点「始终允许」即可）"
echo ""

"$VENV_PY" -m yt_dlp \
  --cookies-from-browser chrome \
  --cookies "$OUT" \
  --ffmpeg-location "$FFMPEG" \
  --simulate --no-playlist \
  "https://www.douyin.com/"

chmod 600 "$OUT"
echo ""
echo "✅ 已导出: $OUT（权限 600）"
echo "今后提取文案不会再弹钥匙串窗口；若数月后提示 cookie 过期，重跑本脚本即可"
