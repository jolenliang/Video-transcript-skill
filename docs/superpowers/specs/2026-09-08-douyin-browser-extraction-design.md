# 抖音可见浏览器单条提取设计 Spec

**状态：已确认，进入实施**

## 1. 背景

当前抖音链路使用 `yt-dlp + cookies.txt`。抖音网页在真实浏览器中可以正常访问，但脱离浏览器上下文的静态 Cookie 请求可能返回 `403 Forbidden` 和 `Fresh cookies are needed`。用户的实际工作流是从手机复制链接，发送给 Mac 端 Codex，由 Mac 端完成提取；用户低频、个人使用，真实抖音账号安全优先于极限自动化成功率。

## 2. 目标

将抖音默认提取链路改为：

```text
手机端 Codex 收到单条链接
    -> Mac 端 Agent 按需启动可见浏览器
    -> 使用独立持久化 Profile 打开抖音视频页
    -> 页面自行处理登录态、动态参数和验证
    -> 捕获当前页面产生的媒体源
    -> 本地提取音频并调用 SenseVoice ASR
    -> 写入 pending Markdown
    -> Agent 后处理并写入 Obsidian
```

用户无需提前打开网页、长期挂着抖音页面、手动保存视频或导出 `cookies.txt`。首次使用专用 Profile 时，用户在可见窗口中手动登录一次；后续任务复用该 Profile。

## 3. 安全边界

必须遵守：

- 一次只处理用户明确发送的一条抖音链接。
- 只启动和操作项目自己的专用可见浏览器，不连接用户日常 Chrome Profile。
- 专用 Profile 位于 `~/.config/video-transcript/browser-profile/`，不进入仓库。
- 不读取、导出、保存或打印 Cookie。
- 不调用 CDP `Network.getAllCookies`，不导出 storage state。
- 不调用抖音 Web API，不实现 `a_bogus`、`X-Bogus` 等签名。
- 不使用 f2、第三方在线解析 API 或抖音 `yt-dlp` Extractor。
- 不访问用户主页、不滚动翻页、不批量抓取、不点赞关注评论。
- 不自动刷新页面，不在失败后连续撞请求。
- 不记录带完整查询参数的媒体 URL，不保存 HAR、trace 或完整网络日志。
- CDP/浏览器仅绑定本机回环地址；任务结束后关闭浏览器和临时上下文。

这个方案降低静态 Cookie 重放和请求特征不匹配的风险，但不承诺平台绝对不会触发验证或风控。

## 4. 非目标

本次不实现：

- 抖音主页、合集、收藏夹和批量下载。
- 自动验证码识别或自动绕过安全验证。
- 抖音动态签名逆向和 API 后端。
- 第三方解析服务。
- 抖音视频永久保存。
- `complete.py` 的语义质量校验。

小红书图文、小红书视频和本地视频链路保持现有行为；小红书继续使用现有 `yt-dlp` 分支。

## 5. 组件和职责

### `scripts/douyin_browser.py`

浏览器后端，负责：

- 按需启动可见 Chromium/Chrome 浏览器。
- 使用独立持久化 Profile。
- 打开单条抖音 URL，并等待短链跳转。
- 识别页面安全验证状态，向 Agent 输出等待状态。
- 监听当前页面媒体响应，并读取页面 `video.currentSrc` 作为补充。
- 返回标题、作者、来源、时长、媒体 URL、媒体类型和最少必要请求头。
- 对媒体候选去重和排序，只选择一个候选。
- 任务结束关闭浏览器，不保留 Cookie 或网络日志。

### `scripts/extract.py`

主流程，负责：

- 抖音 URL 调用浏览器后端，不再调用 `yt-dlp` 抖音解析器。
- 接收浏览器后端返回的媒体源。
- 将媒体源写入系统临时任务目录；优先使用独立音频源，没有时用 ffmpeg 从视频源提取音频。
- 继续调用硅基流动 SenseVoice ASR。
- 继续生成完整 pending Markdown，并输出绝对 `PENDING_FILE`。
- 完成 pending 写入后清理本次临时媒体和音频。

### `scripts/setup.sh`

- 安装或检查 Python 依赖。
- 安装 Playwright Python 包和 Chromium 浏览器运行时。
- 创建专用 Profile 目录并设置用户私有权限。
- 保留 `yt-dlp` 供小红书分支使用。
- 不再把 Cookie 导出或 `curl_cffi` 作为抖音必需步骤。

### `scripts/setup-cookies.sh`

保留为历史兼容文件，但不再出现在抖音默认安装、前置检查或失败处理流程中。实现完成后若无代码引用，可在文档中标记为旧版遗留，不主动读取或执行。

## 6. 浏览器生命周期

每次抖音任务：

1. 创建随机临时任务目录。
2. 检查专用 Profile 目录存在且权限为用户私有。
3. 启动可见持久化浏览器上下文。
4. 打开用户提供的单条链接。
5. 等待页面最多 60 秒；检测验证状态最多 120 秒。
6. 捕获媒体源，或在媒体捕获总时限 180 秒内等待页面视频元素出现。
7. 关闭页面和浏览器。
8. 将单个媒体源交给音频处理流程。

浏览器不作为常驻服务。任务完成或失败后都关闭本次启动的浏览器。若页面需要手动验证，浏览器保持可见，用户完成验证后当前任务继续，不重新导航。

## 7. 媒体捕获

媒体源选择顺序：

1. 当前页面响应中来自 `*.douyinvod.com` 或 `*.ixigua.com` 的直接音频源。
2. 当前页面响应中来自上述域名的直接视频源。
3. `video.currentSrc`。
4. `<video><source>` 的直接媒体地址。
5. 清单地址仅在 ffmpeg 能直接读取时尝试。

忽略封面、头像、缩略图、字体、样式和普通 JSON。`blob:` 地址不能单独作为最终媒体源；必须同时捕获其底层媒体请求，否则返回 `BROWSER_MEDIA_NOT_FOUND`。

媒体候选必须满足以下之一：响应 `Content-Type` 是音频/视频，或 URL/资源信息明确表明是媒体。只选择一个候选，不并发下载多个候选，不为了寻找候选刷新页面。

媒体 URL 只在当前进程和临时文件中短暂存在；普通日志只记录域名、媒体类型和脱敏路径，不记录查询参数。

## 8. 媒体下载和音频提取

优先直接下载独立音频源；只有没有独立音频源时，才下载临时视频并执行：

```bash
ffmpeg -i <临时视频> -vn -c:a copy <临时音频>
```

若复制音轨失败，再使用 MP3 编码回退。完整视频不进入永久目录，任务结束删除。媒体优先在仍存活的 Playwright 专用浏览器上下文中下载，以复用当前页面会话；不得由代码读取、拼接或导出 Cookie。浏览器上下文下载只额外设置 `Referer: https://www.douyin.com/`，若因测试替身或兼容场景必须在浏览器外下载，也只允许使用页面返回的 User-Agent 和该 Referer，不得添加 Cookie。

抖音媒体不写入现有 URL 音频缓存，因为媒体 URL 依赖页面会话且不适合跨任务复用。ASR 失败时不重新打开抖音页面；当前进程内已经捕获的本地音频可用于有限重试。

## 9. 状态和错误

浏览器后端输出机器可识别状态：

```text
BROWSER_STATUS=READY
BROWSER_STATUS=MANUAL_VERIFICATION_REQUIRED
BROWSER_STATUS=PAGE_BLOCKED
BROWSER_STATUS=BROWSER_NOT_READY
BROWSER_STATUS=BROWSER_LAUNCH_FAILED
BROWSER_STATUS=BROWSER_PAGE_LOAD_FAILED
BROWSER_STATUS=BROWSER_MEDIA_NOT_FOUND
```

主流程补充：

```text
MEDIA_DOWNLOAD_FAILED
AUDIO_EXTRACTION_FAILED
ASR_FAILED
PENDING_WRITE_FAILED
```

不再把抖音失败统一报告为 `Fresh cookies are needed`，也不自动触发 `setup-cookies.sh`、f2 或 `yt-dlp` 重试。错误消息必须说明失败阶段、是否需要用户操作、是否会再次访问抖音以及是否保留 pending。

## 10. 与现有 pending/Agent 流程的接口

浏览器提取成功后，`extract.py` 继续写入：

```text
~/.config/video-transcript/pending/<日期>-<标题>-<稳定后缀>.md
```

pending 必须包含完整原文和现有 YAML 元数据。Agent 继续负责摘要、要点、标签、原文排版、Obsidian 写入和可读性自检。最终文件存在且非空后，才调用 `complete.py` 删除本次对应的单个 pending 文件。

## 11. 测试策略

所有自动化测试使用 mock，不访问抖音、不使用真实 Cookie、不调用真实 ASR：

- 模拟页面响应，验证音频源优先、视频源回退、封面过滤和候选去重。
- 验证验证页面状态、页面无媒体状态和浏览器启动失败状态。
- 验证媒体 URL 脱敏日志不含查询参数。
- 验证专用 Profile 路径和临时结果文件权限。
- 验证抖音分支不调用 `yt_dlp`、不检查 `cookies.txt`、不触发 Cookie 导出。
- 验证小红书分支仍调用原有 `yt_dlp` 路径。
- 验证本地文件、ASR、pending 和清理流程不回归。
- 运行 Python 语法检查、单元测试和本地 mock 冒烟测试。

## 12. 验收标准

1. 不存在 `cookies.txt` 时，抖音 URL 仍能进入浏览器流程。
2. 首次运行按需打开可见专用浏览器，用户可手动登录。
3. 后续运行复用专用 Profile，不要求每次登录。
4. 平时不需要长期运行浏览器；任务结束自动退出。
5. 不需要提前打开抖音网页，不需要手动保存视频。
6. 只处理单条链接，不访问主页或批量翻页。
7. 不读取或导出日常 Chrome Cookie。
8. 验证页面可由用户手动完成，超时后停止而不是连续重试。
9. 抖音代码不调用 `yt-dlp`、f2 或第三方解析 API。
10. 成功后生成包含完整文案的 pending Markdown 和绝对路径。
11. Agent 后处理和单文件 pending 清理规则保持不变。
12. 小红书和本地视频功能不回归。
13. 测试和语法检查通过，提交内容不包含密钥、Cookie、浏览器 Profile、媒体、缓存、pending 或个人笔记。

## 13. 风险说明

可见浏览器页面捕获比静态 Cookie 重放更接近用户正常访问，但仍属于自动化控制，不能承诺平台零风险。若抖音页面改为无法直接捕获的 MSE/分片形态，系统应明确失败并停止，不为了提高成功率引入动态签名、Cookie 重放、批量抓取或第三方解析。
