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
    SolarMain()

if __name__ == "__main__":
    main()
