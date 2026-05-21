# Pico W Serial Bridge

This document describes the first-pass remote bridge for `solar12vups` using a Raspberry Pi Pico W as a direct serial bridge to the Renogy controller.

## Goal

The Pico W runs MicroPython, connects to WiFi, opens a TCP connection back to the `solar12vups` bridge server, and forwards raw Modbus RTU request/response bytes between TCP and the Renogy controller over UART.

The current design deliberately keeps Modbus RTU frames intact end to end:

- `solar12vups` builds the RTU request bytes
- the TCP bridge transports those bytes unchanged
- the Pico writes them to UART
- the Pico reads the RTU response bytes and sends them back unchanged

This is RTU-over-TCP framing, not Modbus TCP.

## Current Hardware Assumption

Based on [pico-serial-notes.md](/home/sl/work25/solarups/solar12vups/pico-serial-notes.md), the current working assumption is:

- the Wanderer 10A RJ12 serial port is not true +/- RS232 level signaling
- the controller TX line may be approximately 5V logic
- the Pico TX can likely drive the controller RX directly
- the controller TX into Pico RX should be level-reduced before connecting to GPIO 1

The current preferred first test path is therefore direct Pico UART wiring with a resistor divider on Pico RX, not the RS232 HAT.

The notes currently map:

- Pico GPIO 0 / UART0 TX -> RJ12 pin 2 (controller RX)
- Pico GND -> RJ12 pin 3 (controller GND)
- RJ12 pin 1 (controller TX) -> resistor divider -> Pico GPIO 1 / UART0 RX

See [pico-serial-notes.md](/home/sl/work25/solarups/solar12vups/pico-serial-notes.md) for the sketch.

## Pico W References

Primary references used for this design:

- MicroPython `network.WLAN` docs: <https://docs.micropython.org/en/latest/library/network.WLAN.html>
- MicroPython `machine.UART` docs: <https://docs.micropython.org/en/latest/library/machine.UART.html>
- MicroPython socket docs: <https://docs.micropython.org/en/latest/library/socket.html>
- MicroPython boot sequence (`boot.py`, `main.py`): <https://docs.micropython.org/en/latest/reference/reset_boot.html>
- `mpremote` docs: <https://docs.micropython.org/en/latest/reference/mpremote.html>
- Raspberry Pi Pico W product page: <https://www.raspberrypi.com/products/raspberry-pi-pico-w/>

Notes:

- `mpremote` is the current MicroPython deployment tool to prefer over `pyboard.py`.
- The current bridge app uses only built-in MicroPython modules: `network`, `socket`, `machine`, `time`, `json`.

## Host-Side Pieces

Added Python package:

- [remote/bridge_protocol.py](/home/sl/work25/solarups/solar12vups/remote/bridge_protocol.py)
- [remote/bridge_server.py](/home/sl/work25/solarups/solar12vups/remote/bridge_server.py)
- [remote/session.py](/home/sl/work25/solarups/solar12vups/remote/session.py)
- [remote/task.py](/home/sl/work25/solarups/solar12vups/remote/task.py)

What they do:

- `bridge_server.py` accepts Pico bridge TCP connections on a known port, default `9765`
- `session.py` polls a remote Renogy controller using the same register schedule used by the BLE path
- `task.py` keeps the server running and starts a polling session for each connected bridge

## Pico Files

Added MicroPython-side files:

- [pico/bridge.py](/home/sl/work25/solarups/solar12vups/pico/bridge.py)
- [pico/bridge_protocol.py](/home/sl/work25/solarups/solar12vups/pico/bridge_protocol.py)
- [pico/main.py](/home/sl/work25/solarups/solar12vups/pico/main.py)
- [pico/bridge_config.py.example](/home/sl/work25/solarups/solar12vups/pico/bridge_config.py.example)

Board-specific configuration lives in `bridge_config.py` and includes:

- `bridge_name`
- `wifi_ssid`
- `wifi_password`
- `wifi_static_ip` (optional)
- `wifi_netmask`
- `wifi_gateway`
- `wifi_dns`
- `server_host`
- `server_port`
- `health_port`
- `uart_id`
- `uart_baudrate`
- `uart_tx_pin`
- `uart_rx_pin`

The `bridge_name` is what `solar12vups` will use as the device identity for the remote box.

Current defaults match the note above:

- `uart_id=0`
- `uart_tx_pin=0`
- `uart_rx_pin=1`
- `uart_baudrate=9600`
- `health_port=8766`

## Install Workflow

Install MicroPython on the Pico W first. Once the board appears as a serial device, deploy the bridge files with `mpremote`.

Helper script:

- [tools/install_pico_bridge.py](/home/sl/work25/solarups/solar12vups/tools/install_pico_bridge.py)
- [pico/Makefile](/home/sl/work25/solarups/solar12vups/pico/Makefile)

Example:

```bash
python3 tools/install_pico_bridge.py \
  --connect /dev/ttyACM0 \
  --bridge-name remote-reader-1 \
  --wifi-ssid YOUR_SSID \
  --wifi-password YOUR_PASSWORD \
  --wifi-static-ip 192.168.40.81 \
  --wifi-gateway 192.168.40.1 \
  --wifi-dns 192.168.40.1 \
  --server-host 192.168.40.10 \
  --server-port 9765 \
  --health-port 8766 \
  --uart-id 0 \
  --uart-baudrate 9600 \
  --uart-tx-pin 0 \
  --uart-rx-pin 1 \
  --soft-reset
```

This copies:

- `bridge_protocol.py`
- `bridge.py`
- rendered `bridge_config.py`
- `main.py`

to the device filesystem and optionally soft-resets the board.

## Debug vs Deploy

There are two distinct modes:

- `deploy`: board auto-runs the bridge on power-up, reset, or replug because `main.py` is installed
- `debug`: board does not auto-run the bridge because `main.py` is removed after install

From the repo root:

```bash
make -C pico deploy
make -C pico debug
make -C pico status
```

Switching between them is just switching whether `:main.py` exists on the Pico filesystem.

Useful Pico targets:

- `make -C pico deploy`: install config and auto-run on reset
- `make -C pico deplay`: alias for `deploy`
- `make -C pico debug`: install config, then remove `main.py`
- `make -C pico run`: manually start the bridge in debug mode
- `make -C pico soft-reset`: restart the board
- `make -C pico ping`: test the TCP health port

## Seeing stdout/stderr in Deployed Mode

Yes. In deployed mode, `print()` output from `main.py` and `bridge.py` still goes out over the USB CDC serial console while the bridge is auto-running.

There are two ways to attach:

- `make -C pico console`: attach with `mpremote` without forcing a soft reset
- `make -C pico monitor`: open a raw USB serial monitor

The raw monitor is better if the board is already running and you just want to watch logs:

```bash
make -C pico monitor
```

That uses `python3 -m serial.tools.miniterm /dev/ttyACM0 115200`. On MicroPython USB CDC, the baud rate is not materially important, but `115200` is a conventional setting for the tool.

To exit the raw monitor, use `Ctrl-]`.

## Local Development Test Loop

1. Run `solar12vups` on the dev box.
2. Ensure the remote bridge server is running inside the app.
3. Connect the Pico W over USB and deploy with `mpremote`.
4. Wire the Pico UART directly to the Renogy cable, with level reduction on Pico RX.
5. Watch `stderr.txt` or stderr logs for bridge connect events and remote device updates.

For direct MicroPython interaction:

```bash
mpremote connect /dev/ttyACM0 repl
```

or soft reset:

```bash
mpremote connect /dev/ttyACM0 soft-reset
```

If the bridge is already running and you do not want `mpremote` to reset the board, use:

```bash
mpremote connect /dev/ttyACM0 resume repl
```

For a simple host-side reachability test once the Pico is on WiFi:

```bash
python3 tools/pingpico.py 192.168.40.81
```

Expected reply shape:

```text
pingpico: ok host=192.168.40.81 port=8766 ms=12.3 reply=ok bridge=pico-192-168-40-81 ip=192.168.40.81
```

## Wiring Reminder

Before power-up, verify the Renogy cable pinout and actual electrical levels on the actual controller with a meter or scope if possible.

Software assumes:

- the Renogy side is wired to the correct TX/RX/GND pins
- Pico RX is not exposed directly to a 5V signal without level reduction
- Pico TX is acceptable to the controller RX input

If direct UART does not work or measured levels show true RS232 signaling, fall back to the RS232 HAT design.

That hardware verification is still the main risk item before live testing.
