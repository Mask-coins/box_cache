import json
from unittest.mock import patch

import box_cache
from box_cache import cache
from support import CacheTestCase


class AttributesTests(CacheTestCase):
    def setUp(self):
        super().setUp()
        self.setup_cache()

    def test_body_and_nested_attributes_round_trip(self):
        attributes = {
            "schema_version": 1, "url": "https://example.test/日本語",
            "status": 200, "headers": {"content-type": "text/html"},
            "values": [None, True, False, 1, -2, 0.25, "😀"],
        }
        for index, body in enumerate((b"\x00\xff", "本文", b"", "")):
            with self.subTest(body=body), self.clock(index):
                box_cache.put("web", "url", body, attributes=attributes)
                result = box_cache.get_with_attributes("web", "url")
                self.assertEqual(result, (body, attributes))
                self.assertIs(type(result[0]), type(body))
                self.assertEqual(box_cache.get("web", "url"), body)

    def test_no_attributes_and_legacy_record_return_empty_dict(self):
        box_cache.put("web", "url", b"body")
        self.assertEqual(box_cache.get_with_attributes("web", "url"), (b"body", {}))
        path = next(self.cache.glob("web_*.json"))
        value = json.loads(path.read_text(encoding="utf-8"))
        del value["attributes"]
        path.write_text(json.dumps(value), encoding="utf-8")
        before = path.read_bytes()
        self.assertEqual(box_cache.get_with_attributes("web", "url"), (b"body", {}))
        self.assertEqual(path.read_bytes(), before)  # No implicit migration.

    def test_none_and_empty_attributes(self):
        for key, attributes in (("none", None), ("empty", {})):
            box_cache.put("web", key, "body", attributes=attributes)
            self.assertEqual(box_cache.get_with_attributes("web", key), ("body", {}))

    def test_attributes_are_detached_from_caller_and_disk(self):
        attributes = {"headers": {"x": ["original"]}}
        box_cache.put("web", "url", b"body", attributes=attributes)
        attributes["headers"]["x"].append("caller change")
        result = box_cache.get_with_attributes("web", "url")
        self.assertEqual(result[1], {"headers": {"x": ["original"]}})
        result[1]["headers"]["x"].append("read result change")
        self.assertEqual(box_cache.get_with_attributes("web", "url")[1],
                         {"headers": {"x": ["original"]}})

    def test_selects_latest_version_once_for_both_values(self):
        with self.clock(hour=4):
            box_cache.put("web", "url", "new", attributes={"version": "new"})
        with self.clock(hour=3):
            box_cache.put("web", "url", "old", attributes={"version": "old"})
        with patch("box_cache.cache._versions", wraps=cache._versions) as select:
            self.assertEqual(box_cache.get_with_attributes("web", "url"),
                             ("new", {"version": "new"}))
            self.assertEqual(select.call_count, 1)
        self.assertEqual(len(list(self.cache.glob("*.data"))), 2)

    def test_user_attributes_cannot_override_management_fields(self):
        attributes = {"project": "other", "key": "other", "sha256": "not a hash",
                      "saved_at": "user timestamp", "kind": "user kind"}
        box_cache.put("web", "url", b"body", attributes=attributes)
        self.assertEqual(box_cache.get_with_attributes("web", "url"), (b"body", attributes))
        value = json.loads(next(self.cache.glob("web_*.json")).read_text(encoding="utf-8"))
        self.assertEqual(value["project"], "web")
        self.assertEqual(value["key"], "url")
        self.assertNotEqual(value["sha256"], attributes["sha256"])

    def test_missing_cache_and_corrupt_latest_do_not_return_attributes(self):
        self.assertIsNone(box_cache.get_with_attributes("web", "missing"))
        with self.clock():
            box_cache.put("web", "url", b"old", attributes={"v": 1})
        with self.clock(1):
            box_cache.put("web", "url", b"new", attributes={"v": 2})
        latest = sorted(self.cache.glob("*.data"))[-1]
        latest.write_bytes(b"bad")
        with self.assertWarns(box_cache.CacheWarning):
            self.assertIsNone(box_cache.get_with_attributes("web", "url"))
        value = json.loads(latest.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(value["attributes"], {"v": 2})
        self.assertIn("corruption", value)

    def test_invalid_input_is_rejected_before_any_files_are_written(self):
        invalid_types = [[], "json", {1: "value"}, {"nested": {2: "value"}},
                         {"tuple": (1, 2)}, {"body": b"bytes"}, {"object": object()}]
        invalid_values = [{"number": float("nan")}, {"number": float("inf")},
                          {"pair": "\ud83d\ude00"}, {"\ud83d\ude00": "pair"}]
        circular = {}
        circular["self"] = circular
        invalid_values.append(circular)
        before = {p.name: p.read_bytes() for p in self.cache.iterdir()}
        for expected, items in ((TypeError, invalid_types), (ValueError, invalid_values)):
            for attributes in items:
                with self.subTest(attributes=repr(attributes)), self.assertRaises(expected):
                    box_cache.put("web", "url", b"body", attributes=attributes)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.cache.iterdir()})

    def test_invalid_attributes_on_disk_are_corruption_for_both_read_apis(self):
        for index, invalid in enumerate((None, [], "text", {"number": float("nan")})):
            key = str(index)
            box_cache.put("web", key, b"body")
            path = next(p for p in self.cache.glob("web_*.json")
                        if json.loads(p.read_text(encoding="utf-8"))["key"] == key)
            value = json.loads(path.read_text(encoding="utf-8"))
            value["attributes"] = invalid
            path.write_text(json.dumps(value), encoding="utf-8")
            for read in (box_cache.get, box_cache.get_with_attributes):
                with self.subTest(invalid=invalid, read=read), self.assertWarns(box_cache.CacheWarning):
                    self.assertIsNone(read("web", key))

    def test_excessive_nesting_is_rejected_before_writing(self):
        nested = []
        for _ in range(1500):
            nested = [nested]
        with self.assertRaises(ValueError):
            box_cache.put("web", "url", b"body", attributes={"deep": nested})
        self.assertEqual(list(self.cache.glob("web_*")), [])

    def test_excessively_nested_metadata_warns_instead_of_crashing(self):
        box_cache.put("web", "url", b"body")
        path = next(self.cache.glob("web_*.json"))
        broken = '{"attributes":' + '[' * 1500 + '0' + ']' * 1500 + '}'
        path.write_text(broken, encoding="utf-8")
        for read in (box_cache.get, box_cache.get_with_attributes):
            with self.assertWarns(box_cache.CacheWarning):
                self.assertIsNone(read("web", "url"))
        self.assertEqual(path.read_text(encoding="utf-8"), broken)

    def test_cannot_read_attributes_during_publication(self):
        from box_cache.storage import publish

        def inspect(source, destination):
            if destination.suffix == ".json":
                with self.assertWarns(box_cache.CacheWarning):
                    with self.assertRaises(box_cache.CacheBusyError):
                        box_cache.get_with_attributes("web", "url")
            publish(source, destination)

        with patch("box_cache.cache.publish", side_effect=inspect):
            box_cache.put("web", "url", b"body", attributes={"status": 200})
        self.assertEqual(box_cache.get_with_attributes("web", "url"),
                         (b"body", {"status": 200}))
