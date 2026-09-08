# INSTALL.md - 给 AI Agent 的安装 SOP

> 这份文档写给执行安装的 AI Agent。用户的实际操作是从手机复制抖音链接，发送给 Mac 端 Codex；Mac 端按需启动专用可见浏览器完成单条提取。

## 系统要求

- macOS
- Python 3.9 或更高版本
- git
- 已安装 Obsidian，或用户提供一个本地目录

抖音不要求日常 Chrome 已开启调试端口，不需要导出 `cookies.txt`。本项目会使用自己的 Playwright Chromium 和独立 Profile。

## Step 1：安装到 skills 目录

按当前 Agent 类型选择目标目录：

| Agent | 安装目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/` |
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` |
| 其他/不确定 | `~/.codex/skills/` |

```bash
mkdir -p <skills目录>
git clone https://github.com/jolenliang/Video-transcript-skill.git <skills目录>/video-transcript
```

若目标目录已存在，先检查现有修改；不要覆盖用户的 API Key、专用浏览器 Profile、pending、缓存或 Obsidian 笔记。

## Step 2：安装依赖和浏览器

```bash
bash <skills目录>/video-transcript/scripts/setup.sh
```

脚本会检查 macOS 和 Python，创建 `.venv`，安装 Playwright、yt-dlp、imageio-ffmpeg，安装 Playwright Chromium 运行时，并创建权限为 700 的：

```text
~/.config/video-transcript/browser-profile/
```

其中 yt-dlp 只供小红书分支使用，不是抖音默认后端。

## Step 3：配置笔记目录

把 `setup.sh` 输出的 vault 列表呈现给用户：只有 1 个 vault 时确认使用它，多于 1 个时让用户选择，没有 Obsidian 时让用户指定任意本地目录。然后执行：

```bash
bash <skills目录>/video-transcript/scripts/setup.sh "<用户选定的完整目录>"
```

抖音使用这里配置的目录；小红书自动使用同级的 `I-小红书文案/`。

## Step 4：配置硅基流动 Key

不要让用户在对话中粘贴 Key。让用户在自己的终端运行：

```bash
bash <skills目录>/video-transcript/scripts/setup-keys.sh
```

只需要硅基流动 Key，用于 SenseVoice 语音转文字。文件位置为 `~/.config/video-transcript/.env`，权限为 600，内容只有：

```text
SILICONFLOW_API_KEY=...
```

## Step 5：首次使用抖音专用浏览器

不运行 `setup-cookies.sh`，不导出日常 Chrome Cookie。

首次处理抖音链接时，Agent 会按需打开可见 Playwright Chromium，并复用独立 Profile。请在弹出的窗口中手动登录一次抖音。任务成功或失败后浏览器关闭，平时不需要挂着网页。

## Step 6：执行提取

用户可以在手机复制抖音链接，直接发送给 Mac 端 Codex 并说“提取文案”。Agent 执行：

```bash
<skills目录>/video-transcript/.venv/bin/python \
  <skills目录>/video-transcript/scripts/extract.py \
  --url "<用户提供的链接>"
```

本地视频：

```bash
<skills目录>/video-transcript/.venv/bin/python \
  <skills目录>/video-transcript/scripts/extract.py \
  --file "<视频文件绝对路径>"
```

抖音流程只打开用户指定的单条链接，不访问主页、不批量翻页、不读取 Cookie、不调用抖音 Web API、f2、第三方解析或 yt-dlp 抖音 Extractor。如页面要求验证，保持当前窗口打开，用户手动完成后当前任务继续；不要刷新或重复运行命令。

成功标准：

```text
PENDING_FILE=/Users/your-name/.config/video-transcript/pending/2026-08-31-标题-abc123.md
```

## Step 7：Agent 后处理和清理

Agent 必须读取 `PENDING_FILE` 的完整内容，生成包含“摘要 / 要点 / 标签 / 原文”的 Markdown，写入对应 Obsidian 目录，并自行检查：长文 8-15 条、中等长度 6-12 条、短文 3-8 条；每条要点建议 25-90 字且不超过 100 字；原文删除 Unicode 表情并按话题转换自然分段，不改写、补充或删减事实。

确认最终文件存在且非空后执行：

```bash
<skills目录>/video-transcript/.venv/bin/python \
  <skills目录>/video-transcript/scripts/complete.py \
  --pending "<PENDING_FILE 的绝对路径>" \
  --final "<最终 Obsidian 文件的绝对路径>"
```

`complete.py` 只删除指定的单个 pending 文件并检查最终文件非空，不判断语义质量。Agent 中断、写入失败或自检失败时必须保留 pending，之后直接读取它重试，不重新访问平台或重复 ASR。

## 故障处理

- 缺少 `.env`、配置、虚拟环境或 Playwright：重新运行 Step 2-4；
- `BROWSER_LAUNCH_FAILED`：检查 Playwright Chromium 安装和专用 Profile 权限；
- `MANUAL_VERIFICATION_REQUIRED`：在可见窗口中手动完成验证，不刷新、不重跑；
- `BROWSER_PAGE_BLOCKED`：本次停止，稍后重新发起一次；
- `BROWSER_MEDIA_NOT_FOUND`：不要回退到 Cookie、yt-dlp、f2 或第三方解析，使用本地视频兜底；
- `MEDIA_DOWNLOAD_FAILED` 或 `AUDIO_EXTRACTION_FAILED`：不重新打开抖音页面；
- ASR 临时 5xx：只重试已捕获的本地音频，不再次访问抖音；
- 小红书解析失败：确认链接完整，尤其是 `xsec_token`，间隔后再试；
- pending 已存在：直接读取 pending 继续后处理；
- 最终文件写入失败或为空：保留 pending，修复路径后重试。

不要把抖音失败统一解释为 `Fresh cookies are needed`。`setup-cookies.sh` 是旧版兼容工具，不是当前版本默认步骤。

## 安全检查

提交或同步 GitHub 前确认：

```bash
git status --short
git ls-files | rg '(^|/)(\.env|cookies\.txt|browser-profile|cache|pending|\.venv)(/|$)' || true
```

不得提交 API Key、Cookie、浏览器 Profile、媒体、缓存、pending 或个人 Obsidian 笔记。
