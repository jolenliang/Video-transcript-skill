# 抖音可见浏览器单条提取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将抖音提取从静态 Cookie + yt-dlp 改为按需启动独立可见 Playwright 浏览器、捕获当前单条视频媒体源，再沿用现有 ASR、pending 和 Agent 后处理流程。

**Architecture:** 新增 `scripts/douyin_browser.py`，用 Playwright 的持久化上下文启动独立可见 Chromium Profile，监听当前页面的抖音 CDN 音视频响应并返回一个脱敏前只在进程内流转的媒体结果。`extract.py` 只在抖音分支调用该后端，使用 `urllib` 下载捕获的单个媒体源或使用 ffmpeg 提取音频；小红书和本地视频保持现有链路。浏览器失败不回退到 yt-dlp、f2、Cookie 导出或第三方解析。

**Tech Stack:** Python 3.9+, Playwright Python API, imageio-ffmpeg, ffmpeg, SiliconFlow SenseVoiceSmall, unittest mock。

---

### Task 1: 固化浏览器后端的可测试接口

**Files:**
- Create: `scripts/douyin_browser.py`
- Test: `tests/test_douyin_browser.py`

- [x] **Step 1: Write failing tests for media selection and status mapping**

在 `tests/test_douyin_browser.py` 中测试以下公开接口：

```python
def test_select_media_prefers_audio_and_ignores_cover():
    candidates = [
        {"url": "https://p.douyinvod.com/cover.jpg", "kind": "image", "content_type": "image/jpeg"},
        {"url": "https://p.douyinvod.com/video.mp4?token=secret", "kind": "video", "content_type": "video/mp4"},
        {"url": "https://p.douyinvod.com/audio.m4a?token=secret", "kind": "audio", "content_type": "audio/mp4"},
    ]
    result = select_media_candidate(candidates)
    assert result["kind"] == "audio"
    assert result["url"].endswith("audio.m4a?token=secret")

def test_select_media_falls_back_to_video():
    result = select_media_candidate([
        {"url": "https://p.douyinvod.com/poster.jpg", "kind": "image", "content_type": "image/jpeg"},
        {"url": "https://p.douyinvod.com/video.mp4", "kind": "video", "content_type": "video/mp4"},
    ])
    assert result["kind"] == "video"

def test_sanitize_url_for_log_removes_query():
    assert sanitize_url_for_log("https://p.douyinvod.com/video.mp4?token=secret") == "https://p.douyinvod.com/video.mp4"

def test_detect_page_status():
    assert detect_page_status("请完成安全验证") == "MANUAL_VERIFICATION_REQUIRED"
    assert detect_page_status("Please wait while we verify") == "MANUAL_VERIFICATION_REQUIRED"
    assert detect_page_status("视频标题\n作者") is None
```

运行：

```bash
python3 -m unittest tests.test_douyin_browser -v
```

预期：FAIL，因为 `scripts/douyin_browser.py` 尚未存在。

- [x] **Step 2: Implement the minimal pure helpers**

实现以下公开常量和函数：

```python
DOUYIN_MEDIA_HOSTS = ("douyinvod.com", "ixigua.com")
MEDIA_STATUS_READY = "READY"
MEDIA_STATUS_MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
MEDIA_STATUS_PAGE_BLOCKED = "PAGE_BLOCKED"
MEDIA_STATUS_BROWSER_NOT_READY = "BROWSER_NOT_READY"
MEDIA_STATUS_BROWSER_LAUNCH_FAILED = "BROWSER_LAUNCH_FAILED"
MEDIA_STATUS_BROWSER_PAGE_LOAD_FAILED = "BROWSER_PAGE_LOAD_FAILED"
MEDIA_STATUS_BROWSER_MEDIA_NOT_FOUND = "BROWSER_MEDIA_NOT_FOUND"

def sanitize_url_for_log(url: str) -> str: ...
def detect_page_status(text: str) -> str | None: ...
def select_media_candidate(candidates: list[dict]) -> dict | None: ...
```

候选排序必须是音频优先、视频次之；只接受指定 CDN host，忽略图片、字体、样式、JSON 和 `blob:`。日志脱敏只移除 query/fragment，不改变实际传给 ffmpeg 的 URL。

- [x] **Step 3: Run the focused tests**

运行同一条 unittest 命令，预期全部 PASS。

- [x] **Step 4: Commit the isolated helper behavior**

```bash
git add scripts/douyin_browser.py tests/test_douyin_browser.py
git commit -m "test: define douyin browser media selection contract"
```

### Task 2: 实现独立可见浏览器和页面媒体捕获

**Files:**
- Modify: `scripts/douyin_browser.py`
- Modify: `tests/test_douyin_browser.py`

- [x] **Step 1: Add failing tests for browser result and cleanup**

使用 fake Playwright 对象测试 `capture_douyin_media(url, profile_dir, workdir, ...)`：

```python
def test_capture_returns_metadata_and_one_media_without_exporting_cookies():
    result = capture_douyin_media(
        "https://v.douyin.com/example/",
        profile_dir=Path("/tmp/profile"),
        playwright_factory=FakePlaywrightFactory.ready_with_video_response(),
    )
    assert result.status == "READY"
    assert result.media["kind"] == "video"
    assert result.metadata["source"] == "https://v.douyin.com/example/"
    assert "cookies" not in result.metadata

def test_capture_returns_manual_verification_status_without_second_navigation():
    fake = FakePlaywrightFactory.verification_then_video()
    result = capture_douyin_media(
        "https://www.douyin.com/video/123",
        profile_dir=Path("/tmp/profile"),
        playwright_factory=fake,
        wait_for_manual_verification=lambda page: True,
    )
    assert result.status == "READY"
    assert fake.page.goto_calls == 1

def test_capture_returns_media_not_found_without_refreshing():
    fake = FakePlaywrightFactory.page_without_media()
    result = capture_douyin_media(
        "https://www.douyin.com/video/123",
        profile_dir=Path("/tmp/profile"),
        playwright_factory=fake,
        wait_timeout_ms=0,
    )
    assert result.status == "BROWSER_MEDIA_NOT_FOUND"
    assert fake.page.goto_calls == 1
```

运行 focused tests，预期 FAIL，确认失败来自实现缺失而非 fake 错误。

- [x] **Step 2: Implement the browser boundary**

实现一个可注入工厂的 `capture_douyin_media`，生产环境使用：

```python
async_playwright().start()
chromium.launch_persistent_context(
    user_data_dir=str(profile_dir),
    headless=False,
    viewport={"width": 1280, "height": 900},
    locale="zh-CN",
)
```

页面行为：

- 只创建一个页面并只调用一次 `page.goto(url, wait_until="domcontentloaded")`；
- 监听 `response`，只记录匹配 CDN host 的音频/视频响应 URL、Content-Type 和媒体类型；
- 监听 `request` 只用于同页面媒体候选，不读取请求头中的 Cookie；
- 检查页面文本中的验证标记；如有验证，输出状态并等待可注入的等待函数，等待后继续同一页面；
- 从 `page.title()`、页面可见文本和 `video.currentSrc` 获取标题/作者/媒体补充信息；
- 只返回一个候选，未找到时返回明确状态；
- `finally` 中关闭 page、context 和 Playwright；
- 不调用 storage state、cookies API、HAR、trace 或截图持久化。

Profile 目录由常量 `DEFAULT_PROFILE_DIR = Path.home() / ".config/video-transcript/browser-profile"` 指定，并在创建时使用 `mkdir(mode=0o700)`；结果 dataclass 只包含状态、metadata、media 和 safe error，不包含 Cookie。

- [x] **Step 3: Run focused tests and syntax check**

```bash
python3 -m unittest tests.test_douyin_browser -v
python3 -m py_compile scripts/douyin_browser.py
```

预期：全部 PASS。

- [x] **Step 4: Commit the browser backend**

```bash
git add scripts/douyin_browser.py tests/test_douyin_browser.py
git commit -m "feat: add isolated visible browser douyin backend"
```

### Task 3: 把抖音主流程切换到浏览器媒体源

**Files:**
- Modify: `scripts/extract.py`
- Modify: `tests/test_pending_flow.py`
- Modify: `tests/test_source_no_deepseek.py`

- [x] **Step 1: Write failing tests for the new dispatch contract**

增加测试：

```python
def test_douyin_url_does_not_require_cookie_file_or_call_yt_dlp():
    # patch browser backend to return a local mock media URL and patch media download
    # assert COOKIE_FILE is absent/irrelevant and subprocess.run is not called
    ...

def test_browser_failure_is_reported_without_cookie_recovery_message():
    # browser backend returns BROWSER_MEDIA_NOT_FOUND
    # assert SystemExit contains BROWSER_MEDIA_NOT_FOUND and not "Fresh cookies"
    ...

def test_douyin_media_is_not_written_to_persistent_cache():
    # successful mocked browser extraction creates pending but no CACHE_DIR mp3/json
    ...
```

先运行 focused tests，预期 FAIL。

- [x] **Step 2: Implement media download/extraction helpers**

在 `extract.py` 中增加：

```python
def download_captured_media(media_url, destination, user_agent="", referer="https://www.douyin.com/"):
    """下载浏览器当前页面捕获的单个媒体源，不读取或拼接 Cookie。"""

def extract_audio_from_captured_media(media, workdir, ffmpeg):
    """独立音频源直接保存；视频源由 ffmpeg -vn 提取到任务临时目录。"""
```

实现要求：

- 使用 `urllib.request` 或现有零依赖 HTTP helper；
- 只设置 User-Agent 和 Referer；
- 只写入 `workdir`；
- 媒体下载大小为 0 时失败；
- 视频源优先尝试 `-c:a copy`，失败再用 `libmp3lame`；
- 不把抖音媒体加入 `_cache_paths`、`CACHE_DIR` 或 `cached_meta`。

- [x] **Step 3: Switch only the Douyin branch**

在 `main()` 中：

- `platform == "douyin"` 时调用 `capture_douyin_media`；
- READY 后合并 metadata，调用捕获媒体音频处理和现有 `asr()`；
- 非 READY 时用状态码和简洁用户提示退出；
- 删除抖音分支对 `download_audio()` 的调用；
- 保留 `download_audio()` 供小红书视频分支使用；
- 保留 URL 音频缓存只服务于小红书现有流程；
- 保留本地文件分支和 pending 写入逻辑。

- [x] **Step 4: Run focused tests and all existing tests**

```bash
python3 -m unittest tests.test_douyin_browser tests.test_pending_flow tests.test_source_no_deepseek -v
python3 -m unittest discover -s tests -v
```

预期：全部 PASS。

- [x] **Step 5: Commit the extraction integration**

```bash
git add scripts/extract.py tests/test_douyin_browser.py tests/test_pending_flow.py tests/test_source_no_deepseek.py
git commit -m "feat: route douyin extraction through visible browser"
```

### Task 4: 更新安装、Skill 和用户文档

**Files:**
- Modify: `scripts/setup.sh`
- Modify: `scripts/setup-cookies.sh`
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `tests/test_source_no_deepseek.py`

- [x] **Step 1: Add documentation contract tests**

断言五份文档描述一致：

```python
for name in ("SKILL.md", "README.md", "INSTALL.md"):
    text = Path(name).read_text(encoding="utf-8")
    assert "专用" in text or "browser-profile" in text
    assert "不需要导出" in text or "不再导出" in text
    assert "单条" in text
```

同时断言 `setup.sh` 不再把 `setup-cookies.sh` 作为默认步骤，抖音主流程文档不再把 `cookies.txt` 作为必需项。

- [x] **Step 2: Update setup scripts**

`setup.sh` 安装 Playwright Python 包并执行 `python -m playwright install chromium`；创建 `~/.config/video-transcript/browser-profile` 并设置 700。保留 yt-dlp 供小红书使用。`setup-cookies.sh` 顶部标记旧版兼容工具，不再在安装脚本输出中引用。

- [x] **Step 3: Update SKILL.md**

把每次前置检查改为检查 `.env`、`config.json`、`.venv` 和 Playwright；抖音 URL 执行浏览器流程；明确首次登录专用窗口、按需启动、单条、手动验证等待、失败不回退、不读 Cookie；保留 pending 后处理约束和本地文件兜底。

- [x] **Step 4: Update README.md and INSTALL.md**

同步架构图、安装 SOP、Profile 位置、首次登录、生命周期、失败状态、隐私边界和验证方式；删除“抖音 Cookie 必需”“重新导出 Cookie”“Fresh cookies”作为默认修复方式的说明。说明小红书仍可用 yt-dlp，抖音不走 yt-dlp。

- [x] **Step 5: Run documentation tests and inspect diff**

```bash
python3 -m unittest tests.test_source_no_deepseek -v
git diff --check
rg -n "setup-cookies|cookies.txt|Fresh cookies|yt-dlp.*抖音|f2|Network.getAllCookies" SKILL.md README.md INSTALL.md scripts/setup.sh scripts/extract.py
```

逐项确认保留内容只出现在历史兼容说明或小红书分支，不能误导 Agent 把它作为抖音默认流程。

- [x] **Step 6: Commit documentation and setup changes**

```bash
git add scripts/setup.sh scripts/setup-cookies.sh SKILL.md README.md INSTALL.md tests/test_source_no_deepseek.py
git commit -m "docs: document visible browser douyin workflow"
```

### Task 5: 集成验证和安全审查

**Files:**
- Modify only if verification finds a defect: files from Tasks 1-4

- [x] **Step 1: Run syntax, unit, and mock smoke checks**

```bash
python3 -m py_compile scripts/extract.py scripts/douyin_browser.py scripts/complete.py
python3 -m unittest discover -s tests -v
git diff --check HEAD~4..HEAD
```

预期：语法检查和全部本地测试通过。

- [x] **Step 2: Run repository security searches**

```bash
git grep -n -i -E 'DEEPSEEK_API_KEY|sk-[A-Za-z0-9]|SILICONFLOW_API_KEY=.*[^$]' -- ':!docs/superpowers/specs/*' ':!docs/superpowers/plans/*' || true
git status --short
git ls-files | rg '(^|/)(\.env|cookies\.txt|browser-profile|cache|pending|\.venv)(/|$)' || true
```

不得出现密钥、Cookie、Profile、缓存、pending、虚拟环境被跟踪的情况。

- [x] **Step 3: Request code review**

以设计 Spec 和本实施计划为依据检查：账号安全边界、抖音分支是否彻底绕开 yt-dlp、浏览器是否按需退出、媒体 URL 是否进入日志或 pending、失败是否错误重试、现有小红书/本地流程是否回归。

- [x] **Step 4: Report real-world acceptance boundary**

明确告知用户本地 mock 测试无法证明抖音当前页面一定返回媒体地址；首次真实验收需要用户在专用可见窗口中手动登录，并只测试一条用户主动选择的链接。不得在验证阶段批量重试或重新导出 Cookie。
