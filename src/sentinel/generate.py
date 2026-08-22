"""CLI entry point: python -m sentinel.generate --seed 42."""

from sentinel.data.generate import main

if __name__ == "__main__":
    raise SystemExit(main())
