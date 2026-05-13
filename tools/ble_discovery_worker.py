#!/usr/bin/env python3

import asyncio
import json
import sys
from bleak import BleakScanner


async def scan_once(matchlist):
    devices = await BleakScanner.discover(
        timeout=10.0,
        return_adv=True,
        scanning_mode="active",
    )
    matches = []
    for _key, value in devices.items():
        dev, adv = value
        name = ((dev.name or adv.local_name or '')).strip()
        if not name:
            continue
        devname = name.lower()
        if not any(devname.startswith(prefix) for prefix in matchlist):
            continue
        matches.append({'name': name, 'address': dev.address})
    return matches


def emit(payload):
    print(json.dumps(payload), flush=True)


def main():
    matchlist = [arg.lower().strip() for arg in sys.argv[1:] if arg.strip()]
    while True:
        try:
            emit({'devices': asyncio.run(scan_once(matchlist))})
        except KeyboardInterrupt:
            return
        except Exception as e:
            emit({'error': str(e)})


if __name__ == '__main__':
    main()
