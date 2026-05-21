#!/usr/bin/env python3
# -*- coding: utf-8 -*-


"""Convenience wrapper for running bootstrap directly from source tree."""
import sys
import argparse
from lib.log import setup_logger
from app.solar12vups import SolarMain
import matplotlib
matplotlib.use('TkAgg')
import os
from app import install_desktop as desktop_installer


def main():
    parser = argparse.ArgumentParser(description="Solar12VUPS runner")
    parser.add_argument("--stderr", action="store_true", help="Enable console logging to stderr")
    parser.add_argument("--add-desktop-icon", action="store_true",
                        help="Create a Desktop shortcut and optional menu entry.\n"
                             "Run as normal user for per-user install (~/.local); run as root to install to system.")
    parser.add_argument("--menu", action="store_true",
                        help="Also add an application menu entry (user or system depending on privileges).")
    parser.add_argument("--system", action="store_true",
                        help="Force system-wide menu entry (requires root).")
    parser.add_argument("--no-ble", action="store_true", help="Start only the Tkinter GUI, disabling BLE/discovery/bridge threads")
    parser.add_argument("--bleio-only", action="store_true", help="Start Tkinter with only the BLE data I/O process enabled, but no BLE/discovery threads")
    parser.add_argument("--ble-thread-only", action="store_true", help="Start Tkinter plus the BLE main thread shell, but skip discovery, remote bridge, and device tasks")
    args = parser.parse_args()
    print(args)

    if args.add_desktop_icon or args.menu or args.system:
        # Build argv for installer module
        installer_args = []
        if args.menu:
            installer_args.append('--menu')
        if args.system:
            installer_args.append('--system')
        desktop_installer.main(installer_args)
        return

    setup_logger(stderr=args.stderr)
    enable_ble = not args.no_ble and not args.bleio_only and not args.ble_thread_only
    enable_bleio = enable_ble or args.bleio_only or args.ble_thread_only
    SolarMain(enable_ble=enable_ble, enable_bleio=enable_bleio, ble_thread_only=args.ble_thread_only)

if __name__ == "__main__":
    main()
