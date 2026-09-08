#!/usr/bin/env python3
"""Visible, single-item Douyin browser backend.

This module deliberately uses a dedicated persistent Playwright profile. It
does not export cookies, call Douyin JSON APIs, or replay browser cookies from
outside the browser context.
"""
import asyncio
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse, urlunparse


DEFAULT_PROFILE_DIR = Path.home() / ".config/video-transcript/browser-profile"
DOUYIN_MEDIA_HOSTS = ("douyinvod.com", "ixigua.com")
DOUYIN_REFERER = "https://www.douyin.com/"

MEDIA_STATUS_READY = "READY"
MEDIA_STATUS_MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
MEDIA_STATUS_PAGE_BLOCKED = "PAGE_BLOCKED"
MEDIA_STATUS_BROWSER_NOT_READY = "BROWSER_NOT_READY"
MEDIA_STATUS_BROWSER_LAUNCH_FAILED = "BROWSER_LAUNCH_FAILED"
MEDIA_STATUS_BROWSER_PAGE_LOAD_FAILED = "BROWSER_PAGE_LOAD_FAILED"
MEDIA_STATUS_BROWSER_MEDIA_NOT_FOUND = "BROWSER_MEDIA_NOT_FOUND"
MEDIA_STATUS_MEDIA_DOWNLOAD_FAILED = "MEDIA_DOWNLOAD_FAILED"

_VERIFICATION_MARKERS = (
    "请完成安全验证",
    "安全验证",
    "验证后继续",
    "验证码",
    "please wait while we verify",
    "waf-jschallenge",
    "_wafchallengeid",
)
_VIDEO_EXTENSIONS = (".mp4", ".m4v", ".webm", ".mov", ".m3u8", ".mpd")
_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac")


def _loop_time() -> float:
    """Return monotonic loop time on both Python 3.6 and modern Python."""
    try:
        return asyncio.get_running_loop().time()
    except AttributeError:
        return asyncio.get_event_loop().time()


@dataclass
class BrowserCaptureResult:
    status: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    media: Optional[Dict[str, Any]] = None
    error: str = ""


def _is_supported_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in DOUYIN_MEDIA_HOSTS)


def sanitize_url_for_log(url: str) -> str:
    """Remove query and fragment from a URL before it reaches logs."""
    parsed = urlparse(str(url or ""))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def detect_page_status(text: str) -> Optional[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if any(marker.lower() in normalized for marker in _VERIFICATION_MARKERS):
        return MEDIA_STATUS_MANUAL_VERIFICATION_REQUIRED
    return None


def normalize_media_candidate(
    url: str, content_type: str = "", resource_type: str = ""
) -> Optional[Dict[str, Any]]:
    """Normalize one page resource, rejecting non-media and foreign hosts."""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")) or not _is_supported_host(url):
        return None

    content_type = str(content_type or "").split(";", 1)[0].lower().strip()
    path = (urlparse(url).path or "").lower()
    resource_type = str(resource_type or "").lower().strip()

    if content_type.startswith("audio/") or path.endswith(_AUDIO_EXTENSIONS):
        kind = "audio"
    elif content_type.startswith("video/") or path.endswith(_VIDEO_EXTENSIONS):
        kind = "video"
    elif resource_type == "media" and not path.endswith(
        (".jpg", ".jpeg", ".png", ".gif", ".webp", ".css", ".js", ".json")
    ):
        # Some CDN responses omit Content-Type and extension. A media resource
        # from the allow-listed host is still a valid candidate in that case.
        kind = "video"
    else:
        return None

    return {
        "url": url,
        "kind": kind,
        "content_type": content_type,
        "resource_type": resource_type,
    }


def select_media_candidate(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return one deduplicated candidate, preferring independent audio."""
    unique = []
    seen = set()
    for candidate in candidates or []:
        url = str(candidate.get("url") or "")
        if not url or url in seen:
            continue
        if not _is_supported_host(url):
            continue
        if candidate.get("kind") not in ("audio", "video"):
            continue
        seen.add(url)
        unique.append(candidate)
    unique.sort(key=lambda item: 0 if item.get("kind") == "audio" else 1)
    return unique[0] if unique else None


def _safe_error(error: Any) -> str:
    return re.sub(r"https?://[^\s]+", "[url]", " ".join(str(error).split()))[:500]


def _default_metadata(url: str, page_title: str = "", author: str = "", duration: Any = 0):
    return {
        "title": (page_title or "抖音视频").strip()[:60],
        "author": str(author or "").strip(),
        "url": url,
        "duration": duration or 0,
    }


async def _call_optional_waiter(waiter: Optional[Callable], page: Any) -> bool:
    if waiter is None:
        return True
    result = waiter(page)
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


async def _download_in_browser_context(context: Any, url: str, destination: Path) -> bool:
    """Download one captured CDN resource while the browser session is alive."""
    request_context = getattr(context, "request", None)
    if request_context is None:
        return False
    response = None
    try:
        response = await request_context.get(
            url,
            headers={"Referer": DOUYIN_REFERER},
            timeout=300000,
            fail_on_status_code=False,
        )
        status = int(getattr(response, "status", 0) or 0)
        if status < 200 or status >= 300:
            return False
        body = await response.body()
        if not body:
            return False
        destination.write_bytes(body)
        return destination.is_file() and destination.stat().st_size > 0
    except Exception:
        return False
    finally:
        if response is not None and hasattr(response, "dispose"):
            try:
                await response.dispose()
            except Exception:
                pass


async def _capture_with_playwright(
    url: str,
    profile_dir: Path,
    wait_timeout_ms: int,
    wait_for_manual_verification: Optional[Callable],
    media_output_dir: Optional[Path] = None,
    playwright_factory: Optional[Callable] = None,
) -> BrowserCaptureResult:
    if playwright_factory is None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:
            return BrowserCaptureResult(
                MEDIA_STATUS_BROWSER_NOT_READY,
                error="Playwright 未安装，请先运行 scripts/setup.sh",
            )
        playwright_factory = async_playwright

    playwright = None
    context = None
    page = None
    candidates: List[Dict[str, Any]] = []
    page_load_error = ""
    try:
        factory_result = playwright_factory()
        playwright = await factory_result.start() if hasattr(factory_result, "start") else factory_result
        chromium = getattr(playwright, "chromium", None)
        if chromium is None:
            return BrowserCaptureResult(MEDIA_STATUS_BROWSER_LAUNCH_FAILED, error="未找到 Chromium 浏览器引擎")

        profile_dir = Path(profile_dir).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            profile_dir.chmod(0o700)
        except OSError:
            pass
        context = await chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        def on_response(response):
            try:
                candidate = normalize_media_candidate(
                    response.url,
                    response.headers.get("content-type", ""),
                    getattr(response.request, "resource_type", ""),
                )
                if candidate:
                    candidates.append(candidate)
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as error:
            page_load_error = _safe_error(error)

        deadline = _loop_time() + max(wait_timeout_ms, 0) / 1000
        verification_reported = False
        while True:
            try:
                body_text = await page.locator("body").inner_text(timeout=2000)
            except Exception:
                body_text = ""
            page_status = detect_page_status(body_text)
            if page_status == MEDIA_STATUS_MANUAL_VERIFICATION_REQUIRED:
                if not verification_reported:
                    print("BROWSER_STATUS=MANUAL_VERIFICATION_REQUIRED", flush=True)
                    verification_reported = True
                if not await _call_optional_waiter(wait_for_manual_verification, page):
                    return BrowserCaptureResult(page_status, error="页面需要用户手动完成验证")
            else:
                verification_reported = False

            if candidates:
                break
            try:
                current_srcs = await page.eval_on_selector_all(
                    "video",
                    "els => els.map(el => el.currentSrc || el.src).filter(Boolean)",
                )
                for current_src in current_srcs or []:
                    candidate = normalize_media_candidate(current_src, "", "media")
                    if candidate:
                        candidates.append(candidate)
            except Exception:
                pass
            if _loop_time() >= deadline:
                break
            await page.wait_for_timeout(500)

        try:
            page_title = await page.title()
        except Exception:
            page_title = ""
        try:
            page_meta = await page.evaluate(
                """() => ({
                    title: document.querySelector('meta[property="og:title"]')?.content ||
                        document.querySelector('meta[name="title"]')?.content || '',
                    author: document.querySelector('meta[name="author"]')?.content ||
                        document.querySelector('meta[property="og:author"]')?.content || '',
                    duration: document.querySelector('video')?.duration || 0
                })"""
            )
        except Exception:
            page_meta = {}

        selected = select_media_candidate(candidates)
        metadata = _default_metadata(
            url,
            (page_meta.get("title") if isinstance(page_meta, dict) else "") or page_title,
            page_meta.get("author", "") if isinstance(page_meta, dict) else "",
            page_meta.get("duration", 0) if isinstance(page_meta, dict) else 0,
        )
        if selected:
            selected = {
                **selected,
                "user_agent": await page.evaluate("() => navigator.userAgent"),
                "referer": DOUYIN_REFERER,
            }
            if media_output_dir is not None:
                media_output_dir = Path(media_output_dir).expanduser()
                media_output_dir.mkdir(parents=True, exist_ok=True)
                suffix = ".m4a" if selected["kind"] == "audio" else ".mp4"
                local_path = media_output_dir / ("captured" + suffix)
                if not await _download_in_browser_context(context, selected["url"], local_path):
                    return BrowserCaptureResult(
                        MEDIA_STATUS_MEDIA_DOWNLOAD_FAILED,
                        metadata=metadata,
                        error="浏览器会话内下载捕获的媒体失败",
                    )
                selected["local_path"] = str(local_path)
            return BrowserCaptureResult(MEDIA_STATUS_READY, metadata=metadata, media=selected)
        if page_load_error:
            return BrowserCaptureResult(
                MEDIA_STATUS_BROWSER_PAGE_LOAD_FAILED,
                metadata=metadata,
                error=page_load_error,
            )
        if verification_reported:
            return BrowserCaptureResult(
                MEDIA_STATUS_PAGE_BLOCKED,
                metadata=metadata,
                error="页面验证在等待期限内未完成",
            )
        return BrowserCaptureResult(
            MEDIA_STATUS_BROWSER_MEDIA_NOT_FOUND,
            metadata=metadata,
            error="当前页面没有捕获到可用媒体源",
        )
    except Exception as error:
        return BrowserCaptureResult(MEDIA_STATUS_BROWSER_LAUNCH_FAILED, error=_safe_error(error))
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if playwright is not None and hasattr(playwright, "stop"):
            try:
                await playwright.stop()
            except Exception:
                pass


def capture_douyin_media(
    url: str,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    wait_timeout_ms: int = 180000,
    wait_for_manual_verification: Optional[Callable] = None,
    media_output_dir: Optional[Path] = None,
    playwright_factory: Optional[Callable] = None,
) -> BrowserCaptureResult:
    """Open one visible browser page and capture one current media source."""
    if not str(url or "").strip():
        return BrowserCaptureResult(MEDIA_STATUS_BROWSER_NOT_READY, error="抖音 URL 为空")
    coroutine = _capture_with_playwright(
        str(url).strip(),
        Path(profile_dir),
        wait_timeout_ms,
        wait_for_manual_verification,
        media_output_dir,
        playwright_factory,
    )
    if hasattr(asyncio, "run"):
        result = asyncio.run(coroutine)
    else:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(coroutine)
        finally:
            loop.close()
    print(f"BROWSER_STATUS={result.status}", flush=True)
    return result


if __name__ == "__main__":
    print("该模块由 extract.py 调用，不直接执行抖音任务。")
