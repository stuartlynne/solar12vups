#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import asyncio
from queue import Queue

from remote.bridge_server import BridgeHub, start_bridge_server
from remote.session import RemoteBtThSession

import logging
from lib.log import xreport

logger = logging.getLogger(__name__)

DEFAULT_REMOTE_PORT = 9765
DEFAULT_REMOTE_HOST = "0.0.0.0"


async def remote_server_task(active=None, shutdown=None, aevents=None, controlQueues=None, dataQueue=None, host=DEFAULT_REMOTE_HOST, port=DEFAULT_REMOTE_PORT):
    controlQueues = controlQueues if controlQueues is not None else {}
    hub = BridgeHub()
    sessions = {}
    session_objs = {}

    def on_bridge_registered(bridge_name):
        session = session_objs.get(bridge_name)
        if session is not None:
            session.force_identity_refresh()
            session.emit_status("Pico bridge connected. Waiting for Wanderer response.", level="info")

    def on_bridge_unregistered(bridge_name):
        session = session_objs.get(bridge_name)
        if session is not None:
            session.emit_status("Pico bridge disconnected from host.", level="error")

    hub.on_register = on_bridge_registered
    hub.on_unregister = on_bridge_unregistered
    server = await start_bridge_server(hub, host=host, port=port)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    xreport("RemoteServer", "listen", sockets, green=True)

    async with server:
        while not aevents.is_shutdown():
            for bridge_name in hub.bridge_names():
                task = sessions.get(bridge_name)
                if task is None or task.done():
                    control_queue = controlQueues.get(bridge_name.lower())
                    if control_queue is None:
                        control_queue = Queue()
                        controlQueues[bridge_name.lower()] = control_queue
                    session = RemoteBtThSession(
                        bridge_name=bridge_name,
                        hub=hub,
                        aevents=aevents,
                        controlQueue=control_queue,
                        dataQueue=dataQueue,
                    )
                    session_objs[bridge_name] = session
                    sessions[bridge_name] = asyncio.create_task(session.run(), name=f"remote-{bridge_name}")
                    xreport("RemoteServer", bridge_name, "session started", blue=True)

            finished = [name for name, task in sessions.items() if task.done() and not hub.has_bridge(name)]
            for bridge_name in finished:
                sessions.pop(bridge_name, None)
                session_objs.pop(bridge_name, None)

            try:
                hub.connection_event.clear()
                await asyncio.wait_for(hub.connection_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    for task in sessions.values():
        task.cancel()
    await asyncio.gather(*sessions.values(), return_exceptions=True)
