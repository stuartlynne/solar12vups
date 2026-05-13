#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import argparse
import socket
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="Check Pico bridge TCP health endpoint")
    parser.add_argument("host", help="Pico IP or hostname")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    started = time.monotonic()
    try:
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
            sock.settimeout(args.timeout)
            payload = sock.recv(4096).decode("utf-8", errors="replace").strip()
    except Exception as exc:
        print(f"pingpico: fail host={args.host} port={args.port} error={exc}", file=sys.stderr)
        raise SystemExit(1)

    elapsed_ms = (time.monotonic() - started) * 1000.0
    print(f"pingpico: ok host={args.host} port={args.port} ms={elapsed_ms:.1f} reply={payload}")


if __name__ == "__main__":
    main()

