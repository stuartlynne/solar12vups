import struct


MSG_HELLO = 1
MSG_MODBUS_REQUEST = 2
MSG_MODBUS_RESPONSE = 3
MSG_LOG = 4
MSG_ERROR = 5

HEADER_FORMAT = ">BH"
HEADER_SIZE = 3


def encode_frame(message_type, payload):
    return struct.pack(HEADER_FORMAT, message_type, len(payload)) + payload


def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("socket closed")
        data += chunk
    return data


def read_frame(sock):
    header = recv_exact(sock, HEADER_SIZE)
    message_type, payload_length = struct.unpack(HEADER_FORMAT, header)
    payload = recv_exact(sock, payload_length)
    return message_type, payload


def write_frame(sock, message_type, payload):
    sock.sendall(encode_frame(message_type, payload))
