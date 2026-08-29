#!/bin/bash
# 安全录入 API Key：终端本地输入（不回显），写入 chmod 600 的本地配置文件
# 用法: bash scripts/setup-keys.sh
# 说明: Key 只存本机 ~/.config/video-transcript/.env，不会进入任何对话或网络请求（除官方 API 调用）

set -e
CONFIG_DIR="$HOME/.config/video-transcript"
ENV_FILE="$CONFIG_DIR/.env"

mkdir -p "$CONFIG_DIR"

echo "== Video-transcript-skill · API Key 录入 =="
echo "输入不会回显，Key 只写入本机: $ENV_FILE"
echo ""
echo "两个 Key 的获取方式:"
echo "  1) 硅基流动: https://siliconflow.cn 注册 -> API 密钥（免费，用于语音转文字）"
echo "  2) DeepSeek: https://platform.deepseek.com -> API Keys（用于摘要/要点/标签）"
echo ""

read -s -p "1) 硅基流动 API Key: " SF_KEY
echo ""
read -s -p "2) DeepSeek API Key: " DS_KEY
echo ""
echo ""

if [ -z "$SF_KEY" ] || [ -z "$DS_KEY" ]; then
  echo "❌ 两个 Key 都不能为空，未写入任何内容。"
  exit 1
fi

umask 077
cat > "$ENV_FILE" <<EOF
SILICONFLOW_API_KEY=$SF_KEY
DEEPSEEK_API_KEY=$DS_KEY
EOF
chmod 600 "$ENV_FILE"

echo "✅ 已写入 $ENV_FILE（权限 600，仅本用户可读）"
