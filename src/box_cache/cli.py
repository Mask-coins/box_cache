"""Initial setup and configuration display."""

import argparse
import json
import sys

from .config import configure, load_config
from .exceptions import CacheError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="box-cache")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("configure", help="Set the shared cache directory")
    setup.add_argument("--cache-dir", required=True)
    config = commands.add_parser("config", help="Inspect configuration")
    config.add_subparsers(dest="action", required=True).add_parser("show")
    args = parser.parse_args(argv)
    try:
        if args.command == "configure":
            print(configure(args.cache_dir))
        else:
            print(json.dumps(load_config(), ensure_ascii=True, indent=2))
        return 0
    except CacheError as exc:
        print(f"box-cache: {exc}", file=sys.stderr)
        return 1

