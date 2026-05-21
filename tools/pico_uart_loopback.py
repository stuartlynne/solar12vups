#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import argparse
import subprocess
import sys


DEVICE_SNIPPET = r"""
from machine import Pin, UART
import sys
import time

uart = UART(
    {uart_id},
    baudrate={baudrate},
    tx=Pin({tx_pin}),
    rx=Pin({rx_pin}),
    bits=8,
    parity=None,
    stop=1,
    timeout=100,
    timeout_char=20,
)

while uart.read():
    pass

payload = {payload!r}
uart.write(payload)
deadline = time.ticks_add(time.ticks_ms(), {timeout_ms})
data = b""
while len(data) < len(payload):
    chunk = uart.read(len(payload) - len(data))
    if chunk:
        data += chunk
        continue
    if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
        break
    time.sleep_ms(10)

sys.stdout.write("sent=" + payload.hex() + "\n")
sys.stdout.write("recv=" + data.hex() + "\n")
sys.stdout.write("ok=" + ("1" if data == payload else "0") + "\n")
"""


def main():
    parser = argparse.ArgumentParser(description="Run a UART loopback test on a Pico via mpremote")
    parser.add_argument("--connect", default="/dev/ttyACM0", help="mpremote connect target")
    parser.add_argument("--uart-id", type=int, default=0)
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--tx-pin", type=int, default=0)
    parser.add_argument("--rx-pin", type=int, default=1)
    parser.add_argument("--payload", default="UartLoopback123")
    parser.add_argument("--timeout-ms", type=int, default=1500)
    args = parser.parse_args()

    snippet = DEVICE_SNIPPET.format(
        uart_id=args.uart_id,
        baudrate=args.baudrate,
        tx_pin=args.tx_pin,
        rx_pin=args.rx_pin,
        payload=args.payload.encode("utf-8"),
        timeout_ms=args.timeout_ms,
    )

    proc = subprocess.run(
        ["mpremote", "connect", args.connect, "resume", "exec", snippet],
        capture_output=True,
        text=True,
    )

    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)

    ok = None
    for line in proc.stdout.splitlines():
        if line.startswith("ok="):
            ok = line.split("=", 1)[1].strip()
            break

    if ok != "1":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
