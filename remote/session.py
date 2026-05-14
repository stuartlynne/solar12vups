#!/usr/bin/env python3
#
# Copyright(c)2026 stuart.lynne@gmail.com
# Made available under the MIT License
#

import asyncio
import sys
import traceback

from ble.btth import (
    BATTERY_TYPE,
    CHARGING_STATE,
    FUNCTION,
    LOAD_STATE,
    decode_controller_fault_codes,
    decode_controller_fault_warnings,
    parse_temperature,
)
from lib.utils import bytes_to_int, crc16_modbus, int_to_bytes

import logging
from lib.log import xreport

logger = logging.getLogger(__name__)


class RemoteBtThSession:
    battery_info_registers = [
        ('battery_type_raw', 0xe004, 2, 1, True),
        ('boost_charging_voltage', 0xe008, 2, .1, True),
        ('floating_charging_voltage', 0xe009, 2, .1, True),
        ('nominal_battery_capacity', 0xe002, 2, 1, True),
        ('voltage_settings', 0xe003, 2, 1, True),
        ('over_voltage_threshold', 0xe005, 2, .1, True),
        ('charging_voltage_limit', 0xe006, 2, .1, True),
        ('equalizing_charging_voltage', 0xe007, 2, .1, True),
        ('boost_charging_recovery_voltage', 0xe00a, 2, .1, True),
        ('over_discharge_recovery_voltage', 0xe00b, 2, .1, True),
        ('under_voltage_warning_level', 0xe00c, 2, .1, True),
        ('over_discharge_voltage', 0xe00d, 2, .1, True),
        ('discharge_limit_voltage', 0xe00e, 2, .1, True),
        ('end_of', 0xe00f, 2, 1, False),
        ('over_discharge_time_delay', 0xe010, 2, 1, True),
        ('equalizing_charging_interval', 0xe011, 2, 1, True),
        ('boost_charging_time', 0xe012, 2, 1, True),
        ('equalizing_charging_time', 0xe013, 2, 1, True),
        ('temperature_compensation_factor', 0xe014, 2, 1, True),
        ('load_working_mode', 0xe01d, 2, 1, True),
        ('special_power_control', 0xe021, 2, 1, True),
    ]

    def __init__(self, bridge_name, hub, aevents=None, controlQueue=None, dataQueue=None):
        self.bridge_name = bridge_name
        self.device_name = bridge_name
        self.hub = hub
        self.aevents = aevents
        self.controlQueue = controlQueue
        self.dataQueue = dataQueue
        self.device_id = 255
        self.nicknames = []
        self.model = None
        self.device_nickname = bridge_name
        self.registers_first = True
        self.registers_index = None
        self.register_reads_reset = 0
        self.load_status = 'off'
        self.registers = [
            {'name': 'Charging Info', 'register': 0x100, 'words': 10, 'parser': self.parse_charging_info},
            {'name': 'Load State', 'register': 0x120, 'words': 8, 'parser': self.parse_load_state, 'modulus': [4, 0]},
            {'name': 'Device Info', 'register': 0x0a, 'words': 0x10, 'parser': self.parse_device_info, 'once': True},
            {'name': 'Device Address', 'register': 0x1a, 'words': 1, 'parser': self.parse_device_address, 'once': True},
            {'name': 'History Info', 'register': 0x10b, 'words': 23, 'parser': self.parse_history_info, 'modulus': [4, 0]},
            {'name': 'Battery Info', 'register': 0xe001, 'words': 40, 'parser': self.parse_battery_info, 'modulus': [4, 2]},
        ]

    def queueData(self, data):
        if self.dataQueue is not None:
            self.dataQueue.put((self.device_name, data))

    def emit_ui_event(self, event_name, **fields):
        payload = {'__ui_event__': (None, event_name, False)}
        payload.update(fields)
        self.queueData(payload)

    def emit_status(self, message, level="info"):
        self.emit_ui_event(
            "device_status",
            status_text=(0, message, False),
            status_level=(0, level, False),
        )

    def describe_error(self, exc):
        if isinstance(exc, TimeoutError) or isinstance(exc, asyncio.TimeoutError):
            if not self.hub.has_bridge(self.bridge_name):
                return "Pico bridge disconnected from host.", "error"
            return "Pico connected. Wanderer did not respond to Modbus request.", "error"

        message = str(exc)
        if "bad modbus crc in response" in message:
            return "Pico connected. Wanderer response was invalid (CRC error).", "error"
        if "uart read timeout" in message:
            return "Pico connected. Wanderer did not return UART data.", "error"
        if "bridge not connected" in message.lower():
            return "Pico bridge disconnected from host.", "error"
        return f"Pico connected, but remote read failed: {message}", "error"

    def is_expected_error(self, exc):
        if isinstance(exc, TimeoutError) or isinstance(exc, asyncio.TimeoutError):
            return True
        message = str(exc).lower()
        expected_substrings = (
            "bad modbus crc in response",
            "uart read timeout",
            "bridge not connected",
        )
        return any(part in message for part in expected_substrings)

    def is_shutdown_error(self, exc):
        if isinstance(exc, GeneratorExit):
            return True
        if isinstance(exc, RuntimeError) and "event loop is closed" in str(exc).lower():
            return True
        return False

    def create_generic_read_request(self, device_id, function, regAddr, readWrd):
        data = [device_id, function]
        if regAddr is not None and readWrd is not None:
            data.append(int_to_bytes(regAddr, 0))
            data.append(int_to_bytes(regAddr, 1))
            data.append(int_to_bytes(readWrd, 0))
            data.append(int_to_bytes(readWrd, 1))

        crc = crc16_modbus(bytes(data))
        data.append(crc[0])
        data.append(crc[1])
        return data

    async def send_request(self, request, timeout=5.0):
        logger.info("BRIDGETRACE session request bridge=%s bytes=%d hex=%s", self.bridge_name, len(request), bytes(request).hex())
        return await self.hub.send_request(self.bridge_name, bytes(request), timeout=timeout)

    async def run(self):
        xreport("RemoteBtThSession", self.device_name, "starting", green=True)
        self.emit_ui_event("device_ready")
        self.emit_status("Pico bridge connected. Waiting for Wanderer response.", level="info")
        while not self.aevents.is_shutdown():
            try:
                await self.read_registers("remote")
                self.emit_status("Pico bridge connected. Wanderer responding.", level="ok")
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except GeneratorExit as exc:
                logger.info("RemoteBtThSession[%s] shutting down: %s", self.device_name, exc)
                return
            except Exception as exc:
                if self.is_shutdown_error(exc):
                    logger.info("RemoteBtThSession[%s] shutting down: %s", self.device_name, exc)
                    return
                status_message, status_level = self.describe_error(exc)
                if self.is_expected_error(exc):
                    logger.info("RemoteBtThSession[%s] expected status: %s", self.device_name, status_message)
                else:
                    logging.exception("RemoteBtThSession[%s] error: %s", self.device_name, exc)
                    print(traceback.format_exc(), file=sys.stderr)
                self.emit_status(status_message, level=status_level)
                await asyncio.sleep(2)

    async def read_registers(self, msg):
        if self.controlQueue and not self.controlQueue.empty():
            control = self.controlQueue.get()
            if self.device_name.lower() == control[0].lower():
                match control[1]:
                    case 'set':
                        device_name, op, addr, description, value = control
                        await self.set_register(addr, value)
                        return
                    case 'toggle_load':
                        await self.set_register(0x10a, 1 if self.load_status == 'off' else 0)
                        return

        old_index = self.registers_index
        self.registers_index = 0 if self.registers_index is None else self.registers_index + 1

        if self.registers_first or self.model is None or self.device_nickname is None or self.register_reads_reset % 10 == 0:
            if self.registers_index >= len(self.registers):
                self.registers_index = 0
                self.registers_first = False
                self.register_reads_reset += 1
        else:
            if self.registers_index >= 3:
                self.registers_index = 0
                self.register_reads_reset += 1

        index = self.registers_index
        register_info = self.registers[index]
        logging.info(
            "RemoteBtThSession.read_registers[%s:%s] %s old=%s %04x:%s",
            msg,
            index,
            register_info['name'],
            old_index,
            register_info['register'],
            register_info['words'],
        )
        request = self.create_generic_read_request(self.device_id, 3, register_info['register'], register_info['words'])
        response = await self.send_request(request, timeout=5.0)
        logger.info(
            "BRIDGETRACE session response bridge=%s register=%s bytes=%d hex=%s",
            self.bridge_name,
            register_info['name'],
            len(response),
            response.hex(),
        )
        register_info['parser'](response)

    def parse_history_info(self, bs):
        def bytes_to_int_offset(blob, addr, length, scale=None):
            base = 0x10b
            offset = (addr - base) * 2 + 3
            return bytes_to_int(blob, offset, length, scale=scale)

        data = {}
        registers = [
            ('battery_min_voltage today', 0x10b, 2, 0.1),
            ('battery_max_voltage today', 0x10c, 2, 0.1),
            ('max_charging_current_today', 0x01d, 2, 1),
            ('max_discharging_current_today', 0x01e, 2, 1),
            ('max_charging_power_today', 0x10f, 2, 1),
            ('max_discharging_power_today', 0x110, 2, 1),
            ('charging_amp_hours_today', 0x111, 2, 1),
            ('discharging_amp_hours_today', 0x112, 2, 1),
            ('power_generation_today', 0x113, 2, 1),
            ('power_consumption_today', 0x114, 2, 1),
            ('total_operating_days', 0x115, 2, 1),
            ('total_battery_over_discharges', 0x116, 2, 1),
            ('total_battery_full_discharges', 0x117, 2, 1),
            ('total_battery_full_charges', 0x118, 2, 1),
            ('power_generation_total', 0x11c, 4, 1),
            ('power_consumption_total', 0x11e, 4, 1),
        ]
        for name, addr, length, scale in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False)
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        self.queueData(data)

    def parse_device_info(self, bs):
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        data['device_name'] = (0, self.device_name, False)
        data['device_nickname'] = (0, self.device_name, False)
        data['max_voltage_rated_current'] = (0x0a, bytes_to_int(bs, 3, 2), False)
        data['discharging_current_product_type'] = (0x0b, bytes_to_int(bs, 5, 2), False)
        model = (bs[7:23]).decode('utf-8').strip()
        data['model'] = (0x0c, model, False)
        self.model = model
        data['device_id_raw'] = (0x1a, bytes_to_int(bs, 32, 2), False)
        data['device_id_low'] = (0x1a, bytes_to_int(bs, 32, 2) & 0xff, False)
        data['device_id_high'] = (0x1a, bytes_to_int(bs, 32, 2) >> 8, False)
        data['device_id'] = (0x1a, bytes_to_int(bs, 32, 2) & 0xff, False)
        self.queueData(data)

    def parse_device_address(self, bs):
        data = {}
        data['device_id'] = (0x1a, bytes_to_int(bs, 4, 1), False)
        self.queueData(data)

    def parse_charging_info(self, bs):
        def bytes_to_int_offset(blob, addr, length, scale=None):
            base = 0x100
            offset = (addr - base) * 2 + 3
            return bytes_to_int(blob, offset, length, scale=scale)

        data = {}
        temp_unit = 'F'
        registers = [
            ('battery_percentage', 0x100, 2, 1),
            ('battery_voltage', 0x101, 2, 0.1),
            ('battery_current', 0x102, 2, 0.01),
            ('temperatures', 0x103, 2, None),
            ('load_voltage', 0x104, 2, 0.1),
            ('load_current', 0x105, 2, 0.01),
            ('load_power_raw', 0x106, 2, 1),
            ('pv_voltage', 0x107, 2, 0.1),
            ('pv_current', 0x108, 2, 0.01),
            ('pv_power_raw', 0x109, 2, 1),
        ]
        for name, addr, length, scale in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False)

        data['pv_power'] = (0, data['pv_voltage'][1] * data['pv_current'][1], False)
        data['load_power'] = (0, data['load_voltage'][1] * data['load_current'][1], False)
        data['battery_power'] = (0, data['battery_voltage'][1] * data['battery_current'][1], False)
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        temp = bytes_to_int_offset(bs, 0x103, 2)
        data['battery_temperature'] = (0, parse_temperature(temp & 0xff, temp_unit), False)
        data['controller_temperature'] = (0, parse_temperature(temp >> 8, temp_unit), False)
        self.queueData(data)

    def parse_load_state(self, bs):
        def bytes_to_int_offset(blob, addr, length, scale=None):
            base = 0x120
            offset = (addr - base) * 2 + 3
            return bytes_to_int(blob, offset, length, scale=scale)

        data = {}
        registers = [
            ('light_and_charging_state', 0x120, 2, None),
            ('controller_fault_warnings_121', 0x121, 2, None),
            ('controller_fault_warnings_122', 0x122, 2, None),
        ]
        for name, addr, length, scale in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False)

        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        data['Light On/Off write only'] = (0, None, False)

        status = data['light_and_charging_state'][1]
        data['light_charging_state'] = (0x120, [hex(status >> 7), hex(status & 0xff)], False)
        data['load_status'] = (0x120, LOAD_STATE.get(status >> 15), False)
        self.load_status = data['load_status'][1]
        data['charging_status'] = (0x44, CHARGING_STATE.get(status & 0xff), False)

        fault121 = data['controller_fault_warnings_121'][1]
        fault122 = data['controller_fault_warnings_122'][1]
        data['controller_fault_warnings'] = ('0121', decode_controller_fault_warnings(fault121, fault122), False)
        data['controller_fault_codes'] = ('fault-codes', decode_controller_fault_codes(fault121, fault122), False)
        self.queueData(data)

    def parse_battery_info(self, bs):
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)

        def bytes_to_int_offset(blob, addr, length, scale=None):
            base = 0xe001
            offset = (addr - base) * 2 + 3
            return bytes_to_int(blob, offset, length, scale=scale)

        for name, addr, length, scale, editable in self.battery_info_registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), editable)

        data['battery_type'] = (0, BATTERY_TYPE.get(data['battery_type_raw'][1]), True)
        data['end_of_discharge_soc'] = (0, (data['end_of'][1] & 0x7f) * 0.1, False)
        data['end_of_charge_soc'] = (0, (data['end_of'][1] >> 8) * 0.1, False)
        data['system_voltage'] = (0, data['voltage_settings'][1] >> 8, True)
        data['recognized_voltage'] = (0, data['voltage_settings'][1] & 0x7f, False)
        self.queueData(data)

    async def set_register(self, register, value):
        scaled = int(round(float(value)))
        request = self.create_generic_read_request(self.device_id, 6, register, scaled)
        await self.send_request(request, timeout=5.0)
