import json
import socket
import time
import gc

import network
from machine import Pin, UART

from bridge_config import CONFIG
from bridge_protocol import (
    MSG_ERROR,
    MSG_HELLO,
    MSG_LOG,
    MSG_MODBUS_REQUEST,
    MSG_MODBUS_RESPONSE,
    read_frame,
    write_frame,
)


def crc16_modbus(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def log(sock, message):
    write_frame(sock, MSG_LOG, message.encode("utf-8"))


def debug(message, sock=None):
    text = "BRIDGETRACE pico " + message
    print(text)
    if sock is not None:
        try:
            log(sock, text)
        except Exception:
            pass


def connect_wifi():
    debug("wifi activate")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        scan_results = wlan.scan()
        ssids = []
        for entry in scan_results:
            try:
                ssid = entry[0].decode("utf-8", errors="replace")
            except Exception:
                ssid = str(entry[0])
            ssids.append(ssid)
        debug("wifi scan ssids={}".format(ssids))
    except Exception as exc:
        debug("wifi scan failed {}".format(exc))
    if CONFIG.get("wifi_static_ip"):
        debug("wifi static ip {}".format(CONFIG["wifi_static_ip"]))
        wlan.ifconfig((
            CONFIG["wifi_static_ip"],
            CONFIG["wifi_netmask"],
            CONFIG["wifi_gateway"],
            CONFIG["wifi_dns"],
        ))
    if wlan.isconnected():
        debug("wifi already connected {}".format(wlan.ifconfig()))
        return wlan

    debug("wifi connect ssid={}".format(CONFIG["wifi_ssid"]))
    wlan.connect(CONFIG["wifi_ssid"], CONFIG["wifi_password"])
    deadline = time.ticks_add(time.ticks_ms(), CONFIG.get("wifi_timeout_s", 20) * 1000)
    last_status = None
    while not wlan.isconnected():
        try:
            status = wlan.status()
        except Exception:
            status = None
        if status != last_status:
            debug("wifi status {}".format(status))
            last_status = status
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError("wifi connect timeout status={}".format(status))
        time.sleep_ms(250)
    try:
        status = wlan.status()
    except Exception:
        status = None
    debug("wifi connected status={} {}".format(status, wlan.ifconfig()))
    return wlan


def open_uart():
    debug(
        "uart open id={} baud={} tx={} rx={}".format(
            CONFIG["uart_id"],
            CONFIG["uart_baudrate"],
            CONFIG["uart_tx_pin"],
            CONFIG["uart_rx_pin"],
        )
    )
    return UART(
        CONFIG["uart_id"],
        baudrate=CONFIG["uart_baudrate"],
        tx=Pin(CONFIG["uart_tx_pin"]),
        rx=Pin(CONFIG["uart_rx_pin"]),
        bits=8,
        parity=None,
        stop=1,
        timeout=100,
        timeout_char=20,
    )


def read_uart_exact(uart, size, timeout_ms):
    data = b""
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while len(data) < size:
        chunk = uart.read(size - len(data))
        if chunk:
            data += chunk
            continue
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError("uart read timeout")
        time.sleep_ms(10)
    return data


def read_modbus_response(uart, request, timeout_ms):
    header = read_uart_exact(uart, 2, timeout_ms)
    address = header[0]
    function = header[1]

    if function & 0x80:
        tail = read_uart_exact(uart, 3, timeout_ms)
        return header + tail

    if function in (3, 4):
        byte_count = read_uart_exact(uart, 1, timeout_ms)[0]
        tail = read_uart_exact(uart, byte_count + 2, timeout_ms)
        return header + bytes([byte_count]) + tail

    if function == 6:
        tail = read_uart_exact(uart, 6, timeout_ms)
        return header + tail

    tail = b""
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        chunk = uart.read()
        if chunk:
            tail += chunk
            deadline = time.ticks_add(time.ticks_ms(), 50)
        else:
            time.sleep_ms(10)
    return header + tail


def validate_crc(frame):
    if len(frame) < 4:
        return False
    expected = frame[-2] | (frame[-1] << 8)
    return crc16_modbus(frame[:-2]) == expected


def connect_server():
    server_list = CONFIG.get("server_list")
    if not server_list:
        legacy_host = CONFIG.get("server_host")
        server_list = [legacy_host] if legacy_host else []

    last_exc = None
    for server_host in server_list:
        try:
            addr = socket.getaddrinfo(server_host, CONFIG["server_port"])[0][-1]
            debug("server connect target={}:{} resolved={}".format(server_host, CONFIG["server_port"], addr))
            sock = socket.socket()
            try:
                sock.connect(addr)
                hello = {
                    "bridge_name": CONFIG["bridge_name"],
                    "server_host": server_host,
                    "server_port": CONFIG["server_port"],
                    "uart_baudrate": CONFIG["uart_baudrate"],
                }
                write_frame(sock, MSG_HELLO, json.dumps(hello).encode("utf-8"))
                debug("server hello sent bridge_name={}".format(CONFIG["bridge_name"]), sock)
                return sock
            except Exception:
                try:
                    sock.close()
                except Exception:
                    pass
                raise
        except Exception as exc:
            last_exc = exc
            debug("server connect failed target={}:{} exc={}".format(server_host, CONFIG["server_port"], exc))
            continue

    if last_exc is not None:
        raise last_exc
    raise OSError("no server hosts configured")


def health_server():
    addr = socket.getaddrinfo("0.0.0.0", CONFIG.get("health_port", 8766))[0][-1]
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(addr)
    server.listen(1)
    server.settimeout(0.2)
    debug("health server listen {}".format(addr))
    return server


def service_health(server, wlan):
    try:
        conn, addr = server.accept()
    except OSError:
        return

    try:
        payload = "ok bridge={} ip={}\n".format(CONFIG["bridge_name"], wlan.ifconfig()[0])
        conn.send(payload.encode("utf-8"))
    finally:
        conn.close()


def is_socket_timeout(exc):
    if not exc.args:
        return False
    code = exc.args[0]
    return code == "timed out" or code == 110


def bridge_loop(sock, uart):
    wlan = network.WLAN(network.STA_IF)
    health = health_server()
    try:
        sock.settimeout(0.2)
        while True:
            service_health(health, wlan)
            try:
                message_type, payload = read_frame(sock)
            except OSError as exc:
                if is_socket_timeout(exc):
                    continue
                raise
            if message_type != MSG_MODBUS_REQUEST:
                raise OSError("unexpected request type")
            debug("modbus request {} bytes {}".format(len(payload), payload.hex()), sock)

            try:
                while uart.read():
                    pass

                uart.write(payload)
                response = read_modbus_response(uart, payload, CONFIG["modbus_timeout_ms"])
                if not validate_crc(response):
                    raise OSError("bad modbus crc in response")
                debug("modbus response {} bytes {}".format(len(response), response.hex()), sock)
                write_frame(sock, MSG_MODBUS_RESPONSE, response)
            except Exception as exc:
                debug("request exception {}".format(exc), sock)
                write_frame(sock, MSG_ERROR, str(exc).encode("utf-8"))
    finally:
        try:
            health.close()
        except Exception:
            pass


def main():
    while True:
        sock = None
        try:
            debug("main loop begin")
            connect_wifi()
            uart = open_uart()
            sock = connect_server()
            debug("bridge connected", sock)
            bridge_loop(sock, uart)
        except Exception as exc:
            debug("exception {}".format(exc), sock)
            if sock is not None:
                try:
                    write_frame(sock, MSG_ERROR, str(exc).encode("utf-8"))
                except Exception:
                    pass
                try:
                    sock.close()
                except Exception:
                    pass
            gc.collect()
            time.sleep(3)
