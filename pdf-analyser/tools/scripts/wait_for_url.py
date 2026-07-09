#!/usr/bin/env python3
import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(args.url, timeout=10) as response:
                body = response.read().decode("utf-8", errors="replace")
                if 200 <= response.status < 300:
                    print(body)
                    return 0
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(args.interval)

    print(json.dumps({"status": "timeout", "url": args.url, "last_error": last_error}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
