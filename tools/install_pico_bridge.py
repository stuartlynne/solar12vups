#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import argparse
import glob
import json
import os
import subprocess
import tempfile


CONFIG_TEMPLATE = """CONFIG = {{
    "bridge_name": "{bridge_name}",
    "wifi_ssid": "{wifi_ssid}",
    "wifi_password": "{wifi_password}",
    "wifi_static_ip": {wifi_static_ip},
    "wifi_netmask": "{wifi_netmask}",
    "wifi_gateway": "{wifi_gateway}",
    "wifi_dns": "{wifi_dns}",
    "server_list": {server_list},
    "server_port": {server_port},
    "health_port": {health_port},
    "uart_id": {uart_id},
    "uart_baudrate": {uart_baudrate},
    "uart_tx_pin": {uart_tx_pin},
    "uart_rx_pin": {uart_rx_pin},
    "modbus_timeout_ms": {modbus_timeout_ms},
    "wifi_timeout_s": {wifi_timeout_s},
}}
"""


def run_mpremote(args):
    subprocess.run(["mpremote"] + args, check=True)


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

    # De-duplicate while preserving order.
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
            "Multiple MicroPython serial devices found. "
            "Specify --connect explicitly.\n  " + "\n  ".join(unique_matches)
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
    parser = argparse.ArgumentParser(description="Install the Solar12VUPS Pico bridge via mpremote")
    parser.add_argument("--connect", default="auto", help="mpremote connect target, e.g. /dev/ttyACM0")
    parser.add_argument("--bridge-name", required=True)
    parser.add_argument("--wifi-ssid", required=True)
    parser.add_argument("--wifi-password", required=True)
    parser.add_argument("--wifi-static-ip")
    parser.add_argument("--wifi-netmask", default="255.255.255.0")
    parser.add_argument("--wifi-gateway", default="192.168.1.1")
    parser.add_argument("--wifi-dns", default="192.168.1.1")
    parser.add_argument("--server-list", nargs="+", required=True)
    parser.add_argument("--server-port", type=int, default=9765)
    parser.add_argument("--health-port", type=int, default=8766)
    parser.add_argument("--uart-id", type=int, default=0)
    parser.add_argument("--uart-baudrate", type=int, default=9600)
    parser.add_argument("--uart-tx-pin", type=int, default=0)
    parser.add_argument("--uart-rx-pin", type=int, default=1)
    parser.add_argument("--modbus-timeout-ms", type=int, default=1500)
    parser.add_argument("--wifi-timeout-s", type=int, default=20)
    parser.add_argument("--soft-reset", action="store_true")
    args = parser.parse_args()
    args.connect = detect_connect_target(args.connect)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pico_dir = os.path.join(repo_root, "pico")

    rendered_config = CONFIG_TEMPLATE.format(
        bridge_name=args.bridge_name,
        wifi_ssid=args.wifi_ssid,
        wifi_password=args.wifi_password,
        wifi_static_ip=repr(args.wifi_static_ip),
        wifi_netmask=args.wifi_netmask,
        wifi_gateway=args.wifi_gateway,
        wifi_dns=args.wifi_dns,
        server_list=json.dumps(args.server_list),
        server_port=args.server_port,
        health_port=args.health_port,
        uart_id=args.uart_id,
        uart_baudrate=args.uart_baudrate,
        uart_tx_pin=args.uart_tx_pin,
        uart_rx_pin=args.uart_rx_pin,
        modbus_timeout_ms=args.modbus_timeout_ms,
        wifi_timeout_s=args.wifi_timeout_s,
    )

    with tempfile.NamedTemporaryFile("w", delete=False, suffix="_bridge_config.py") as tmp:
        tmp.write(rendered_config)
        config_path = tmp.name

    try:
        run_mpremote(["connect", args.connect, "fs", "cp", os.path.join(pico_dir, "bridge_protocol.py"), ":bridge_protocol.py"])
        run_mpremote(["connect", args.connect, "fs", "cp", os.path.join(pico_dir, "bridge.py"), ":bridge.py"])
        run_mpremote(["connect", args.connect, "fs", "cp", config_path, ":bridge_config.py"])
        run_mpremote(["connect", args.connect, "fs", "cp", os.path.join(pico_dir, "main.py"), ":main.py"])
        if args.soft_reset:
            run_mpremote(["connect", args.connect, "soft-reset"])
    finally:
        os.unlink(config_path)


if __name__ == "__main__":
    main()
