import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationAndSetupTests(unittest.TestCase):
    def test_setup_keys_only_references_siliconflow(self):
        source = (ROOT / "scripts" / "setup-keys.sh").read_text(encoding="utf-8")
        self.assertNotIn("DEEPSEEK", source)
        self.assertIn("SILICONFLOW_API_KEY", source)

    def test_skill_docs_describe_pending_agent_flow(self):
        for name in ("SKILL.md", "README.md", "INSTALL.md"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("pending", source.lower(), name)
            self.assertIn("Agent", source, name)

    def test_douyin_docs_require_visible_isolated_browser_flow(self):
        for name in ("SKILL.md", "README.md", "INSTALL.md"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("browser-profile", source, name)
            self.assertIn("单条", source, name)
            self.assertIn("不需要导出", source, name)

    def test_setup_script_does_not_make_cookie_export_a_default_step(self):
        source = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
        self.assertIn("playwright install chromium", source)
        self.assertIn("browser-profile", source)
        self.assertNotIn("setup-cookies.sh", source)

    def test_setup_script_searches_for_supported_python_versions(self):
        source = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
        self.assertIn("python3.12", source)
        self.assertIn("python3.11", source)
        self.assertIn("python3.10", source)
        self.assertIn("python3.9", source)

    def test_cleanup_script_does_not_own_semantic_quality_rules(self):
        source = (ROOT / "scripts" / "complete.py").read_text(encoding="utf-8")
        self.assertNotIn("quality", source.lower())
        self.assertNotIn("emoji", source.lower())
        self.assertNotIn("paragraph", source.lower())
        self.assertIn("non-empty", source)


if __name__ == "__main__":
    unittest.main()
