import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tts_batch


class NamingAndApprovalTests(unittest.TestCase):
    def test_legacy_and_dated_names(self):
        self.assertEqual(tts_batch.parse_identity(Path("A001_旧稿.md")), ("A001", "A001_旧稿"))
        self.assertEqual(
            tts_batch.parse_identity(Path("20260901-A031公司赔偿.md")),
            ("A031", "20260901-A031公司赔偿"),
        )

    def test_output_stem_keeps_readable_title(self):
        self.assertEqual(
            tts_batch.parse_identity(Path("A127_拒绝亲子鉴定就一定会败诉吗口播稿.md")),
            ("A127", "A127_拒绝亲子鉴定就一定会败诉吗口播稿"),
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
    def test_script_at_end_of_file_is_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'case.md'
            path.write_text('## 事实核验\n来源\n## 口播稿\n真正正文', encoding='utf-8')
            self.assertEqual(tts_batch.extract_script(path), '真正正文')

    def test_resume_rejects_changed_audio_script_or_subtitles(self):
        import hashlib
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, srt, report = root/'a.mp3', root/'a.srt', root/'report.json'
            audio.write_bytes(b'audio')
            srt.write_bytes(b'captions')
            data = dict(script_sha256=tts_batch.text_hash('正文'),
                        audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
                        srt_sha256=hashlib.sha256(srt.read_bytes()).hexdigest(),
                        alignment_confidence=.97, review_cues=[])
            report.write_text(json.dumps(data), encoding='utf-8')
            self.assertTrue(tts_batch.verified_outputs(report, '正文', audio, srt))
            self.assertFalse(tts_batch.verified_outputs(report, '改了正文', audio, srt))
            srt.write_bytes(b'wrong subtitles')
            self.assertFalse(tts_batch.verified_outputs(report, '正文', audio, srt))
            srt.write_bytes(b'captions')
            audio.write_bytes(b'wrong audio')
            self.assertFalse(tts_batch.verified_outputs(report, '正文', audio, srt))

    def test_asr_homophone_errors_do_not_enter_final_captions(self):
        raw = '1\n00:00:00,000 --> 00:00:03,000\n賬戶魚兒只有262元\n'
        result, _, _ = tts_batch.source_locked_srt('账户余额只有262元。', raw)
        self.assertIn('账户余额只有262元', result)
        self.assertNotIn('魚兒', result)

    def test_load_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# comment\nFISH_AUDIO_API_KEY='secret'\nFISH_AUDIO_MODEL=s2.1-pro-free\n", encoding="utf-8")
            self.assertEqual(tts_batch.load_env_file(path)["FISH_AUDIO_API_KEY"], "secret")


class CaptionPunctuationTests(unittest.TestCase):
    def test_rejects_reset_overlap_and_missing_audio_tail(self):
        good = '1\n00:00:00,000 --> 00:00:03,000\n正文\n'
        self.assertTrue(tts_batch.valid_caption_timeline(good, 3.1))
        self.assertFalse(tts_batch.valid_caption_timeline(good, 23))
        bad = good + '\n2\n00:00:00,000 --> 00:00:01,000\n倒退\n'
        self.assertFalse(tts_batch.valid_caption_timeline(bad, 3.1))

    def test_strips_caption_ending_punctuation_by_default(self):
        self.assertEqual(tts_batch.caption_display_text("为什么？"), "为什么")
        self.assertEqual(tts_batch.caption_display_text("净身出户。"), "净身出户")
        self.assertEqual(tts_batch.caption_display_text("他说「可以。」"), "他说「可以」")

    def test_can_preserve_caption_ending_punctuation(self):
        self.assertEqual(
            tts_batch.caption_display_text("为什么？", strip_ending_punctuation=False),
            "为什么？",
        )

    def test_punctuation_only_caption_becomes_empty(self):
        self.assertEqual(tts_batch.caption_display_text("。"), "")


if __name__ == "__main__":
    unittest.main()
