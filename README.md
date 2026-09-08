# Video-transcript-skill

抖音视频口播 / 小红书笔记（图文+视频）提取为完整文字，再由当前 AI Agent 整理为 Obsidian 笔记。

你的实际使用方式可以保持不变：手机复制抖音链接，发送给 Mac 端 Codex。Mac 端按需启动一个专用可见浏览器窗口，完成单条视频提取；不需要提前打开网页、不需要长期挂着网页、不需要手动保存视频，也不需要导出 Cookie。

## 工作原理

```text
手机端 Codex 传入单条抖音 URL
                |
                v
Mac Agent 按需启动专用可见 Chromium
                |
                v
独立持久化 Profile 打开抖音视频页
                |
                v
页面自行处理登录、动态参数和安全验证
                |
                v
捕获当前页面一个媒体源 -> 临时音频 -> SenseVoice ASR
                |
                v
~/.config/video-transcript/pending/<日期>-<标题>-<唯一后缀>.md
                |
                v
Agent 读取完整 pending -> 摘要/要点/标签/原文 -> Obsidian
                |
                v
验证最终文件非空 -> 删除对应 pending 文件
```

抖音默认不调用 `yt-dlp`、f2、抖音 Web API 或第三方在线解析服务，不读取或导出 `cookies.txt`。小红书分支继续使用 `yt-dlp`；本地视频继续使用 ffmpeg 和现有 ASR。

## 一键安装

复制这句话发给你的 AI Agent：

> **帮我安装这个 skill 并配置好：https://github.com/jolenliang/Video-transcript-skill**

安装时只需要在自己的终端录入一个硅基流动 API Key：

```bash
bash <skill目录>/scripts/setup.sh
bash <skill目录>/scripts/setup-keys.sh
```

`setup.sh` 会安装 Playwright、yt-dlp、imageio-ffmpeg，并安装 Chromium 运行时。它会准备专用 Profile：

```text
~/.config/video-transcript/browser-profile/
```

首次提取抖音链接时，专用可见浏览器会打开。请在这个窗口中手动登录一次，登录状态保存在独立 Profile；后续按需启动并复用。该窗口不是常驻服务，任务结束会关闭。

## 使用

抖音：

```text
手机复制链接 -> 发给 Mac 端 Codex -> 说“提取文案”
```

小红书或本地视频也可直接交给 Agent。脚本成功后输出：

```text
PENDING_FILE=/Users/your-name/.config/video-transcript/pending/2026-08-31-标题-abc123.md
```

Agent 必须读取该文件的完整内容，而不是依赖终端预览。默认最终笔记包含：

```markdown
## 摘要
...
## 要点
- 每条保留必要背景，建议 25-90 字，不超过 100 字
## 原文
按语义自然分段，删除 Unicode 表情但不改写事实
```

最终文件写入成功、存在且非空，并完成可读性自检后，Agent 才删除对应 pending。失败或中断时 pending 保留，重试直接读取它。

## 账号安全边界

- 单条、低频、用户主动触发。
- 使用独立可见浏览器 Profile，不连接日常 Chrome。
- 不导出或读取 Cookie，不调用 `Network.getAllCookies`。
- 不访问主页、不批量翻页、不点赞、关注、评论或发布。
- 不自动刷新，不连续撞请求。
- 不实现动态签名，不使用 f2，不接第三方解析。
- 页面遇到验证时由用户手动处理。
- 媒体在当前专用浏览器会话存活期间下载到任务临时目录，不永久保存抖音视频；代码不读取或导出 Cookie。

这会降低静态 Cookie 重放导致的请求不匹配风险，但不能承诺平台绝对不会触发验证或风控。

## 失败状态

抖音失败会区分：

```text
BROWSER_NOT_READY
BROWSER_LAUNCH_FAILED
BROWSER_PAGE_LOAD_FAILED
MANUAL_VERIFICATION_REQUIRED
BROWSER_PAGE_BLOCKED
BROWSER_MEDIA_NOT_FOUND
MEDIA_DOWNLOAD_FAILED
AUDIO_EXTRACTION_FAILED
ASR_FAILED
```

不再把失败统一提示为 `Fresh cookies are needed`，也不把重新导出 Cookie 作为默认修复方法。浏览器无法捕获媒体时，使用用户提供的本地视频作为兜底。

## Pending 文件生命周期

pending 固定在：

```text
~/.config/video-transcript/pending/
```

其中包含完整原文、平台、标题、作者、来源、日期和时长。抖音媒体不进入 URL 缓存，因为它依赖当前浏览器页面会话。Agent 成功写入 Obsidian 后只删除对应的一个 pending 文件，不批量清理。

## 系统要求

- macOS
- Python 3.9 或更高版本、git
- Obsidian，或任意本地笔记目录
- 首次抖音使用需要在专用可见浏览器窗口中登录

## 隐私

- 只需要硅基流动 API Key，保存在本机 `~/.config/video-transcript/.env`，权限 600。
- 抖音登录状态只保存在本机专用浏览器 Profile，不导出为 `cookies.txt`。
- 抖音音频由当前页面捕获后发送到硅基流动 SenseVoice 进行 ASR。
- 不调用文本生成 API；摘要、要点、标签和最终文件由当前 Agent 处理。
- 请自行确认内容使用权限。

## 手动安装

见 [INSTALL.md](INSTALL.md)。详细行为约束见 [SKILL.md](SKILL.md)。

## 设计 Spec

实现边界记录在 [抖音可见浏览器单条提取设计 Spec](docs/superpowers/specs/2026-09-08-douyin-browser-extraction-design.md)。

## License

MIT
