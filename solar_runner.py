#!/usr/bin/env python3
# -*- coding: utf-8 -*-


"""Convenience wrapper for running bootstrap directly from source tree."""
import sys
import argparse
from lib.log import setup_logger
from app.solar12vups import SolarMain
import matplotlib
matplotlib.use('TkAgg')


def main():
    parser = argparse.ArgumentParser(description="Solar12VUPS runner")
    parser.add_argument("--stderr", action="store_true", help="Enable console logging to stderr")
    parser.add_argument("--no-ble", action="store_true", help="Start only the Tkinter GUI, disabling BLE/discovery/bridge threads")
    parser.add_argument("--bleio-only", action="store_true", help="Start Tkinter with only the BLE data I/O process enabled, but no BLE/discovery threads")
    parser.add_argument("--ble-thread-only", action="store_true", help="Start Tkinter plus the BLE main thread shell, but skip discovery, remote bridge, and device tasks")
    args = parser.parse_args()

    setup_logger(stderr=args.stderr)
    enable_ble = not args.no_ble and not args.bleio_only and not args.ble_thread_only
    enable_bleio = enable_ble or args.bleio_only or args.ble_thread_only
    SolarMain(enable_ble=enable_ble, enable_bleio=enable_bleio, ble_thread_only=args.ble_thread_only)

if __name__ == "__main__":
    main()
