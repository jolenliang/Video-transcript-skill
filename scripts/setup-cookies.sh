#!/bin/bash
# 旧版兼容工具：当前版本的抖音主流程不再使用 cookies.txt。
# 不要把此脚本作为新安装或 403 故障的默认解决方案。
# 仅在用户明确需要维护旧版安装时，才由用户在自己的终端手动执行。
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

# yt-dlp 的抖音解析器不认首页，必须用具体视频页触发 cookie 导出；可用参数覆盖
EXPORT_URL="${1:-https://www.douyin.com/video/7670918074329025792}"

if ! "$VENV_PY" -m yt_dlp \
  --cookies-from-browser chrome \
  --cookies "$OUT" \
  --ffmpeg-location "$FFMPEG" \
  --simulate --no-playlist \
  "$EXPORT_URL"; then
  echo ""
  echo "❌ 导出失败。默认视频页可能已失效，可传入任意一条抖音视频链接重试："
  echo "  bash $0 \"https://www.douyin.com/video/xxxx\""
  exit 1
fi

chmod 600 "$OUT"
echo ""
echo "✅ 已导出: $OUT（权限 600）"
echo "今后提取文案不会再弹钥匙串窗口；若数月后提示 cookie 过期，重跑本脚本即可"
