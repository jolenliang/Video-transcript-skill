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

    def test_cleanup_script_does_not_own_semantic_quality_rules(self):
        source = (ROOT / "scripts" / "complete.py").read_text(encoding="utf-8")
        self.assertNotIn("quality", source.lower())
        self.assertNotIn("emoji", source.lower())
        self.assertNotIn("paragraph", source.lower())
        self.assertIn("non-empty", source)


if __name__ == "__main__":
    unittest.main()
