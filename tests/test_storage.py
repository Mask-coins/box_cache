import os
from pathlib import Path
import subprocess
import sys

from box_cache import CacheBusyError, CollisionError
from box_cache.storage import locked, publish, temporary
from support import CacheTestCase


class StorageTests(CacheTestCase):
    def setUp(self):
        super().setUp()
        self.setup_cache()

    def test_publish_does_not_overwrite_even_without_precheck(self):
        destination = self.cache / "existing.data"
        destination.write_bytes(b"evidence")
        source = temporary(self.cache, b"replacement")
        with self.assertRaises(CollisionError):
            publish(source, destination)
        self.assertEqual(destination.read_bytes(), b"evidence")
        self.assertEqual(source.read_bytes(), b"replacement")

    def test_lock_releases_after_exception(self):
        with self.assertRaises(RuntimeError):
            with locked(self.cache):
                raise RuntimeError("interrupted")
        with locked(self.cache):
            pass

    def test_lock_excludes_other_process(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        code = (
            "import sys; from pathlib import Path; "
            "from box_cache.storage import locked; "
            "from box_cache import CacheBusyError\n"
            "try:\n"
            "    with locked(Path(sys.argv[1])): pass\n"
            "except CacheBusyError: sys.exit(0)\n"
            "sys.exit(1)\n"
        )
        with locked(self.cache):
            result = subprocess.run(
                [sys.executable, "-B", "-c", code, str(self.cache)],
                env=env, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

