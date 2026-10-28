# Video-transcript Skill 维护项目

> 最后更新：2026-10-28
>
> 本文档同步维护于 [jolenliang/Video-transcript-skill](https://github.com/jolenliang/Video-transcript-skill) 的 `docs/PROJECT.md`，本地为同步副本；修改请以仓库那份为准。

## 一、项目背景

**Video-transcript** 是一个把抖音 / 小红书内容转成 Obsidian 笔记的本地 skill：抓取视频音频 → 硅基流动 SenseVoice 做 ASR → 生成带摘要、要点、原文的结构化 Markdown，写进 Obsidian vault。

这个 workspace 不是一个从零开发的项目，而是 **2026-10-21 一次故障排查延伸出来的维护工作**：

1. 提取「傻白呀」的 QQQ LEAP Call 视频时连续两次失败，报 `AUDIO_EXTRACTION_FAILED`
2. 定位到根因是抖音 DASH 分离流传导下的捕获时序 bug（详见第六节「已知坑」）
3. 修复后实测通过，把补丁推到 GitHub 开源仓库 `jolenliang/Video-transcript-skill`
4. 为「本地运行源」和「GitHub 发布源」双份结构配套了同步脚本 `vts-sync`

当前状态：修复已上线（远程 `main` 至 `d978856`），三份测试全绿（12 + 18 + 6 项），两份代码同步无差异。

## 二、四个位置的关系

| 位置 | 角色 | 权威内容 |
|---|---|---|
| `~/.codex/skills/video-transcript/` | **运行源**，Agent 实际调用 | 代码 + `SKILL.md` |
| `~/.workbuddy/skills/video-transcript` | 软链，指向运行源 | 无（勿在此建副本） |
| `~/Projects/Video-transcript-skill/` | **发布源**，git 仓库，推 GitHub | `README.md` / `INSTALL.md` / `docs/` |
| `~/.config/video-transcript/` | 运行时配置与状态 | API Key、vault 路径、浏览器 Profile |

`~` 本身是一个 git 仓库（remote 为 `jolenliang/learngit.git`），**不要在 `~/.codex` 下直接 commit**，改动会被混进 learngit 的错误分支。

## 三、文件结构

### 运行源 `~/.codex/skills/video-transcript/`

```text
├── SKILL.md                    7.9 KB   Agent 执行说明（工作流、边界、后处理要求）
├── README.md                   5.7 KB   面向人的使用文档
├── INSTALL.md                  5.7 KB   手动安装步骤
├── .gitignore                            排除 .venv / pending / cache / 媒体文件
├── docs/superpowers/
│   ├── plans/2026-09-08-douyin-browser-extraction.md
│   └── specs/2026-09-08-douyin-browser-extraction-design.md
├── scripts/
│   ├── extract.py            478 行    主流程：URL 路由 / ASR / pending 写入
│   ├── douyin_browser.py     474 行    抖音可见浏览器媒体捕获（Playwright）
│   ├── complete.py            40 行    校验最终笔记后清理 pending
│   ├── setup.sh                        装依赖 + 探测 Obsidian vault
│   ├── setup-keys.sh                   录入硅基流动 API Key（输入不回显）
│   └── setup-cookies.sh                旧版兼容工具，当前流程不用
├── tests/
│   ├── test_douyin_browser.py 334 行   媒体判定与捕获流程，12 项
│   ├── test_pending_flow.py   477 行   端到端流程与下载/转码，18 项
│   └── test_source_no_deepseek.py 49 行 源码约束检查，6 项
└── .venv/                              Python 3.12.14 虚拟环境（不进 git）
```

`extract.py` 负责编排：抖音走浏览器分支，小红书走 `yt-dlp`，本地文件走 ffmpeg。`douyin_browser.py` 只负责「打开页面、挑一条能出声的媒体流、在会话存活期内下载」。

### 发布源 `~/Projects/Video-transcript-skill/`

目录结构同上，额外带 `.git/`，文件名与运行源一致。差别只在权限位和 git 元数据。

### 配置与状态 `~/.config/video-transcript/`

```text
├── .env                 600   SILICONFLOW_API_KEY
├── config.json                {"vault_dir": ".../Reading/I-抖音文案"}
├── browser-profile/     700   抖音专用 Chromium Profile（含登录态，勿手改）
├── cache/                     小红书元数据与音频缓存
├── cookies.txt          600   旧版遗留，当前流程不读取
└── pending/                   等待 Agent 后处理的原文稿
```

### 本 workspace

```text
├── PROJECT.md                 本文档
├── outputs/                   交付给用户的成品副本
└── .workbuddy/memory/         跨会话工作记录
```

## 四、依赖情况

### 运行环境

| 项 | 版本 / 说明 |
|---|---|
| 操作系统 | macOS（脚本硬校验 `uname`，Windows 未适配） |
| Python | 3.9+ 即可，实测 3.12.14（`~/.codex/skills/video-transcript/.venv`） |
| ffmpeg | **由 `imageio-ffmpeg` 自带**（`ffmpeg-macos-aarch64-v7.1`），不依赖系统 ffmpeg |

### Python 包（`.venv`）

| 包 | 版本 | 用途 |
|---|---|---|
| `playwright` | 1.62.0 | 驱动可见 Chromium 抓抖音媒体流 |
| `greenlet` / `pyee` | 3.5.5 / 13.0.1 | Playwright 运行时依赖，无需直接调用 |
| `yt-dlp` | 2026.8.19 | 小红书图文 / 视频解析 |
| `imageio-ffmpeg` | 0.6.0 | 提供 ffmpeg 二进制，供抽音与转码 |

Chromium 运行时由 `playwright install chromium` 单独下载，装在 `~/Library/Caches/ms-playwright/`。

### 外部服务与工具

| 依赖 | 用途 | 凭据位置 |
|---|---|---|
| 硅基流动 SenseVoice API | 语音转文字 | `~/.config/video-transcript/.env`（600） |
| Obsidian（Vault: Reading） | 笔记落盘目标 | `config.json` 的 `vault_dir` |
| GitHub CLI 2.92.0 | 推送开源仓库 | `gh auth` 全局凭据 |
| `rsync` / `trash` | 同步脚本、安全删除 | 系统自带 |

## 五、常用操作

```bash
vts-sync -m "fix: 描述"     # 同步两份 + 跑测试 + 提交 + 推送
vts-sync -n                 # 干跑，只看会动什么
```

单条提取：

```bash
~/.codex/skills/video-transcript/.venv/bin/python \
  ~/.codex/skills/video-transcript/scripts/extract.py --url "<抖音或小红书链接>"
```

注意：`tests/` 目录没有 `__init__.py`，`unittest discover` 会报「not importable」，逐个文件跑即可（`vts-sync` 内部就是这么做的）。

## 六、已知坑

**1. 抖音 DASH 双流（2026-10-21 已修）**
画面和声音是两条独立流，音轨流的 `Content-Type` 同样是 `video/mp4`。原逻辑一捕到候选就退出等待，拿到的必然是无音轨画面流，ffmpeg 报 `Output file does not contain any stream`。现行逻辑：URL 语义优先判音轨 → 只有画面流时再等 12 秒 → 保留最多 3 个候选依次尝试。

**2. iCloud 目录受 TCC 保护**
WorkBuddy 进程对 `~/Library/Mobile Documents` 只有 `stat` 权限，`open` 读取会被拒。因此 `complete.py` 校验会失败、无法直接写 vault。可行通道是让 Obsidian 自己落盘：

```bash
open "obsidian://new?vault=Reading&file=<相对路径>&content=<URL 编码全文>"
```

写入后用 `stat` 比对字节数验证（本次 14,106 字节完全一致）。

**3. `rsync -a` 会污染 git 权限**
运行源里 `setup*.sh` 是 `700`，`-a` 会把权限推过去，git 记录成 mode change。同步脚本已改用 `-rlt -c`（只传内容、符号链接、时间戳）。

**4. 遗留文件**
`pending/` 里还躺着一份 2026-09-18 的未完成 pending（「自媒体人的skill盘点」），`cookies.txt` 是旧版遗留。两者都不影响当前流程，确认后可清理。

## 七、变更记录

**2026-10-28**
- 本文档纳入 GitHub 仓库 `docs/PROJECT.md`，由 `vts-sync` 与本地工作区保持一致

**2026-10-21**
- `be649e3` 修复 DASH 音轨捕获（4 文件，+173 / −34），新增 2 项回归测试
- `731019c` README 补充 DASH 说明与新的失败状态描述
- `d978856` 同步脚本首次运行，`setup*.sh` 权限归一为 755
- 新增 `vts-sync` 同步工具，建立运行源 ⇄ 发布源的双向维护流程
- 清理 `scripts.bak-20261021`、`tests.bak-20261021` 与顶层遗留 `extract.py`
