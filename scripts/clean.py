"""Remove build and test caches.

Replaces the previous `rm -rf` + `find` recipe, which needed a POSIX shell and
failed on Windows where GNU make hands recipes to cmd.exe.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIRS = (".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov")


def main() -> int:
    for name in CACHE_DIRS:
        shutil.rmtree(ROOT / name, ignore_errors=True)

    coverage = ROOT / ".coverage"
    coverage.unlink(missing_ok=True)

    for pycache in ROOT.rglob("__pycache__"):
        if ".venv" in pycache.parts:
            continue
        shutil.rmtree(pycache, ignore_errors=True)

    print("clean complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
