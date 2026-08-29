# INSTALL.md — 给 AI Agent 的安装 SOP

> 这份文档是写给 AI Agent 执行的安装流程，不是给人读的教程。
> Agent 收到类似「帮我安装这个 skill：https://github.com/Jolen/Video-transcript-skill」的请求时，按以下步骤执行。
> 全程只需用户做 2 件手动事：① 在自己终端录入 API Key；② 确认 Chrome 已登录 douyin.com。

## 系统要求（先检查）

- macOS（其他系统直接告知用户暂不支持并停止）
- python3 >= 3.9（`command -v python3`）
- git
- 本机 Chrome 浏览器（用于读取抖音 cookie）

## Step 1：克隆到 Agent 对应的 skills 目录

按当前 Agent 类型选择目标目录（以下任一，存在哪个用哪个；都不存在则用 WorkBuddy 路径并创建）：

| Agent | 安装目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/` |
| Claude Code | `~/.claude/skills/` |
| 其他/不确定 | `~/.workbuddy/skills/` |

```bash
mkdir -p <skills目录>
git clone https://github.com/Jolen/Video-transcript-skill.git <skills目录>/video-transcript
```

若目标目录已存在 `video-transcript`，改为 `cd` 进去 `git pull` 更新。

## Step 2：安装依赖 + 探测 Obsidian

```bash
bash <skills目录>/video-transcript/scripts/setup.sh
```

脚本会：创建 `.venv`、安装 yt-dlp + imageio-ffmpeg、输出检测到的 Obsidian vault 列表（JSON）。

## Step 3：让用户选择笔记存放目录

把 Step 2 输出的 vault 列表呈现给用户：

- 只有 1 个 vault → 向用户确认使用它，默认子目录 `I-抖音文案`
- 多个 vault → 让用户选一个
- 没有 Obsidian → 让用户指定任意本地目录

然后写入配置：

```bash
bash <skills目录>/video-transcript/scripts/setup.sh "<用户选定的vault路径>/I-抖音文案"
```

## Step 4：引导用户录入 API Key（关键安全步骤）

**不要让用户在对话里粘贴 Key。** 让用户打开自己的终端，运行：

```bash
bash <skills目录>/video-transcript/scripts/setup-keys.sh
```

用户需要提前准备好两个 Key（脚本运行时也会提示获取网址）：
- 硅基流动（siliconflow.cn，免费，语音转文字用）
- DeepSeek（platform.deepseek.com，摘要加工用）

用户看到 `✅ 已写入` 后继续。

## Step 5：确认 Chrome 登录抖音

提醒用户：在 Chrome 打开 https://www.douyin.com 并扫码登录（yt-dlp 需要读取 cookie 才能解析链接，数月过期一次，过期重登即可）。

## Step 6：冒烟测试

请用户粘贴一条真实抖音分享链接，执行（约 30-90 秒）：

```bash
<skills目录>/video-transcript/.venv/bin/python \
  <skills目录>/video-transcript/scripts/extract.py \
  --url "<用户提供的链接>"
```

**首次运行时 macOS 会弹出钥匙串密码框**（"python 想要使用 Chrome Safe Storage"）——这是 yt-dlp 解密 Chrome cookie 的正常环节，密码只输给系统、不经过任何第三方。提前告知用户，并建议点「**始终允许**」（点"允许"则每次运行都会再问一遍；换了 python 环境也会重新问一次）。

成功标准：生成 Markdown 文件到用户选定的目录，输出摘要/要点/标签。

若失败，按 SKILL.md 的「故障处理」顺序排查。

## Step 7：告知用户使用方式

安装完成后，用户以后只需在对话里粘贴抖音链接说「提取文案」即可触发。告诉用户：

- 笔记位置：Step 3 选定的目录
- Key 位置：`~/.config/video-transcript/.env`（本机 600 权限，可随时重跑 setup-keys.sh 更换）
- 解析失败兜底：抖音 App 保存视频 → 直接拖给 Agent
