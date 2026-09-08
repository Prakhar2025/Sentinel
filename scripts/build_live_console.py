"""Build the console against the deployed App Runner API.

`make snapshot` bakes fixtures and needs no backend. This target does the
opposite: it wires the static export to the live engine so the playground
scores real events.

Shell environment variables cannot be used here. Next.js reads
`console/.env.local`, which pins the API to localhost for development, and
that file wins over an inline variable on Windows. `.env.production.local`
takes precedence over `.env.local`, so this script writes one for the
duration of the build and removes it afterwards, leaving no key on disk.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSOLE = ROOT / "console"
OVERRIDE = CONSOLE / ".env.production.local"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: build_live_console.py <api-url> <api-key>")
        return 2
    api_url, api_key = sys.argv[1], sys.argv[2]

    OVERRIDE.write_text(
        f"NEXT_PUBLIC_API_URL={api_url}\nNEXT_PUBLIC_API_KEY={api_key}\nNEXT_PUBLIC_DEMO=\n",
        encoding="utf-8",
    )
    # next.config.ts selects "export" over "standalone" from this flag, and it
    # reads process.env directly, so it cannot come from the .env file above.
    env = {**os.environ, "SENTINEL_STATIC": "1"}
    try:
        result = subprocess.run(
            ["npx", "next", "build"], cwd=CONSOLE, shell=os.name == "nt", env=env
        )
    finally:
        OVERRIDE.unlink(missing_ok=True)

    if result.returncode != 0:
        return result.returncode

    # A build that silently kept the dev defaults is worse than a failed one.
    out = CONSOLE / "out"
    if not out.is_dir():
        print("FAILED: no out/ directory; the build was not a static export")
        return 1
    chunks = list((out / "_next" / "static" / "chunks").rglob("*.js"))
    blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in chunks)
    if api_url not in blob:
        print(f"FAILED: {api_url} is not in the built bundle")
        return 1
    if "localhost:8000" in blob:
        print("FAILED: the bundle still points at localhost:8000")
        return 1

    print(f"built against {api_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
