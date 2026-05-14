#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import argparse
import glob
import os
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

payload = bytes.fromhex({payload_hex!r})
uart.write(payload)
deadline = time.ticks_add(time.ticks_ms(), {timeout_ms})
data = b""

while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    chunk = uart.read()
    if chunk:
        data += chunk
        deadline = time.ticks_add(time.ticks_ms(), 80)
    else:
        time.sleep_ms(10)

sys.stdout.write("sent=" + payload.hex() + "\n")
sys.stdout.write("recv=" + data.hex() + "\n")
sys.stdout.write("recv_len=" + str(len(data)) + "\n")
"""


def detect_connect_target(connect_target):
    if connect_target != "auto":
        return connect_target

    patterns = [
        "/dev/serial/by-id/usb-MicroPython_Board_in_*",
        "/dev/serial/by-id/usb-MicroPython_*",
    ]
    matches = []
    for pattern in patterns:
        matches.extend(sorted(glob.glob(pattern)))

    unique_matches = []
    seen = set()
    for match in matches:
        real = os.path.realpath(match)
        if real in seen:
            continue
        seen.add(real)
        unique_matches.append(match)

    if len(unique_matches) == 1:
        return unique_matches[0]
    if len(unique_matches) > 1:
        raise SystemExit(
            "Multiple MicroPython serial devices found. Specify --connect explicitly.\n  "
            + "\n  ".join(unique_matches)
        )

    tty_matches = sorted(glob.glob("/dev/ttyACM*"))
    if len(tty_matches) == 1:
        return tty_matches[0]
    if len(tty_matches) > 1:
        raise SystemExit(
            "Multiple ttyACM devices found and no unique MicroPython by-id match exists. "
            "Specify --connect explicitly.\n  " + "\n  ".join(tty_matches)
        )
    raise SystemExit("No MicroPython serial device found. Specify --connect explicitly.")


def main():
    parser = argparse.ArgumentParser(description="Send one raw Modbus RTU request from a Pico UART and print raw bytes returned")
    parser.add_argument("--connect", default="auto", help="mpremote connect target")
    parser.add_argument("--uart-id", type=int, default=0)
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--tx-pin", type=int, default=0)
    parser.add_argument("--rx-pin", type=int, default=1)
    parser.add_argument("--request-hex", default="ff03001a0001b013")
    parser.add_argument("--timeout-ms", type=int, default=1500)
    args = parser.parse_args()

    connect = detect_connect_target(args.connect)
    snippet = DEVICE_SNIPPET.format(
        uart_id=args.uart_id,
        baudrate=args.baudrate,
        tx_pin=args.tx_pin,
        rx_pin=args.rx_pin,
        payload_hex=args.request_hex,
        timeout_ms=args.timeout_ms,
    )

    proc = subprocess.run(
        ["mpremote", "connect", connect, "resume", "exec", snippet],
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
