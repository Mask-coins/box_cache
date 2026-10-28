from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from box_cache import configure


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="box-cache-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / "AppData"
        self.local.mkdir()
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cache = self.root / "cache"

    def setup_cache(self):
        configure(self.cache)

    @contextmanager
    def clock(self, millisecond=0, hour=3):
        saved = datetime(2026, 10, 28, hour, 0, 0, millisecond * 1000,
                         tzinfo=timezone.utc)
        with patch("box_cache.metadata.now", return_value=saved):
            yield

