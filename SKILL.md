---
name: video-transcript
description: 提取文案、提取抖音视频口播文案、小红书笔记正文（图文+视频），交给当前 Agent 生成 Obsidian Markdown 笔记。当用户粘贴抖音/douyin.com 链接（v.douyin.com 短链）或小红书链接（xhslink.cn 短链、xiaohongshu.com）并要求提取文案/转文字/逐字稿/字幕/正文时触发；也支持本地视频文件转文字。触发词示例：”提取文案”、"提取这条抖音的文案"、"存一下这篇小红书"、"视频转文字"、"口播稿整理"。仅限 macOS。
---

# Video-transcript · 抖音/小红书文案提取

本 skill 将“提取”和“理解写作”分开：脚本获取完整文本和元数据，当前 Agent 负责摘要、要点、标签、排版及最终 Obsidian 文件。

## 平台流程

- 抖音单条链接：按需启动专用可见 Playwright Chromium，使用独立持久化 Profile 打开链接，捕获当前页面的媒体源（DASH 下画面与音轨是两条流，优先取独立音轨流；只捕到视频流时额外等 12 秒等音轨），提取音频后调用硅基流动 SenseVoice ASR。最多保留 3 个候选媒体，抽音失败时依次换下一个。
- 小红书图文：使用 `yt-dlp` 读取正文，不需要抖音浏览器 Profile。
- 小红书视频：使用现有 `yt-dlp` 音频流程，再调用 SenseVoice ASR。
- 本地视频：使用 ffmpeg 提取音频，再调用 SenseVoice ASR。

抖音流程不调用 `yt-dlp`、f2、抖音 Web API 或第三方解析服务，也不读取或导出 `cookies.txt`，不需要导出 Cookie。抖音浏览器按任务启动，任务结束关闭，不需要提前打开或长期挂着抖音网页。

约定：`SKILL_DIR` = 本 SKILL.md 所在目录。

## 抖音账号安全边界

必须遵守：

- 一次只处理用户明确发送的一条链接。
- 使用 `~/.config/video-transcript/browser-profile/` 这个独立 Profile，不连接用户日常 Chrome。
- 首次使用时在弹出的可见窗口中手动登录；后续任务复用该 Profile。
- 不读取、导出、保存或打印 Cookie，不调用 CDP `Network.getAllCookies`，不导出 storage state。
- 不访问抖音主页、不滚动翻页、不批量抓取、不点赞、关注、评论或发布内容。
- 页面遇到验证码或安全验证时等待用户手动处理，不自动刷新，不连续重试。
- 只捕获当前页面的一个音频或视频媒体源；媒体 URL 不进入日志、pending 或最终笔记。
- 浏览器只绑定本机进程，任务结束关闭页面和浏览器。

这个边界降低了静态 Cookie 重放和脱离浏览器请求的风险，但不能承诺平台绝对不会触发验证或风控。

## 执行

### 前置检查

每次执行前确认：

1. `~/.config/video-transcript/.env` 存在且包含 `SILICONFLOW_API_KEY`。
2. `~/.config/video-transcript/config.json` 存在且包含 Obsidian 目录。
3. `SKILL_DIR/.venv/bin/python` 存在。
4. `SKILL_DIR/.venv` 中可导入 Playwright；仅小红书分支需要 `yt-dlp`。

### 抖音链接

从用户消息中提取纯 URL；支持 Markdown 链接、反斜杠转义和分享附加文字：

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/extract.py --url "<链接>"
```

脚本会按需启动专用可见浏览器。若窗口中出现登录或安全验证，提醒用户在该窗口手动完成；不要重新运行命令，不要重新导出 Cookie。

成功后脚本输出：

```text
PENDING_FILE=/Users/your-name/.config/video-transcript/pending/2026-08-31-标题-abc123.md
```

### 小红书和本地视频

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/extract.py --url "<小红书链接>"
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/extract.py --file "<视频文件绝对路径>"
```

## Pending 与 Agent 后处理

提取脚本只在 `~/.config/video-transcript/pending/` 写入带 YAML 元数据的完整原文，不直接写最终笔记。Agent 必须读取 `PENDING_FILE` 的完整内容，不能依赖终端预览。

默认最终结构：

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

### 后处理质量要求

- 摘要写清主题、核心结论和关键背景，不只复述标题。
- 原文超过 1600 字生成 8-15 条要点，800-1600 字生成 6-12 条，800 字以内生成 3-8 条。
- 每条要点建议 25-90 字，硬上限 100 字；每条包含结论和必要背景或影响，不写空泛标签。
- 原文保留事实和顺序，只删除 Unicode 表情并做排版；按话题转换、问答转换和完整句群自然分段，通常每段 2-4 句，最长约 600 字或 8 个句末标点。
- Agent 写入后自行检查要点数量、单点长度、原文段落和表情；检查失败时修订，不删除 pending。

Agent 按以下顺序完成：

1. 读取并解析 pending 的完整元数据和原文。
2. 生成摘要、要点、标签和保真的原文排版，写入对应 Obsidian 目录。
3. 确认最终文件存在且非空，并完成上述可读性自检。
4. 仅在确认成功后执行：

```bash
SKILL_DIR/.venv/bin/python SKILL_DIR/scripts/complete.py \
  --pending "<PENDING_FILE>" \
  --final "<最终 Obsidian 文件绝对路径>"
```

`complete.py` 只确认最终文件存在且非空，然后删除指定的一个 pending 文件，不判断语义质量。Agent 中断、写入失败或自检失败时必须保留 pending；重试时直接读取 pending，不重新访问平台、不重新执行 ASR。

当用户要求改善已经保存的 Obsidian 笔记时，直接读取和修改本地 Markdown，不重新访问抖音或小红书，不下载视频，不重复执行 ASR。

## 故障处理

- 缺少 `.env`、`config.json`、虚拟环境或 Playwright：引导用户在自己的终端运行 `bash SKILL_DIR/scripts/setup.sh`。
- `BROWSER_NOT_READY` 或 `BROWSER_LAUNCH_FAILED`：检查 Playwright Chromium 是否安装、专用 Profile 是否可写；不要读取日常 Chrome Cookie。
- `MANUAL_VERIFICATION_REQUIRED`：保持当前可见窗口，等待用户手动验证；不要刷新或重跑。
- `BROWSER_PAGE_BLOCKED`：本次停止，不自动连续重试；稍后由用户重新发起一次任务。
- `BROWSER_MEDIA_NOT_FOUND`：说明页面未捕获到可用媒体源；不要回退到 yt-dlp、f2、Cookie 导出或第三方解析，可使用本地视频兜底。
- `MEDIA_DOWNLOAD_FAILED` 或 `AUDIO_EXTRACTION_FAILED`：本次停止，不重新打开抖音页面。
- ASR 5xx：只对已捕获的本地音频按现有有限重试处理，不再次访问抖音。
- 小红书解析失败：确认 App 复制的链接完整，尤其是 `xsec_token`；小红书仍可使用现有 yt-dlp 分支。
- `PENDING_FILE` 已存在：直接读取并继续 Agent 后处理，不重新提取。

不要把抖音失败统一解释成 `Fresh cookies are needed`，也不要把 `setup-cookies.sh` 作为当前版本的默认恢复方案。该脚本只是旧版兼容工具。

## 目录与隐私

- 抖音最终笔记使用配置的 `vault_dir`；小红书使用同级 `I-小红书文案/`。
- 专用浏览器 Profile：`~/.config/video-transcript/browser-profile/`，只供该 skill 使用。
- pending：`~/.config/video-transcript/pending/`，成功后由 Agent 删除对应单文件。
- API Key：`~/.config/video-transcript/.env`，权限 600。
- 抖音媒体在专用浏览器会话存活期间下载到任务临时目录，不永久保存视频；代码不读取或导出 Cookie，音频仅用于 ASR。
- 音频发送到硅基流动 SenseVoice API；脚本不调用文本摘要或润色 API。
- 不提交密钥、Cookie、浏览器 Profile、缓存、pending、媒体或个人笔记。

## 兜底

如果用户明确提供本地视频，直接使用 `--file`。这不是抖音默认流程，只是浏览器页面无法捕获媒体时的保守兜底。
