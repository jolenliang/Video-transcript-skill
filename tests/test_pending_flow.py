import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract = load_module("extract", ROOT / "scripts" / "extract.py")
complete = load_module("complete", ROOT / "scripts" / "complete.py")


class PendingFileTests(unittest.TestCase):
    def test_pending_markdown_keeps_full_transcript_and_metadata(self):
        transcript = "一段很长的原文。" * 4000
        meta = {
            "title": '标题: "需要清理"',
            "author": "作者",
            "url": "https://www.douyin.com/video/123",
            "duration": 99,
        }

        with tempfile.TemporaryDirectory() as directory:
            pending_path = extract.write_pending(
                Path(directory), "douyin", meta, transcript
            )
            content = pending_path.read_text(encoding="utf-8")

        self.assertEqual(pending_path.suffix, ".md")
        self.assertIn("type: video-transcript-pending", content)
        self.assertIn("status: pending", content)
        self.assertIn("platform: douyin", content)
        self.assertIn('title: "标题: \\"需要清理\\""', content)
        self.assertIn("## 原始文案", content)
        self.assertTrue(content.endswith(transcript + "\n"))

    def test_pending_name_is_stable_and_distinguishes_same_title(self):
        meta = {"title": "同一个标题", "author": "", "duration": 0}

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first = extract.write_pending(
                directory,
                "douyin",
                {**meta, "url": "https://example.test/one"},
                "文案一",
                extracted="2026-08-31",
            )
            repeat = extract.write_pending(
                directory,
                "douyin",
                {**meta, "url": "https://example.test/one"},
                "文案一",
                extracted="2026-08-31",
            )
            second = extract.write_pending(
                directory,
                "douyin",
                {**meta, "url": "https://example.test/two"},
                "文案二",
                extracted="2026-08-31",
            )

        self.assertEqual(first, repeat)
        self.assertNotEqual(first, second)

    def test_config_requires_only_siliconflow_key(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            env_file = directory / ".env"
            config_file = directory / "config.json"
            vault_dir = directory / "notes"
            env_file.write_text("SILICONFLOW_API_KEY=sf-test\n", encoding="utf-8")
            config_file.write_text(
                json.dumps({"vault_dir": str(vault_dir)}), encoding="utf-8"
            )

            with patch.object(extract, "ENV_FILE", env_file), patch.object(
                extract, "CONFIG_FILE", config_file
            ):
                env, loaded_vault = extract.load_config()

        self.assertEqual(env["SILICONFLOW_API_KEY"], "sf-test")
        self.assertEqual(loaded_vault, vault_dir)

    def test_platform_directories_remain_compatible(self):
        vault_dir = Path("/vault/I-抖音文案")
        self.assertEqual(extract.notes_dir_for(vault_dir, "douyin"), vault_dir)
        self.assertEqual(
            extract.notes_dir_for(vault_dir, "xhs"),
            Path("/vault/I-小红书文案"),
        )

    def test_normalize_url_accepts_markdown_link_and_escaped_underscore(self):
        raw = r"[https://v.douyin.com/hSMokeshs\_o/](https://v.douyin.com/hSMokeshs_o/)"
        self.assertEqual(
            extract.normalize_source_url(raw),
            "https://v.douyin.com/hSMokeshs_o/",
        )

    def test_download_uses_writable_cookie_copy_and_preserves_source_file(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            cookie_file = directory / "cookies.txt"
            cookie_file.write_text("original cookies\n", encoding="utf-8")
            workdir = directory / "workdir"
            workdir.mkdir()
            cache_dir = directory / "cache"
            seen = {}

            def fake_run(cmd, **kwargs):
                cookie_path = Path(cmd[cmd.index("--cookies") + 1])
                seen["cookie_path"] = cookie_path
                cookie_path.write_text("updated cookies\n", encoding="utf-8")
                (workdir / "video.info.json").write_text(
                    json.dumps(
                        {
                            "title": "测试视频",
                            "uploader": "作者",
                            "webpage_url": "https://www.douyin.com/video/1",
                            "duration": 1,
                        }
                    ),
                    encoding="utf-8",
                )
                (workdir / "video.mp3").write_bytes(b"audio")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch.object(extract, "COOKIE_FILE", cookie_file), patch.object(
                extract, "CACHE_DIR", cache_dir
            ), patch.object(extract.subprocess, "run", side_effect=fake_run):
                extract.download_audio("https://example.test/video/1", workdir, "ffmpeg")

            self.assertNotEqual(seen["cookie_path"], cookie_file)
            self.assertEqual(seen["cookie_path"].parent, workdir)
            self.assertEqual(cookie_file.read_text(encoding="utf-8"), "original cookies\n")

    def test_main_writes_absolute_pending_path_after_mocked_local_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            pending_dir = directory / "pending"
            source = directory / "sample.mp4"
            source.write_bytes(b"video")

            def fake_extract_audio(video, workdir, ffmpeg):
                audio = workdir / "sample.mp3"
                audio.write_bytes(b"audio")
                return audio, {"title": "本地视频", "author": "", "url": "", "duration": 0}

            output = io.StringIO()
            with patch.object(extract, "PENDING_DIR", pending_dir), patch.object(
                extract,
                "load_config",
                return_value=(
                    {"SILICONFLOW_API_KEY": "mock-key"},
                    directory / "vault",
                ),
            ), patch.object(extract, "get_ffmpeg", return_value="ffmpeg"), patch.object(
                extract, "extract_audio_from_file", side_effect=fake_extract_audio
            ), patch.object(extract, "asr", return_value="完整的本地视频文案"), patch.object(
                sys, "argv", ["extract.py", "--file", str(source)]
            ), redirect_stdout(output):
                extract.main()

            pending_files = list(pending_dir.glob("*.md"))
            self.assertEqual(len(pending_files), 1)
            self.assertTrue(pending_files[0].is_absolute())
            self.assertIn(f"PENDING_FILE={pending_files[0]}", output.getvalue())
            self.assertIn("完整的本地视频文案", pending_files[0].read_text(encoding="utf-8"))

    def test_implementation_no_longer_mentions_deepseek(self):
        source = (ROOT / "scripts" / "extract.py").read_text(encoding="utf-8")
        self.assertNotIn("deepseek", source.lower())
        self.assertNotIn("DEEPSEEK_API_KEY", source)


class PendingCleanupTests(unittest.TestCase):
    def test_cleanup_deletes_only_pending_file_after_valid_final_file(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            pending_dir = directory / "pending"
            pending_dir.mkdir()
            pending = pending_dir / "one.md"
            other_pending = pending_dir / "two.md"
            final = directory / "final.md"
            pending.write_text("pending", encoding="utf-8")
            other_pending.write_text("keep", encoding="utf-8")
            final.write_text("final note", encoding="utf-8")

            with patch.object(complete, "PENDING_DIR", pending_dir):
                complete.remove_pending_after_success(pending, final)

            self.assertFalse(pending.exists())
            self.assertTrue(other_pending.exists())

    def test_cleanup_keeps_pending_when_final_file_is_missing_or_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            pending_dir = directory / "pending"
            pending_dir.mkdir()
            pending = pending_dir / "one.md"
            final = directory / "final.md"
            pending.write_text("pending", encoding="utf-8")

            with patch.object(complete, "PENDING_DIR", pending_dir):
                with self.assertRaises(ValueError):
                    complete.remove_pending_after_success(pending, final)
                self.assertTrue(pending.exists())

                final.write_text("", encoding="utf-8")
                with self.assertRaises(ValueError):
                    complete.remove_pending_after_success(pending, final)
                self.assertTrue(pending.exists())


if __name__ == "__main__":
    unittest.main()
