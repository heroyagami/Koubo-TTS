import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update_caption_punctuation import migrate_srt


class MigrationTests(unittest.TestCase):
    def test_restore_questions_without_retiming_or_changing_internal_punctuation(self):
        raw = '1\r\n00:00:00,000 --> 00:00:02,000\r\n可以吗\r\n\r\n2\r\n00:00:02,000 --> 00:00:04,000\r\n价格3.14元，没错。\r\n'
        fixed, stats = migrate_srt(raw, '可以吗？\n\n价格3.14元，没错！')
        self.assertIn('可以吗？\r\n', fixed)
        self.assertIn('价格3.14元，没错！\r\n', fixed)
        self.assertIn('00:00:02,000 --> 00:00:04,000', fixed)
        self.assertTrue(stats['source_exact_match'])
        self.assertEqual(migrate_srt(fixed, '可以吗？\n\n价格3.14元，没错！')[0], fixed)

    def test_mismatch_does_not_guess_punctuation_or_correct_words(self):
        raw = '1\n00:00:00,000 --> 00:00:02,000\n鱼儿是3.14元。\n'
        fixed, stats = migrate_srt(raw, '余额是3.14元？')
        self.assertIn('鱼儿是3.14元\n', fixed)
        self.assertFalse(stats['source_exact_match'])

    def test_multiline_ellipsis_and_quoted_question(self):
        raw = '1\n00:00:00,000 --> 00:00:02,000\n他说，\n“可以吗”\n\n2\n00:00:02,000 --> 00:00:04,000\n等等...\n'
        fixed, _ = migrate_srt(raw, '他说，“可以吗？”\n\n等等...')
        self.assertIn('他说，\n“可以吗？”', fixed)
        self.assertIn('等等...', fixed)
