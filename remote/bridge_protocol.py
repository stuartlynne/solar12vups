#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import asyncio
import json
import struct


MSG_HELLO = 1
MSG_MODBUS_REQUEST = 2
MSG_MODBUS_RESPONSE = 3
MSG_LOG = 4
MSG_ERROR = 5

HEADER_STRUCT = struct.Struct(">BH")


def encode_frame(message_type, payload):
    return HEADER_STRUCT.pack(message_type, len(payload)) + payload


def encode_json_frame(message_type, payload):
    return encode_frame(message_type, json.dumps(payload).encode("utf-8"))


async def read_exactly(reader, size):
    return await reader.readexactly(size)


async def read_frame(reader):
    header = await read_exactly(reader, HEADER_STRUCT.size)
    message_type, payload_length = HEADER_STRUCT.unpack(header)
    payload = await read_exactly(reader, payload_length)
    return message_type, payload


async def write_frame(writer, message_type, payload):
    writer.write(encode_frame(message_type, payload))
    await writer.drain()


async def write_json_frame(writer, message_type, payload):
    await write_frame(writer, message_type, json.dumps(payload).encode("utf-8"))

