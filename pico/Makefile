PORT ?= auto
BRIDGE_NAME ?= pico-192-168-40-81
WIFI_SSID ?= wimsey
WIFI_PASSWORD ?= aa.bb.cc.dd
WIFI_STATIC_IP ?= 192.168.40.81
WIFI_NETMASK ?= 255.255.255.0
WIFI_GATEWAY ?= 192.168.40.1
WIFI_DNS ?= 192.168.40.1
SERVER_HOST ?= 192.168.40.16
SERVER_PORT ?= 9765
HEALTH_PORT ?= 8766
UART_ID ?= 0
UART_BAUDRATE ?= 9600
UART_TX_PIN ?= 0
UART_RX_PIN ?= 1

ROOT := ..
INSTALL := python3 $(ROOT)/tools/install_pico_bridge.py
PING := python3 $(ROOT)/tools/pingpico.py
LOOPBACK := python3 $(ROOT)/tools/pico_uart_loopback.py
MPREMOTE := mpremote connect $(PORT)
MINITERM := python3 -m serial.tools.miniterm $(PORT) 115200

.PHONY: help debug deploy deplay ping loopback console monitor logs repl reset soft-reset ls config stop clean-main run status

help:
	@echo "Targets:"
	@echo "  make debug      - install bridge files/config, remove main.py, and reset into non-auto-run debug mode"
	@echo "  make deploy     - install bridge files/config and main.py so it auto-runs on reset"
	@echo "  make deplay     - alias for deploy"
	@echo "  make ping       - probe Pico TCP health endpoint"
	@echo "  make loopback   - send bytes on UART TX and verify they arrive on UART RX"
	@echo "  make console    - attach to running device without soft-reset using mpremote"
	@echo "  make monitor    - raw USB serial monitor for deployed-mode stdout/stderr"
	@echo "  make logs       - alias for monitor"
	@echo "  make repl       - attach normal REPL"
	@echo "  make run        - start bridge manually from current REPL state without installing main.py"
	@echo "  make stop       - interrupt a running script"
	@echo "  make soft-reset - soft reset the board"
	@echo "  make reset      - hard reset the board"
	@echo "  make ls         - list files on the Pico"
	@echo "  make config     - print installed bridge config"
	@echo "  make status     - show whether main.py is installed (deploy mode) or absent (debug mode)"

deploy:
	$(INSTALL) \
		--connect $(PORT) \
		--bridge-name $(BRIDGE_NAME) \
		--wifi-ssid $(WIFI_SSID) \
		--wifi-password $(WIFI_PASSWORD) \
		--wifi-static-ip $(WIFI_STATIC_IP) \
		--wifi-netmask $(WIFI_NETMASK) \
		--wifi-gateway $(WIFI_GATEWAY) \
		--wifi-dns $(WIFI_DNS) \
		--server-host $(SERVER_HOST) \
		--server-port $(SERVER_PORT) \
		--health-port $(HEALTH_PORT) \
		--uart-id $(UART_ID) \
		--uart-baudrate $(UART_BAUDRATE) \
		--uart-tx-pin $(UART_TX_PIN) \
		--uart-rx-pin $(UART_RX_PIN) \
		--soft-reset

deplay: deploy

debug:
	$(INSTALL) \
		--connect $(PORT) \
		--bridge-name $(BRIDGE_NAME) \
		--wifi-ssid $(WIFI_SSID) \
		--wifi-password $(WIFI_PASSWORD) \
		--wifi-static-ip $(WIFI_STATIC_IP) \
		--wifi-netmask $(WIFI_NETMASK) \
		--wifi-gateway $(WIFI_GATEWAY) \
		--wifi-dns $(WIFI_DNS) \
		--server-host $(SERVER_HOST) \
		--server-port $(SERVER_PORT) \
		--health-port $(HEALTH_PORT) \
		--uart-id $(UART_ID) \
		--uart-baudrate $(UART_BAUDRATE) \
		--uart-tx-pin $(UART_TX_PIN) \
		--uart-rx-pin $(UART_RX_PIN)
	$(MPREMOTE) fs rm :main.py || true
	$(MPREMOTE) soft-reset
	@echo "Debug mode installed. main.py removed, board will not auto-run bridge on reset."
	@echo "Use 'make run' or 'make repl' to start it manually."

ping:
	$(PING) $(WIFI_STATIC_IP) --port $(HEALTH_PORT)

loopback:
	$(LOOPBACK) \
		--connect $(PORT) \
		--uart-id $(UART_ID) \
		--baudrate $(UART_BAUDRATE) \
		--tx-pin $(UART_TX_PIN) \
		--rx-pin $(UART_RX_PIN)

console:
	$(MPREMOTE) resume repl

monitor:
	$(MINITERM)

logs: monitor

repl:
	$(MPREMOTE) repl

run:
	$(MPREMOTE) resume exec "import bridge; bridge.main()"

stop:
	$(MPREMOTE) resume exec "raise KeyboardInterrupt()"

soft-reset:
	$(MPREMOTE) soft-reset

reset:
	$(MPREMOTE) reset

ls:
	$(MPREMOTE) fs ls

config:
	$(MPREMOTE) resume exec "import bridge_config; print(bridge_config.CONFIG)"

clean-main:
	$(MPREMOTE) fs rm :main.py

status:
	$(MPREMOTE) fs ls :main.py
