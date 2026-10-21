import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "douyin_browser", ROOT / "scripts" / "douyin_browser.py"
)
douyin_browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(douyin_browser)


class DouyinBrowserHelperTests(unittest.TestCase):
    def test_select_media_prefers_audio_and_ignores_cover(self):
        candidates = [
            {
                "url": "https://p.douyinvod.com/cover.jpg",
                "kind": "image",
                "content_type": "image/jpeg",
            },
            {
                "url": "https://p.douyinvod.com/video.mp4?token=secret",
                "kind": "video",
                "content_type": "video/mp4",
            },
            {
                "url": "https://p.douyinvod.com/audio.m4a?token=secret",
                "kind": "audio",
                "content_type": "audio/mp4",
            },
        ]

        result = douyin_browser.select_media_candidate(candidates)

        self.assertEqual(result["kind"], "audio")
        self.assertTrue(result["url"].endswith("audio.m4a?token=secret"))

    def test_select_media_falls_back_to_video(self):
        result = douyin_browser.select_media_candidate(
            [
                {
                    "url": "https://p.douyinvod.com/poster.jpg",
                    "kind": "image",
                    "content_type": "image/jpeg",
                },
                {
                    "url": "https://p.douyinvod.com/video.mp4",
                    "kind": "video",
                    "content_type": "video/mp4",
                },
            ]
        )

        self.assertEqual(result["kind"], "video")

    def test_select_media_rejects_non_douyin_hosts(self):
        result = douyin_browser.select_media_candidate(
            [
                {
                    "url": "https://example.com/video.mp4",
                    "kind": "video",
                    "content_type": "video/mp4",
                }
            ]
        )

        self.assertIsNone(result)

    def test_sanitize_url_for_log_removes_query_and_fragment(self):
        self.assertEqual(
            douyin_browser.sanitize_url_for_log(
                "https://p.douyinvod.com/video.mp4?token=secret#part"
            ),
            "https://p.douyinvod.com/video.mp4",
        )

    def test_detect_page_status(self):
        self.assertEqual(
            douyin_browser.detect_page_status("请完成安全验证"),
            "MANUAL_VERIFICATION_REQUIRED",
        )
        self.assertEqual(
            douyin_browser.detect_page_status("Please wait while we verify"),
            "MANUAL_VERIFICATION_REQUIRED",
        )
        self.assertIsNone(douyin_browser.detect_page_status("视频标题\n作者"))

    def test_normalize_media_candidate_classifies_supported_urls(self):
        audio = douyin_browser.normalize_media_candidate(
            "https://cdn.ixigua.com/file/audio.m4a?token=secret",
            "audio/mp4",
            resource_type="media",
        )
        image = douyin_browser.normalize_media_candidate(
            "https://cdn.ixigua.com/file/cover.jpg",
            "image/jpeg",
            resource_type="image",
        )

        self.assertEqual(audio["kind"], "audio")
        self.assertIsNone(image)

    def test_normalize_detects_dash_audio_track_despite_video_content_type(self):
        # 抖音 DASH 音轨流没有扩展名，Content-Type 也是 video/mp4，
        # 只能靠 query 里的 mime_type 区分
        audio = douyin_browser.normalize_media_candidate(
            "https://v3-web.douyinvod.com/abc/video/tos/cn/tos-cn-ve-15/oQxxxx/"
            "?a=6383&mime_type=audio_mp4&br=64000",
            "video/mp4",
            resource_type="media",
        )
        video = douyin_browser.normalize_media_candidate(
            "https://v3-web.douyinvod.com/abc/video/tos/cn/tos-cn-ve-15/oQxxxx/"
            "?a=6383&mime_type=video_mp4&br=2000000",
            "video/mp4",
            resource_type="media",
        )

        self.assertEqual(audio["kind"], "audio")
        self.assertEqual(video["kind"], "video")

    def test_select_media_candidates_keeps_audio_first_then_video(self):
        result = douyin_browser.select_media_candidates(
            [
                {"url": "https://p.douyinvod.com/v1/?mime_type=video_mp4", "kind": "video"},
                {"url": "https://p.douyinvod.com/a1/?mime_type=audio_mp4", "kind": "audio"},
                {"url": "https://p.douyinvod.com/v2/?mime_type=video_mp4", "kind": "video"},
            ]
        )

        self.assertEqual([item["kind"] for item in result], ["audio", "video", "video"])
        self.assertEqual(
            [item["url"] for item in result],
            [
                "https://p.douyinvod.com/a1/?mime_type=audio_mp4",
                "https://p.douyinvod.com/v1/?mime_type=video_mp4",
                "https://p.douyinvod.com/v2/?mime_type=video_mp4",
            ],
        )


class FakeBodyLocator:
    def __init__(self, page):
        self.page = page

    async def inner_text(self, timeout=0):
        if self.page.body_texts:
            return self.page.body_texts.pop(0)
        return ""


class FakePage:
    def __init__(self, body_texts=None, current_sources=None):
        self.body_texts = list(body_texts or [""])
        self.current_sources = list(current_sources or [])
        self.handlers = {}
        self.goto_calls = 0
        self.closed = False

    def on(self, event, handler):
        self.handlers[event] = handler

    async def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls += 1

    def locator(self, selector):
        self.last_locator = selector
        return FakeBodyLocator(self)

    async def eval_on_selector_all(self, selector, expression):
        return self.current_sources

    async def title(self):
        return "测试视频"

    async def evaluate(self, expression):
        if "navigator.userAgent" in expression:
            return "Mozilla/5.0 Test"
        return {"author": "测试作者", "duration": 12}

    async def wait_for_timeout(self, milliseconds):
        return None

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, page, request=None):
        self.page = page
        self.request = request
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, context):
        self.context = context
        self.launch_calls = []

    async def launch_persistent_context(self, **kwargs):
        self.launch_calls.append(kwargs)
        return self.context


class FakePlaywright:
    def __init__(self, page):
        self.page = page
        self.chromium = FakeChromium(FakeContext(page))
        self.stopped = False

    async def stop(self):
        self.stopped = True


class FakePlaywrightFactory:
    def __init__(self, page):
        self.playwright = FakePlaywright(page)

    def __call__(self):
        return self.playwright


class DouyinBrowserCaptureTests(unittest.TestCase):
    def test_capture_returns_metadata_and_one_media_without_cookie_export(self):
        page = FakePage(
            current_sources=["https://cdn.douyinvod.com/video.mp4?token=secret"]
        )
        factory = FakePlaywrightFactory(page)

        result = douyin_browser.capture_douyin_media(
            "https://v.douyin.com/example/",
            profile_dir=Path("/tmp/video-transcript-test-profile"),
            playwright_factory=factory,
            wait_timeout_ms=0,
        )

        self.assertEqual(result.status, "READY")
        self.assertEqual(result.media["kind"], "video")
        self.assertEqual(result.metadata["url"], "https://v.douyin.com/example/")
        self.assertNotIn("cookies", result.metadata)
        self.assertNotIn("cookie", result.metadata)
        self.assertEqual(page.goto_calls, 1)
        self.assertTrue(factory.playwright.stopped)

    def test_capture_does_not_refresh_after_manual_verification(self):
        page = FakePage(
            body_texts=["请完成安全验证", "视频已加载"],
            current_sources=["https://cdn.douyinvod.com/video.mp4"],
        )
        factory = FakePlaywrightFactory(page)

        async def verification_done(_page):
            return True

        result = douyin_browser.capture_douyin_media(
            "https://www.douyin.com/video/123",
            profile_dir=Path("/tmp/video-transcript-test-profile"),
            playwright_factory=factory,
            wait_for_manual_verification=verification_done,
            wait_timeout_ms=1000,
        )

        self.assertEqual(result.status, "READY")
        self.assertEqual(page.goto_calls, 1)

    def test_capture_returns_media_not_found_without_refreshing(self):
        page = FakePage(body_texts=["视频页面"], current_sources=[])
        factory = FakePlaywrightFactory(page)

        result = douyin_browser.capture_douyin_media(
            "https://www.douyin.com/video/123",
            profile_dir=Path("/tmp/video-transcript-test-profile"),
            playwright_factory=factory,
            wait_timeout_ms=0,
        )

        self.assertEqual(result.status, "BROWSER_MEDIA_NOT_FOUND")
        self.assertEqual(page.goto_calls, 1)

    def test_capture_can_save_media_while_browser_context_is_alive(self):
        class FakeResponse:
            status = 200

            async def body(self):
                return b"media bytes"

            async def dispose(self):
                return None

        class FakeRequestContext:
            def __init__(self):
                self.urls = []

            async def get(self, url, **kwargs):
                self.urls.append((url, kwargs))
                return FakeResponse()

        page = FakePage(
            current_sources=["https://cdn.douyinvod.com/video.mp4?token=secret"]
        )
        request_context = FakeRequestContext()
        factory = FakePlaywrightFactory(page)
        factory.playwright.chromium.context.request = request_context

        with self.subTest("browser session download"):
            with tempfile.TemporaryDirectory() as directory:
                result = douyin_browser.capture_douyin_media(
                    "https://www.douyin.com/video/123",
                    profile_dir=Path(directory) / "profile",
                    media_output_dir=Path(directory) / "media",
                    playwright_factory=factory,
                    wait_timeout_ms=0,
                )
                local_path = Path(result.media["local_path"])
                self.assertEqual(result.status, "READY")
                self.assertEqual(local_path.read_bytes(), b"media bytes")
                self.assertEqual(len(request_context.urls), 1)
                self.assertEqual(
                    request_context.urls[0][1]["headers"],
                    {"Referer": "https://www.douyin.com/"},
                )


if __name__ == "__main__":
    unittest.main()
