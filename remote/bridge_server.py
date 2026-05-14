#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import asyncio
import json

from remote.bridge_protocol import (
    MSG_ERROR,
    MSG_HELLO,
    MSG_LOG,
    MSG_MODBUS_REQUEST,
    MSG_MODBUS_RESPONSE,
    read_frame,
    write_frame,
)

import logging
from lib.log import xreport

logger = logging.getLogger(__name__)


class BridgeConnection:
    def __init__(self, hub, reader, writer):
        self.hub = hub
        self.reader = reader
        self.writer = writer
        self.peername = writer.get_extra_info("peername")
        self.bridge_name = None
        self.hello = {}
        self.request_lock = asyncio.Lock()
        self.response_queue = asyncio.Queue()

    async def run(self):
        message_type, payload = await read_frame(self.reader)
        if message_type != MSG_HELLO:
            raise ValueError(f"Expected HELLO frame, got type {message_type}")

        self.hello = json.loads(payload.decode("utf-8"))
        self.bridge_name = self.hello["bridge_name"]
        await self.hub.register(self)
        xreport("BridgeServer", self.bridge_name, f"connected from {self.peername}", green=True)
        logger.info("BRIDGETRACE host hello bridge=%s peer=%s hello=%r", self.bridge_name, self.peername, self.hello)

        try:
            while True:
                message_type, payload = await read_frame(self.reader)
                if message_type == MSG_LOG:
                    logger.info("bridge[%s] %s", self.bridge_name, payload.decode("utf-8", errors="replace"))
                    continue
                if message_type in (MSG_MODBUS_RESPONSE, MSG_ERROR):
                    await self.response_queue.put((message_type, payload))
                    continue
                raise ValueError(f"Unexpected unsolicited message type {message_type} from {self.bridge_name}")
        finally:
            await self.hub.unregister(self)
            self.writer.close()
            await self.writer.wait_closed()
            xreport("BridgeServer", self.bridge_name or "unknown", "disconnected", yellow=True)

    async def send_request(self, payload, timeout=5.0):
        async with self.request_lock:
            logger.info("BRIDGETRACE host send_request bridge=%s bytes=%d hex=%s", self.bridge_name, len(payload), payload.hex())
            await write_frame(self.writer, MSG_MODBUS_REQUEST, payload)
            message_type, response_payload = await asyncio.wait_for(self.response_queue.get(), timeout=timeout)
            if message_type == MSG_MODBUS_RESPONSE:
                logger.info("BRIDGETRACE host recv_response bridge=%s bytes=%d hex=%s", self.bridge_name, len(response_payload), response_payload.hex())
                return response_payload
            if message_type == MSG_ERROR:
                logger.info("BRIDGETRACE host recv_error bridge=%s payload=%r", self.bridge_name, response_payload)
                raise RuntimeError(response_payload.decode("utf-8", errors="replace"))
            raise ValueError(f"Unexpected response frame type {message_type} from {self.bridge_name}")


class BridgeHub:
    def __init__(self):
        self.connections = {}
        self.connection_event = asyncio.Event()
        self.on_register = None
        self.on_unregister = None

    async def register(self, connection):
        existing = self.connections.get(connection.bridge_name)
        if existing is not None and existing is not connection:
            existing.writer.close()
        self.connections[connection.bridge_name] = connection
        self.connection_event.set()
        logger.info("BridgeHub registered %s", connection.bridge_name)
        if self.on_register is not None:
            try:
                self.on_register(connection.bridge_name)
            except Exception:
                logger.exception("BridgeHub on_register callback failed for %s", connection.bridge_name)

    async def unregister(self, connection):
        if self.connections.get(connection.bridge_name) is connection:
            self.connections.pop(connection.bridge_name, None)
            logger.info("BridgeHub unregistered %s", connection.bridge_name)
            if self.on_unregister is not None:
                try:
                    self.on_unregister(connection.bridge_name)
                except Exception:
                    logger.exception("BridgeHub on_unregister callback failed for %s", connection.bridge_name)

    def bridge_names(self):
        return sorted(self.connections.keys())

    def has_bridge(self, bridge_name):
        return bridge_name in self.connections

    async def wait_for_bridge(self, bridge_name, timeout=None):
        if self.has_bridge(bridge_name):
            return self.connections[bridge_name]

        while True:
            self.connection_event.clear()
            await asyncio.wait_for(self.connection_event.wait(), timeout=timeout)
            if self.has_bridge(bridge_name):
                return self.connections[bridge_name]

    async def send_request(self, bridge_name, payload, timeout=5.0):
        connection = await self.wait_for_bridge(bridge_name, timeout=timeout)
        return await connection.send_request(payload, timeout=timeout)


async def serve_bridge_client(hub, reader, writer):
    connection = BridgeConnection(hub, reader, writer)
    try:
        await connection.run()
    except asyncio.IncompleteReadError:
        logger.info("bridge client closed before full frame: %s", connection.peername)
    except Exception as exc:
        logger.exception("bridge client error: %s", exc)
        try:
            await write_frame(writer, MSG_ERROR, str(exc).encode("utf-8"))
        except Exception:
            pass
        writer.close()
        await writer.wait_closed()


async def start_bridge_server(hub, host="0.0.0.0", port=9765):
    return await asyncio.start_server(lambda r, w: serve_bridge_client(hub, r, w), host, port)


async def run_bridge_server(host="0.0.0.0", port=9765):
    hub = BridgeHub()
    server = await start_bridge_server(hub, host=host, port=port)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    xreport("BridgeServer", "listen", sockets, green=True)
    async with server:
        await server.serve_forever()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Solar12VUPS remote bridge server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9765)
    args = parser.parse_args()

    from lib.log import setup_logger

    setup_logger(stderr=True)
    asyncio.run(run_bridge_server(host=args.host, port=args.port))


if __name__ == "__main__":
    main()
