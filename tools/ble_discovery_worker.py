#!/usr/bin/env python3

import asyncio
import json
import os
import signal
import sys
from time import time

from bleak import BleakScanner
from bleak.exc import BleakError

SCAN_TIME = 8.0
SCAN_ERROR_BACKOFF = 2.0
LOST_AFTER = 30.0


def emit(payload):
    print(json.dumps(payload), flush=True)


class BLEDiscoveryWorker:
    def __init__(self, matchlist):
        self.matchlist = [m.lower().strip() for m in matchlist if m.strip()]
        self.stop_event = asyncio.Event()
        self.history = {}
        self.new_devices = []

    def stop(self):
        self.stop_event.set()

    @staticmethod
    def _normalize_name(device, adv):
        name = ((getattr(device, "name", None) or getattr(adv, "local_name", None) or "")).strip()
        return name

    def _matches(self, name):
        devname = name.lower()
        return any(devname.startswith(prefix) for prefix in self.matchlist)

    async def _handle_advert(self, device, adv):
        try:
            name = self._normalize_name(device, adv)
            if not name or not self._matches(name):
                return

            now = round(time(), 0)
            self.history[name] = {
                "address": getattr(device, "address", None),
                "last_seen": now,
            }
            if name not in self.new_devices:
                self.new_devices.append(name)
        except Exception as exc:
            emit({"error": f"callback error: {exc}"})

    def _callback(self, device, adv):
        asyncio.create_task(self._handle_advert(device, adv))

    async def run(self):
        while not self.stop_event.is_set():
            self.new_devices = []
            try:
                async with BleakScanner(detection_callback=self._callback, scanning_mode="active") as _scanner:
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=SCAN_TIME)
                    except asyncio.TimeoutError:
                        pass
            except BleakError as exc:
                emit({"error": str(exc)})
                await asyncio.sleep(SCAN_ERROR_BACKOFF)
                continue
            except OSError as exc:
                emit({"error": str(exc)})
                await asyncio.sleep(SCAN_ERROR_BACKOFF)
                continue
            except Exception as exc:
                emit({"error": str(exc)})
                await asyncio.sleep(SCAN_ERROR_BACKOFF)
                continue

            if self.new_devices:
                devices = []
                for name in self.new_devices:
                    info = self.history.get(name)
                    if not info:
                        continue
                    devices.append({"name": name, "address": info["address"]})
                if devices:
                    emit({"devices": devices})

            now = round(time(), 0)
            stale = [name for name, info in self.history.items() if now - info["last_seen"] > LOST_AFTER]
            for name in stale:
                del self.history[name]


async def amain(matchlist):
    worker = BLEDiscoveryWorker(matchlist)

    def _sigint_handler(*_args):
        worker.stop()

    signal.signal(signal.SIGINT, _sigint_handler)
    signal.signal(signal.SIGTERM, _sigint_handler)
    await worker.run()


def main():
    matchlist = [arg for arg in sys.argv[1:] if arg.strip()]
    asyncio.run(amain(matchlist))


if __name__ == "__main__":
    main()
