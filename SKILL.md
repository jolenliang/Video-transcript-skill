---
name: video-transcript
description: 提取抖音视频口播文案、小红书笔记正文（图文+视频），交给当前 Agent 生成 Obsidian Markdown 笔记。当用户粘贴抖音/douyin.com 链接（v.douyin.com 短链）或小红书链接（xhslink.cn 短链、xiaohongshu.com）并要求提取文案/转文字/逐字稿/字幕/正文时触发；也支持本地视频文件转文字。触发词示例："提取这条抖音的文案"、"存一下这篇小红书"、"视频转文字"、"口播稿整理"。仅限 macOS。
---

# Video-transcript · 抖音/小红书文案提取

本 skill 将“提取”和“理解写作”分成两个职责：脚本只负责获取完整文本和元数据，当前 Agent 负责摘要、要点、标签及最终笔记。脚本自动识别平台路由，同一条命令通吃：

- 抖音链接 → 下载音频 → ASR → pending 文件 → Agent 写入 `I-抖音文案/`
- 小红书图文 → 直接取正文（无下载无 ASR，秒级）→ pending 文件 → Agent 写入 `I-小红书文案/`
- 小红书视频笔记 → 下载音频 → ASR → pending 文件 → Agent 写入 `I-小红书文案/`

约定：`SKILL_DIR` = 本 SKILL.md 所在目录。

## 职责边界

`scripts/extract.py` 只执行平台解析、音频处理、硅基流动 SenseVoice ASR，并将完整提取文本和元数据写入：

```text
~/.config/video-transcript/pending/
```

脚本成功后输出机器可识别的绝对路径 `PENDING_FILE=/absolute/path/file.md`。它不会调用其他文本生成 API，也不会直接写入最终 Obsidian 笔记。

Agent 必须读取 `PENDING_FILE` 指向文件的完整内容，不能只依赖终端中的原文预览。默认将内容整理为以下最终结构，并根据用户要求调整：

```markdown
---
title: "..."
author: "..."
source: "..."
extracted: 2026-08-31
duration: "1:39"
tags: [标签]
---
## 摘要
...
## 要点
- ...
## 原文
...
```

Agent 应按以下顺序完成交付：

1. 读取并解析 pending 文件的完整元数据和 `## 原始文案` 内容。
2. 生成摘要、要点、标签和保真的原文排版，并写入配置的 Obsidian 目录：抖音使用 `vault_dir`，小红书使用其同级的 `I-小红书文案/`。
3. 验证最终文件存在且内容非空。
4. 只有验证成功后，执行：

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/complete.py \
  --pending "<PENDING_FILE 的绝对路径>" \
  --final "<最终 Obsidian 文件的绝对路径>"
```

`complete.py` 只会删除指定的单个 pending 文件。Agent 中断、最终写入失败、文件为空或验证失败时，不得删除 pending 文件；重试时直接读取它，不要重新请求平台或重复执行 ASR。

## 前置检查（每次执行前）

依次确认，缺失则跳到「故障处理」对应条目：

1. `~/.config/video-transcript/.env` 存在，且包含 `SILICONFLOW_API_KEY`（只需一个 API Key）
2. `~/.config/video-transcript/config.json` 存在（笔记目录）
3. `SKILL_DIR/.venv/bin/python` 存在（依赖环境）
4. `~/.config/video-transcript/cookies.txt` 存在（cookie 文件，仅抖音链接需要；小红书匿名即可）

## 执行

**分支 A：链接**（优先）。从用户消息中提取支持平台的纯 URL；如果用户消息包含 Markdown 链接，使用其中的 URL，不要把 `](...)` 或反斜杠转义符传给脚本：

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/extract.py --url "<链接>"
```

**分支 B：本地视频文件**（链接解析失败兜底，或用户直接给文件）：

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/extract.py --file "<视频文件绝对路径>"
```

全流程：小红书图文约 10 秒，视频类约 30-90 秒，不要中途打断。提取脚本成功后，读取完整 pending 文件，完成后处理并展示最终 Markdown 文件路径。不要把终端中的预览当作完整原文。

## 故障处理（按顺序）

1. **缺 .env 或缺硅基流动 Key** → 让用户在【自己的终端】运行 `bash SKILL_DIR/scripts/setup-keys.sh`（Key 输入不回显，不要让用户在对话里粘贴 Key）
2. **缺 config.json 或 .venv** → 运行 `bash SKILL_DIR/scripts/setup.sh` 并按其输出引导
3. **缺 cookies.txt 或抖音明确提示 cookie 过期/无效** → 让用户在【自己的终端】运行 `bash SKILL_DIR/scripts/setup-cookies.sh`（必须由用户终端执行：Agent 沙箱会拦截钥匙串写入，自动导出只会得到不完整的 cookie）。导出时若弹钥匙串密码框（可能弹多次），逐个点「始终允许」
4. **报 "Fresh cookies needed" 但 cookie 刚导出** → 这是 TLS 指纹被抖音拦截的典型症状，检查 `.venv` 里是否装了 `curl_cffi`（没有则 `SKILL_DIR/.venv/bin/pip install "curl_cffi>=0.15"`）
5. 仍失败 → Chrome 重新登录 douyin.com，然后重跑 setup-cookies.sh
6. **小红书解析失败** → 确认链接完整（从 App 重新复制，需带 xsec_token 参数）；间隔几分钟再试
7. 仍失败 → 升级 yt-dlp：`SKILL_DIR/.venv/bin/pip install -U yt-dlp`
8. 仍失败 → 引导用户走分支 B：App「保存本地」，把视频文件提供给 Agent
9. **ASR 报错** → 5xx 临时错误脚本已自动退避重试（5 秒 × 4 次，硅基流动部分节点不稳定属常态）；持续失败再检查硅基流动控制台额度与模型状态
10. **macOS 反复弹钥匙串密码框（Chrome Safe Storage）** → 说明 cookies.txt 缺失或失效，走第 3 步导出一次即可根治；不要试图靠点「Always Allow」解决（Agent 沙箱会拦截授权写入，且 Chrome 更新会重写该钥匙串项）
11. **pending 已存在** → 直接读取对应文件并继续生成最终笔记；不要重新运行提取脚本。只有最终文件验证成功后才调用 `complete.py`。
12. **最终文件写入或验证失败** → 保留 pending 文件，记录失败原因并修复后重试；不得批量删除 pending 文件。
13. **出现 `PermissionError: Operation not permitted` 且路径是 `~/.config/video-transcript/cookies.txt`** → 这通常是 `yt-dlp` 试图保存更新后的 cookie，而 Agent 沙箱不能改写用户 Cookie 快照；当前脚本会先复制 Cookie 到临时工作目录供 `yt-dlp` 读写，因此应先确认安装副本已更新并重试，不要仅因这个错误重新授权。只有重试后出现明确的 cookie 过期/无效提示，才按第 3 步重新导出。
14. **用户消息中的链接带 `[文字](URL)`、反斜杠或分享文案** → 由脚本自动规范化为纯平台 URL；若仍失败，检查命令参数中是否只剩一个完整 URL。

## 边界

- 一次处理一条链接；批量需求逐条串行执行并提醒反爬风险
- **反爬纪律（必须遵守）**：脚本已内置"失败等 30 秒只重试 1 次"。若仍失败，告知用户间隔几分钟后再试，**不要连续手动重跑**——短时间重复请求会被平台临时风控，越试越糟
- Cookie：`cookies.txt` 是用户在终端导出的授权快照。提取时脚本只读取它，并复制到临时工作目录；`yt-dlp` 对 Cookie 的刷新写回临时副本，不修改原始快照，也不会因为每次提取而要求重新授权
- 音频缓存：下载成功的音频按链接缓存在 `~/.config/video-transcript/cache/`，**pending 文件成功写入后自动清理**；只有下载、ASR 或 pending 写入失败时保留，供重试时命中缓存、不再请求平台。pending 文件不放入 Obsidian，成功完成最终笔记后由 Agent 单文件清理
- 纯自用工具，提取内容用于个人学习沉淀
- 视频本身不落盘；pending 文本会暂存在本机配置目录，最终 Markdown 笔记永久保存

## 隐私说明

- API Key 只保存在本机 `~/.config/video-transcript/.env`，不应粘贴到对话或提交到 Git
- 音频请求只发送到硅基流动 ASR；脚本不调用文本润色或摘要 API
- Cookie 快照和 pending 文件包含敏感的本地数据，按本机文件权限保护；Cookie 提取副本位于临时目录，流程结束后自动销毁；完成后应由 Agent 通过 `complete.py` 删除对应 pending 文件
