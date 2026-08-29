---
name: video-transcript
description: 提取抖音视频口播文案并沉淀为 Obsidian Markdown 笔记。当用户粘贴抖音/douyin.com 链接（尤其是 v.douyin.com 短链）并要求提取文案/转文字/逐字稿/字幕时触发；也支持用户直接提供本地视频文件转文字。触发词示例："提取这条抖音的文案"、"视频转文字"、"口播稿整理"。仅限 macOS。
---

# Video-transcript · 抖音文案提取

把抖音视频的口播内容转成文字，经 DeepSeek 加工（摘要/要点/标签）后写入 Obsidian。

约定：`SKILL_DIR` = 本 SKILL.md 所在目录。

## 前置检查（每次执行前）

依次确认，缺失则跳到「故障处理」对应条目：

1. `~/.config/video-transcript/.env` 存在（API Keys）
2. `~/.config/video-transcript/config.json` 存在（笔记目录）
3. `SKILL_DIR/.venv/bin/python` 存在（依赖环境）
4. `~/.config/video-transcript/cookies.txt` 存在（cookie 文件，仅 --url 分支需要）

## 执行

**分支 A：链接**（优先）。从用户消息中用正则提取 `https?://\S*douyin\.com/\S+`：

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/extract.py --url "<链接>"
```

**分支 B：本地视频文件**（链接解析失败兜底，或用户直接给文件）：

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/extract.py --file "<视频文件绝对路径>"
```

全流程约 30-90 秒，不要中途打断。完成后把脚本输出的摘要/要点/标签整理呈现给用户，并展示生成的 Markdown 文件路径。

## 故障处理（按顺序）

1. **缺 .env** → 让用户在【自己的终端】运行 `bash SKILL_DIR/scripts/setup-keys.sh`（Key 输入不回显，不要让用户在对话里粘贴 Key）
2. **缺 config.json 或 .venv** → 运行 `bash SKILL_DIR/scripts/setup.sh` 并按其输出引导
3. **缺 cookies.txt 或报 cookie 相关错误** → 让用户在【自己的终端】运行 `bash SKILL_DIR/scripts/setup-cookies.sh`（必须由用户终端执行：Agent 沙箱会拦截钥匙串写入，自动导出只会得到不完整的 cookie）。导出时若弹钥匙串密码框（可能弹多次），逐个点「始终允许」
4. **报 "Fresh cookies needed" 但 cookie 刚导出** → 这是 TLS 指纹被抖音拦截的典型症状，检查 `.venv` 里是否装了 `curl_cffi`（没有则 `SKILL_DIR/.venv/bin/pip install "curl_cffi>=0.15"`）
5. 仍失败 → Chrome 重新登录 douyin.com，然后重跑 setup-cookies.sh
6. 仍失败 → 升级 yt-dlp：`SKILL_DIR/.venv/bin/pip install -U yt-dlp`
7. 仍失败 → 引导用户走分支 B：抖音 App「保存本地」，把视频文件提供给 Agent
8. **ASR 报错** → 检查硅基流动控制台额度与模型状态；503 等临时错误直接重试一次
9. **macOS 反复弹钥匙串密码框（Chrome Safe Storage）** → 说明 cookies.txt 缺失或失效，走第 3 步导出一次即可根治；不要试图靠点「Always Allow」解决（Agent 沙箱会拦截授权写入，且 Chrome 更新会重写该钥匙串项）

## 边界

- 一次处理一条链接；批量需求逐条串行执行并提醒反爬风险
- 纯自用工具，提取内容用于个人学习沉淀
- 视频/音频本身不落盘，只有 Markdown 笔记永久保存
