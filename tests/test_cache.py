import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from box_cache import (
    CacheBusyError, CacheError, CacheWarning, CollisionError, get, put,
)
from support import CacheTestCase


class CacheTests(CacheTestCase):
    def setUp(self):
        super().setUp()
        self.setup_cache()

    def test_round_trip_types_and_arbitrary_keys(self):
        keys = ["", "日本語/\x00\n", "\ud800", "é", "e\u0301", "Key", "key"]
        for key in keys:
            for index, data in enumerate([b"", b"\x00\xff", "", "日本語\ud800", '{"x":1}']):
                with self.clock(index):
                    put("project", key, data)
                self.assertEqual(get("project", key), data)
                self.assertIs(type(get("project", key)), type(data))
        self.assertIsNone(get("project", "absent"))
        self.assertFalse(any(path.is_dir() for path in self.cache.iterdir()))

    def test_history_and_latest_by_saved_time(self):
        with self.clock(hour=4):
            put("project", "key", "newer")
        with self.clock(hour=3):
            put("project", "key", "older written later")
        self.assertEqual(get("project", "key"), "newer")
        self.assertEqual(len(list(self.cache.glob("*.data"))), 2)
        self.assertEqual(len(list(self.cache.glob("project_*.json"))), 2)

    def test_surrogate_pair_and_scalar_keys_remain_distinct(self):
        keys = ["\ud83d\ude00", "\U0001f600", "x\ud83d\ude00\ud800y"]
        with self.clock():
            for index, key in enumerate(keys):
                put("project", key, f"body-{index}")
        for index, key in enumerate(keys):
            with self.subTest(key=ascii(key)):
                self.assertEqual(get("project", key), f"body-{index}")
        self.assertEqual(len(list(self.cache.glob("*.data"))), len(keys))

    def test_legacy_metadata_without_exact_key_field_remains_readable(self):
        key = "日本語\U0001f600"
        put("project", key, b"legacy")
        path = next(self.cache.glob("project_*.json"))
        value = json.loads(path.read_text(encoding="utf-8"))
        del value["key_utf8_hex"]
        path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
        self.assertEqual(get("project", key), b"legacy")

    def test_tampered_exact_key_is_rejected(self):
        put("project", "key", b"body")
        path = next(self.cache.glob("project_*.json"))
        value = json.loads(path.read_text(encoding="utf-8"))
        value["key_utf8_hex"] = "00"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertWarns(CacheWarning):
            self.assertIsNone(get("project", "key"))

    def test_different_projects_and_different_keys(self):
        with self.clock():
            put("first", "key", "first")
            put("second", "key", "second")
            put("FIRST", "other-key", "other")
        self.assertEqual(get("first", "key"), "first")
        self.assertEqual(get("second", "key"), "second")
        self.assertEqual(get("FIRST", "other-key"), "other")

    def test_case_conflict_even_for_different_timestamp(self):
        with self.clock():
            put("Weather", "key", b"original")
        with self.clock(1), self.assertWarns(CacheWarning):
            with self.assertRaises(CollisionError):
                put("weather", "key", b"must not save")
        self.assertEqual(get("Weather", "key"), b"original")
        self.assertEqual(len(list(self.cache.glob("*.data"))), 1)

    def test_same_millisecond_stops_without_overwrite(self):
        with self.clock():
            put("project", "key", "original")
            before = {p.name: p.read_bytes() for p in self.cache.glob("project_*")}
            with self.assertWarns(CacheWarning), self.assertRaises(CollisionError):
                put("project", "key", "replacement")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.cache.glob("project_*")})
        self.assertTrue((self.cache / "box_cache.log").exists())

    def test_corrupt_body_warns_records_and_does_not_fallback(self):
        with self.clock():
            put("project", "key", b"older")
        with self.clock(1):
            put("project", "key", b"newer")
        latest = sorted(self.cache.glob("*.data"))[-1]
        latest.write_bytes(b"XXXXX")  # Same size: checksum must detect it.
        with self.assertWarns(CacheWarning):
            self.assertIsNone(get("project", "key"))
        value = json.loads(latest.with_suffix(".json").read_text())
        self.assertIn("SHA-256", value["corruption"]["reason"])
        self.assertEqual(latest.read_bytes(), b"XXXXX")
        log = (self.cache / "box_cache.log").read_text()
        self.assertIn("Corrupt cache", log)

    def test_broken_metadata_is_preserved_and_logged(self):
        put("project", "key", b"body")
        path = next(self.cache.glob("project_*.json"))
        path.write_bytes(b"{broken")
        with self.assertWarns(CacheWarning):
            self.assertIsNone(get("project", "key"))
        self.assertEqual(path.read_bytes(), b"{broken")
        self.assertIn("Corrupt cache", (self.cache / "box_cache.log").read_text())

    def test_missing_body_and_metadata(self):
        put("project", "body-missing", b"body")
        next(self.cache.glob("*.data")).unlink()
        with self.assertWarns(CacheWarning):
            self.assertIsNone(get("project", "body-missing"))
        put("project", "meta-missing", b"body")
        for path in self.cache.glob("project_*.json"):
            if json.loads(path.read_text())["key"] == "meta-missing":
                path.unlink()
        with self.assertWarns(CacheWarning):
            self.assertIsNone(get("project", "meta-missing"))

    def test_invalid_inputs_do_not_create_cache_versions(self):
        for project in ("", "a/b", "NUL", "COM1", "bad.", "bad ", "x\x00", "a" * 200):
            with self.assertRaises(ValueError):
                put(project, "key", b"body")
        for project, key, data in [(1, "k", b""), ("p", 1, b""), ("p", "k", {})]:
            with self.assertRaises(TypeError):
                put(project, key, data)
        self.assertEqual(list(self.cache.glob("*.data")), [])

    def test_other_process_and_cwd_use_same_config(self):
        put("project", "key", "shared")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        # Also check the base interpreter, outside the IntelliJ virtualenv.
        for executable in {sys.executable, sys._base_executable}:
            with self.subTest(executable=executable):
                result = subprocess.run(
                    [executable, "-B", "-c",
                     "from box_cache import get; assert get('project', 'key') == 'shared'"],
                    cwd=elsewhere, env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_project_name_with_underscores_dots_and_unicode(self):
        project = "調査_2026.v1"
        put(project, "key", "body")
        self.assertEqual(get(project, "key"), "body")

    def test_log_failure_is_also_warned(self):
        import warnings
        put("project", "key", b"body")
        next(self.cache.glob("*.data")).write_bytes(b"bad")
        (self.cache / "box_cache.log").mkdir()
        with warnings.catch_warnings(record=True) as messages:
            warnings.simplefilter("always", CacheWarning)
            self.assertIsNone(get("project", "key"))
        self.assertTrue(any("Cannot write cache log" in str(item.message) for item in messages))
        self.assertTrue(any("Corrupt cache" in str(item.message) for item in messages))

    def test_no_partial_read_during_publish(self):
        from box_cache.storage import publish

        attempts = []

        def inspect_publish(source, destination):
            if destination.suffix == ".data":
                with self.assertWarns(CacheWarning), self.assertRaises(CacheBusyError):
                    get("project", "key")
                attempts.append(True)
            publish(source, destination)

        with patch("box_cache.cache.publish", side_effect=inspect_publish):
            put("project", "key", "complete")
        self.assertEqual(attempts, [True])
        self.assertEqual(get("project", "key"), "complete")

    def test_interrupted_save_retains_evidence_and_returns_none(self):
        from box_cache.storage import publish

        def interrupt(source, destination):
            if destination.suffix == ".json":
                raise OSError("simulated interruption")
            publish(source, destination)

        with patch("box_cache.cache.publish", side_effect=interrupt):
            with self.assertWarns(CacheWarning), self.assertRaises(CacheError):
                put("project", "key", "interrupted")
        self.assertEqual(len(list(self.cache.glob("*.data"))), 1)
        self.assertTrue(list(self.cache.glob("*.tmp")))
        with self.assertWarns(CacheWarning):
            self.assertIsNone(get("project", "key"))

