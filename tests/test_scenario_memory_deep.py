"""
Deep tests for scenario_memory.py — covers remaining uncovered lines.

Targets:
  - Line 42: ValueError on empty decision/outcome/correction_path
  - Lines 71-72: json.JSONDecodeError/OSError in match()
  - Line 74: record missing "correction_path" key → skip in match()
  - Lines 85-95: validate_store() returns bad record ids
  - Line 101: _similarity with one empty set → 0.0
"""

import json
import os
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

import vsf_rsi.scenario_memory as sm


class TestRecordValidation(TestCase):
    """Line 42: record() raises ValueError on empty required fields."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch.dict(os.environ, {"VSI_RSI_STORE": self._tmpdir})
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_decision_raises(self):
        with self.assertRaises(ValueError):
            sm.record("", "outcome", "fix")

    def test_empty_outcome_raises(self):
        with self.assertRaises(ValueError):
            sm.record("decision", "", "fix")

    def test_empty_correction_path_raises(self):
        with self.assertRaises(ValueError):
            sm.record("decision", "outcome", "")

    def test_whitespace_only_decision_raises(self):
        with self.assertRaises(ValueError):
            sm.record("", "", "")

    def test_valid_record_succeeds(self):
        sid = sm.record("decision", "outcome", "fix")
        self.assertIsInstance(sid, str)
        self.assertEqual(len(sid), 12)


class TestMatchCorruptedRecords(TestCase):
    """Lines 71-72, 74: match() skips corrupted and malformed records."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch.dict(os.environ, {"VSI_RSI_STORE": self._tmpdir})
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_corrupted_json_skipped(self):
        (sm._get_store() / "bad.json").write_text("{NOT VALID JSON")
        result = sm.match("anything", threshold=0.0)
        self.assertIsNone(result)

    def test_unreadable_file_skipped(self):
        bad_path = sm._get_store() / "unreadable.json"
        bad_path.write_text("x")
        os.chmod(bad_path, 0o000)
        result = sm.match("anything", threshold=0.0)
        self.assertIsNone(result)

    def test_missing_correction_path_skipped(self):
        rec = {"id": "abc", "fault_signature": "foo", "decision": "d", "outcome": "o"}
        (sm._get_store() / "nocp.json").write_text(json.dumps(rec))
        result = sm.match("foo", threshold=0.0)
        self.assertIsNone(result)

    def test_non_dict_record_skipped(self):
        (sm._get_store() / "list.json").write_text("[1, 2, 3]")
        result = sm.match("anything", threshold=0.0)
        self.assertIsNone(result)

    def test_valid_record_is_not_skipped(self):
        rec = {
            "id": "good1",
            "fault_signature": "alpha beta",
            "decision": "d",
            "outcome": "o",
            "correction_path": "/fix/1",
        }
        (sm._get_store() / "good1.json").write_text(json.dumps(rec))
        result = sm.match("alpha beta", threshold=0.0)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "good1")


class TestValidateStore(TestCase):
    """Lines 85-95: validate_store() returns ids of corrupted/forged records."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch.dict(os.environ, {"VSI_RSI_STORE": self._tmpdir})
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_corrupted_json_detected(self):
        (sm._get_store() / "corrupt.json").write_text("{bad json")
        bad_ids = sm.validate_store()
        self.assertIn("corrupt", bad_ids)

    def test_missing_correction_path_detected(self):
        rec = {"id": "forged", "decision": "d"}
        (sm._get_store() / "forged.json").write_text(json.dumps(rec))
        bad_ids = sm.validate_store()
        self.assertIn("forged", bad_ids)

    def test_non_dict_detected(self):
        (sm._get_store() / "alist.json").write_text("[1, 2]")
        bad_ids = sm.validate_store()
        self.assertIn("alist", bad_ids)

    def test_valid_record_not_flagged(self):
        rec = {
            "id": "valid",
            "fault_signature": "sig",
            "decision": "d",
            "outcome": "o",
            "correction_path": "/fix",
        }
        (sm._get_store() / "valid.json").write_text(json.dumps(rec))
        bad_ids = sm.validate_store()
        self.assertNotIn("valid", bad_ids)

    def test_empty_store_returns_empty(self):
        bad_ids = sm.validate_store()
        self.assertEqual(bad_ids, [])

    def test_mixed_records(self):
        good = {
            "id": "g1",
            "fault_signature": "sig",
            "decision": "d",
            "outcome": "o",
            "correction_path": "/fix",
        }
        bad = {"id": "b1", "decision": "d"}
        (sm._get_store() / "g1.json").write_text(json.dumps(good))
        (sm._get_store() / "b1.json").write_text(json.dumps(bad))
        (sm._get_store() / "b2.json").write_text("{bad")
        bad_ids = sm.validate_store()
        self.assertIn("b1", bad_ids)
        self.assertIn("b2", bad_ids)
        self.assertNotIn("g1", bad_ids)


class TestSimilarityEdgeCases(TestCase):
    """Line 101: _similarity returns 0.0 when one set is empty."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch.dict(os.environ, {"VSI_RSI_STORE": self._tmpdir})
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_a_returns_zero(self):
        self.assertEqual(sm._similarity("", "hello world"), 0.0)

    def test_empty_b_returns_zero(self):
        self.assertEqual(sm._similarity("hello world", ""), 0.0)

    def test_both_empty_returns_zero(self):
        self.assertEqual(sm._similarity("", ""), 0.0)

    def test_whitespace_only_returns_zero(self):
        self.assertEqual(sm._similarity("   ", "hello"), 0.0)

    def test_nonzero_similarity(self):
        score = sm._similarity("alpha beta gamma", "alpha beta delta")
        self.assertAlmostEqual(score, 2.0 / 4.0)


if __name__ == "__main__":
    main()
