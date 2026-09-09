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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSOLE = ROOT / "console"
OVERRIDE = CONSOLE / ".env.production.local"


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=value file, ignoring blanks and # comments."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def main() -> int:
    settings = _read_env_file(ROOT / "deploy" / "live-console.env")
    api_url, api_key = settings.get("LIVE_API"), settings.get("LIVE_KEY")
    if not api_url or not api_key:
        print(
            "deploy/live-console.env must define LIVE_API and LIVE_KEY. "
            "That file is gitignored on purpose; see deploy/HOSTING.md for the values."
        )
        return 2

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
