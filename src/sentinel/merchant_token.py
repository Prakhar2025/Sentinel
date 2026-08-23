"""CLI entry point: python -m sentinel.merchant_token MERCHANT_ID [TTL]."""

import sys

from sentinel.auth import issue_token
from sentinel.config import get_settings

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m sentinel.merchant_token MERCHANT_ID [TTL_SECONDS]")
    merchant_id = sys.argv[1]
    ttl = int(sys.argv[2]) if len(sys.argv) > 2 else 24 * 3600
    token = issue_token(get_settings().jwt_secret, merchant_id, ttl)
    print(token)
