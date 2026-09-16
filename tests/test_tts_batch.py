import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tts_batch


class NamingAndApprovalTests(unittest.TestCase):
    def test_legacy_and_dated_names(self):
        self.assertEqual(tts_batch.parse_identity(Path("A001_旧稿.md")), ("A001", "A001"))
        self.assertEqual(
            tts_batch.parse_identity(Path("20260901-A031公司赔偿.md")),
            ("A031", "20260901-A031公司赔偿"),
        )

    def test_requires_exact_approval_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / "A001_待审核.md"
            pending.write_text("审核状态：待审核\n\n## 完整口播稿\n正文\n\n## 来源\n来源", encoding="utf-8")
            approved = root / "A002_已审核.md"
            approved.write_text("审核状态：已审核\n\n## 完整口播稿\n正文\n\n## 来源\n来源", encoding="utf-8")
            self.assertFalse(tts_batch.is_approved(pending))
            self.assertTrue(tts_batch.is_approved(approved))

    def test_extracts_only_spoken_section(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "稿件.md"
            path.write_text(
                "## 完整口播稿\n\n正文\n\n### 朗读提示\n仍属正文\n\n## 画面节点建议\n不得送入",
                encoding="utf-8",
            )
            self.assertEqual(tts_batch.extract_script(path), "正文\n\n### 朗读提示\n仍属正文")


class EnvironmentTests(unittest.TestCase):
    def test_load_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# comment\nFISH_AUDIO_API_KEY='secret'\nFISH_AUDIO_MODEL=s2.1-pro-free\n", encoding="utf-8")
            self.assertEqual(tts_batch.load_env_file(path)["FISH_AUDIO_API_KEY"], "secret")


if __name__ == "__main__":
    unittest.main()
