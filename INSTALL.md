# INSTALL.md - 给 AI Agent 的安装 SOP

> 这份文档是写给 AI Agent 执行的安装流程，不是给人读的教程。
> Agent 收到类似“帮我安装这个 skill：https://github.com/jolenliang/Video-transcript-skill”的请求时，按以下步骤执行。
> 用户只需手动录入一个 API Key，并在使用抖音链接时确认 Chrome 已登录。

## 系统要求（先检查）

- macOS（其他系统直接告知用户暂不支持并停止）
- Python 3.9 或更高版本（`command -v python3`）
- git
- 本机 Chrome 浏览器（用于读取抖音 cookie）
- 已安装 Obsidian，或用户提供一个本地目录

## Step 1：克隆到 Agent 对应的 skills 目录

按当前 Agent 类型选择目标目录：

| Agent | 安装目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/` |
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` |
| 其他/不确定 | `~/.codex/skills/`（默认） |

```bash
mkdir -p <skills目录>
git clone https://github.com/jolenliang/Video-transcript-skill.git <skills目录>/video-transcript
```

若目标目录已存在 `video-transcript`，先进入目录检查现有修改，再按用户要求更新；不要覆盖用户未确认的本地配置、Cookie、缓存或笔记。

## Step 2：安装依赖并探测 Obsidian

```bash
bash <skills目录>/video-transcript/scripts/setup.sh
```

脚本会创建 `.venv`，安装 `yt-dlp`、`imageio-ffmpeg` 和 `curl_cffi`，并输出检测到的 Obsidian vault 列表（JSON）。

## Step 3：让用户选择笔记存放目录

把 Step 2 输出的 vault 列表呈现给用户：

- 只有 1 个 vault：确认使用它，默认子目录 `<vault>/I-抖音文案`
- 多个 vault：让用户选一个
- 没有 Obsidian：让用户指定任意本地目录

然后写入配置：

```bash
bash <skills目录>/video-transcript/scripts/setup.sh "<用户选定的完整目录>"
```

抖音使用这里配置的 `vault_dir`；小红书自动使用其同级的 `I-小红书文案/`。

## Step 4：让用户录入硅基流动 API Key

**不要让用户在对话里粘贴 Key。** 让用户打开自己的终端运行：

```bash
bash <skills目录>/video-transcript/scripts/setup-keys.sh
```

只需要准备硅基流动 Key（[siliconflow.cn](https://siliconflow.cn)），用于 SenseVoice 语音转文字。脚本将只写入：

```text
SILICONFLOW_API_KEY=...
```

文件位置为 `~/.config/video-transcript/.env`，权限为 `600`。不要求、不保存其他文本生成服务的 Key。

## Step 5：Chrome 登录抖音并导出 cookie（一次性）

1. 提醒用户在 Chrome 打开 <https://www.douyin.com> 并扫码登录。
2. 让用户在自己的终端运行，不能由 Agent 代跑：

```bash
bash <skills目录>/video-transcript/scripts/setup-cookies.sh
```

Agent 沙箱可能拦截钥匙串写入，自动导出会得到不完整 cookie。导出过程中若弹出 Chrome Safe Storage 密码框，逐个点“始终允许”。脚本会写入 `~/.config/video-transcript/cookies.txt`（权限为 `600`）。提取脚本后续只读取这个授权快照，并在临时工作目录创建可写副本供 `yt-dlp` 使用，不会修改原始 Cookie 文件。只处理小红书或本地视频时可跳过此步。

## Step 6：运行提取与 Agent 后处理

链接：

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

提取成功标准是输出类似下面的绝对路径：

```text
PENDING_FILE=/Users/your-name/.config/video-transcript/pending/2026-08-31-标题-abc123.md
```

接下来 Agent 必须读取该文件的完整内容，生成包含“摘要 / 要点 / 标签 / 原文”的最终 Markdown，按平台写入配置的 Obsidian 目录，并确认最终文件存在且非空。后处理要求如下：长文生成 8-15 条要点，中等长度生成 6-12 条，短文生成 3-8 条；每条建议 25-90 字且不得超过 100 字；原文删除 Unicode 表情，并按语义和话题转换自然分段，通常每段 2-4 句，最长不超过约 600 字或 8 个句末标点，只能排版，不能改写、补充或删减事实。以上内容质量由 Agent 自行检查，`complete.py` 不负责语义质量判断，只确认最终文件存在且非空。确认成功后才执行：

```bash
<skills目录>/video-transcript/.venv/bin/python \
  <skills目录>/video-transcript/scripts/complete.py \
  --pending "<PENDING_FILE 的绝对路径>" \
  --final "<最终 Obsidian 文件的绝对路径>"
```

清理命令只删除这一个 pending 文件。Agent 中断、最终写入失败或验证失败时必须保留 pending，之后直接读取它重试，不要重新请求平台或重复 ASR。

## Step 7：故障处理与验证

- 缺少 `.env`、配置或虚拟环境：按 Step 2-4 补齐
- 抖音 cookie 缺失或失效：按 Step 5 重新导出；不要在对话里传 Cookie
- 小红书解析失败：确认链接完整，尤其是 App 复制的 `xsec_token` 参数；间隔几分钟后再试
- ASR 5xx：脚本会有限重试；持续失败时检查硅基流动额度和模型状态，失败期间音频缓存会保留
- `PermissionError: Operation not permitted` 且路径指向 `cookies.txt`：通常是旧安装副本让 `yt-dlp` 直接回写原始 Cookie；更新到当前版本后重试，不要仅因这个错误重复授权。只有明确提示 cookie 过期或无效时才按 Step 5 重新导出
- 用户分享内容带 Markdown 链接或附加文字：脚本会提取并规范化纯平台 URL；也可手动传入不带包装的 URL
- 平台解析持续失败：使用 App 保存本地视频，再走 `--file` 兜底
- pending 已存在：直接读取 pending 继续后处理，不重新提取
- 最终笔记写入失败或为空：保留 pending，修复路径或内容后重试
- Agent 自检发现最终笔记可读性不足：检查要点数量、单点是否超过 100 字、原文是否自然分段、单段是否过长以及是否仍有表情；修复后再重试，自检通过前不得调用清理脚本或删除 pending

安装完成后，验证以下项目：

1. `.env` 只有硅基流动 Key，权限为 `600`
2. 提取命令生成 `PENDING_FILE=` 且路径为绝对路径
3. pending 包含完整原文和 YAML 元数据
4. 最终笔记包含信息充分的要点、自然分段且无表情
5. 最终笔记写入成功且非空后，只有对应 pending 文件被删除

## 手动清理边界

pending 文件不是最终笔记。只删除已经确认不再需要的单个文件，避免使用 `rm ~/.config/video-transcript/pending/*` 之类的批量命令。音频缓存同理：下载、ASR 或 pending 写入失败时应保留，以便重试；提取流程成功写入 pending 后脚本会清理本次 URL 音频缓存。
