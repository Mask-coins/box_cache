import json
from unittest.mock import patch

from box_cache import CacheWarning, ConfigurationError, configure, load_config
from box_cache.cli import main
from box_cache.config import config_path
from support import CacheTestCase


class ConfigurationTests(CacheTestCase):
    def test_unconfigured_does_not_initialize(self):
        with self.assertWarns(CacheWarning), self.assertRaises(ConfigurationError):
            load_config()
        self.assertFalse(config_path().parent.exists())

    def test_foreign_config_directory_including_empty_is_untouched(self):
        config_path().parent.mkdir()
        with self.assertWarns(CacheWarning), self.assertRaises(ConfigurationError):
            configure(self.cache)
        self.assertEqual(list(config_path().parent.iterdir()), [])
        self.assertFalse(self.cache.exists())

    def test_foreign_cache_directory_is_untouched(self):
        self.cache.mkdir()
        evidence = self.cache / "user.txt"
        evidence.write_text("preserve")
        with self.assertWarns(CacheWarning), self.assertRaises(ConfigurationError):
            configure(self.cache)
        self.assertEqual(evidence.read_text(), "preserve")
        self.assertEqual(len(list(self.cache.iterdir())), 1)
        self.assertFalse(config_path().exists())

    def test_switch_destination_without_moving_evidence(self):
        from box_cache import get, put
        self.setup_cache()
        put("project", "key", b"original")
        original = list(self.cache.glob("*.data"))[0]
        other = self.root / "other"
        configure(other)
        self.assertEqual(original.read_bytes(), b"original")
        self.assertIsNone(get("project", "key"))
        configure(self.cache)
        self.assertEqual(get("project", "key"), b"original")

    def test_invalid_paths_preserve_existing_config(self):
        self.setup_cache()
        before = config_path().read_bytes()
        for path in ("", self.root / "bad?path", self.root / "bad.",
                     self.root / "missing-parent" / "cache", config_path().parent):
            with self.assertWarns(CacheWarning), self.assertRaises(ConfigurationError):
                configure(path)
            self.assertEqual(config_path().read_bytes(), before)

    def test_corrupt_or_foreign_marker_is_rejected(self):
        self.setup_cache()
        marker = self.cache / ".box_cache.json"
        for content in (b"{broken", b'{"application":"other"}',
                        b'{"application":"box_cache","format_version":true}'):
            marker.write_bytes(content)
            with self.assertWarns(CacheWarning), self.assertRaises(ConfigurationError):
                load_config()
            self.assertEqual(marker.read_bytes(), content)

    def test_cli_configure_and_show(self):
        with patch("builtins.print") as output:
            self.assertEqual(main(["configure", "--cache-dir", str(self.cache)]), 0)
            self.assertEqual(main(["config", "show"]), 0)
        self.assertEqual(json.loads(output.call_args.args[0])["cache_dir"], str(self.cache))

