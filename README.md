# Video-transcript-skill

抖音视频口播 / 小红书笔记（图文+视频）提取为完整文字，再由当前 AI Agent 整理为 Obsidian 笔记。

粘贴抖音或小红书分享链接给你的 AI Agent，或提供本地视频文件。脚本负责解析、下载音频和语音转文字；Agent 负责摘要、要点、标签、排版和最终文件写入。默认笔记存入 Obsidian 的 `I-抖音文案/` 或 `I-小红书文案/`。小红书图文无需 cookie、秒级完成。

## 一键安装

复制这句话发给你的 AI Agent：

> **帮我安装这个 skill 并配置好：https://github.com/jolenliang/Video-transcript-skill**

你只需要在自己的终端完成两项操作：

1. 运行 `scripts/setup-keys.sh`，录入一个硅基流动 API Key。输入不会回显，Key 只保存在本机。
2. 使用抖音链接时，在 Chrome 登录 [douyin.com](https://www.douyin.com)，再运行 `scripts/setup-cookies.sh` 导出 cookie。只提取小红书或处理本地视频时可跳过。

安装完成后，粘贴链接并说“提取文案”即可。若平台解析失败，可在抖音 App 保存视频后直接把本地视频交给 Agent。

## 工作原理

```text
抖音链接   -> yt-dlp 下载音频（Chrome cookie）-> 硅基流动 SenseVoice ASR
小红书图文 -> yt-dlp 读取元数据和正文（匿名即可）
小红书视频 -> yt-dlp 下载音频 -> 硅基流动 SenseVoice ASR
本地视频   -> ffmpeg 提取音频 -> 硅基流动 SenseVoice ASR
                                      |
                                      v
                ~/.config/video-transcript/pending/<日期>-<标题>-<唯一后缀>.md
                                      |
                                      v
             Agent 读取完整 pending -> 生成摘要/要点/标签/原文 -> Obsidian
                                      |
                                      v
                         验证最终文件非空 -> 删除对应 pending 文件
```

脚本不调用文本生成 API，也不直接写入最终 Obsidian 笔记。唯一需要配置的 API Key 是硅基流动 Key，用于 SenseVoice 语音转文字。抖音 Cookie 文件只作为本地授权快照读取；脚本会复制到临时目录供 `yt-dlp` 使用，避免 Agent 沙箱因阻止 Cookie 文件回写而误报需要重新授权。

## Pending 文件

待处理文件固定在：

```text
~/.config/video-transcript/pending/
```

文件是带 YAML 元数据的 Markdown，包含 `type: video-transcript-pending`、`status: pending`、平台、标题、作者、来源、提取日期、时长，以及 `## 原始文案` 下的完整提取文本。原文不会按 20,000 字符截断。

脚本成功后会输出机器可识别的绝对路径：

```text
PENDING_FILE=/Users/your-name/.config/video-transcript/pending/2026-08-31-标题-abc123.md
```

Agent 必须读取这个文件的完整内容，而不是依赖终端预览。默认最终笔记结构为：

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

Agent 写入最终文件并确认文件存在且非空后，执行：

```bash
<skill目录>/.venv/bin/python <skill目录>/scripts/complete.py \
  --pending "<PENDING_FILE>" \
  --final "<最终 Obsidian 文件绝对路径>"
```

清理脚本只删除指定的一个 pending 文件。Agent 中断、写入失败或验证失败时，pending 文件必须保留；重试时直接读取它，不重新请求平台或重复 ASR。手动清理只应针对已经确认不再需要的单个文件，不要用通配符批量删除待处理内容。

## 目录路由

- 抖音：使用安装时配置的 `vault_dir`，默认建议为 `<vault>/I-抖音文案/`
- 小红书：使用配置目录的同级 `<vault>/I-小红书文案/`

音频按来源链接缓存到 `~/.config/video-transcript/cache/`。pending 文件成功写入后，脚本清理本次音频缓存；下载、ASR 或 pending 写入失败时保留缓存，以便重试命中并减少平台请求。视频本身不永久落盘。

如果看到 `PermissionError: Operation not permitted` 并且错误路径指向 `~/.config/video-transcript/cookies.txt`，先确认使用的是最新安装副本并重试。这通常是旧版本把原始 Cookie 文件直接交给 `yt-dlp`，而沙箱禁止其写回；新版本会使用临时 Cookie 副本。只有出现明确的 cookie 过期或无效提示时，才需要在用户自己的终端重新运行 `scripts/setup-cookies.sh`。分享文案中的 Markdown 链接、反斜杠转义和附加文字由脚本自动规范化。

## 系统要求

- macOS（Windows 适配计划中）
- Python 3.9 或更高版本、git、Chrome
- 已安装并配置 Obsidian，或提供任意本地目录作为笔记目录

## 隐私与安全

- 只需一个硅基流动 API Key，保存在 `~/.config/video-transcript/.env`，权限为 `600`，不会进入对话记录或 Git
- 抖音 cookie 保存在 `~/.config/video-transcript/cookies.txt`，权限为 `600`，不要提交到仓库
- 脚本向硅基流动发送音频进行 ASR；pending 文件包含完整原文和来源元数据，暂存在本机配置目录
- 纯自用工具，提取内容用于个人学习沉淀；请自行确认内容使用权限

## 手动安装

见 [INSTALL.md](INSTALL.md)，按安装 SOP 执行。

## License

MIT
