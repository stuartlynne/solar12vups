#!/usr/bin/env python3
# 
# Copyright(c)2025 stuart.lynne@gmail.com
# Made available under the MIT License
# See LICENSE.md
#
## Contributors
# Stuart Lynne <stuart.lynne@gmail.com>
# 

import sys
import asyncio
from bleak.uuids import uuid16_dict, uuid128_dict, uuidstr_to_str, register_uuids
#from bleak.backends.corebluetooth import CBCharacteristicProperties

from enum import Enum, IntEnum

import traceback

from utils import bytes_to_int, crc16_modbus, int_to_bytes

from lib import name_to_uuid, uuid_to_name
import logging
from log import setup_logger, xreport
logger = logging.getLogger(__name__)


BT_TH_UUIDS = {
    "0000ffd0-0000-1000-8000-00805f9b34fb": "BT_TH Write Service",
    "0000ffd1-0000-1000-8000-00805f9b34fb": "BT_TH Write",

    "0000fff0-0000-1000-8000-00805f9b34fb": "BT_TH Data Service",
    "0000fff1-0000-1000-8000-00805f9b34fb": "BT_TH Data",

    "0000ffd1-0000-1000-8000-00805f9b34fb": "BT_TH Write",
    #"0000ffd2-0000-1000-8000-00805f9b34fb": "BT_TH Notification",
    #0000fff1-0000-1000-8000-00805f9b34fb
    #0000ffd1-0000-1000-8000-00805f9b34fb
}

BT_TH_Supported_Characteristics = {
        "BT_TH Read Service:": {
        'read': [],
        'notify': ["BT_TH Data"],
        'ignore': [ ]
    },
        "BT_TH Write Service:": {
        'read': [],
        'notify': [""],
        'ignore': [ "BT_TH Write"]
    },
}, 


class Renogy:

    name = 'Renogy'


    def __init__(self):
        register_uuids(BT_TH_UUIDS)
        self.BT_TH_WRITE_SERVICE = name_to_uuid("BT_TH Write Service")
        self.BT_TH_WRITE = name_to_uuid("BT_TH Write")
        self.BT_TH_DATA_SERVICE = name_to_uuid("BT_TH DATA Service")
        self.BT_TH_DATA = name_to_uuid("BT_TH Data")

        self.device_id = 255
        self.notify_list = [ self.BT_TH_DATA, ]
        self.registers_index = 0
        self.registers = [
            {'name': 'Charging Info',  'register': 0x100, 'words': 10, 'parser': self.parse_charging_info, }, # 0x100
            {'name': 'Load State',     'register': 0x120, 'words': 8, 'parser': self.parse_load_state, 'modulus': [4,0], }, # 0x100
            {'name': 'Device Info',    'register': 0x0a, 'words': 0x10, 'parser': self.parse_device_info, 'once': True, },     # 0x0c
            {'name': 'Device Address', 'register': 26, 'words': 1, 'parser': self.parse_device_address, 'once': True,  }, # 0x1a
            {'name': 'History Info',   'register': 0x10b, 'words': 23, 'parser': self.parse_history_info, 'modulus': [4,0], }, # 0x100
            {'name': 'Battery Info',   'register': 0xe001, 'words': 40, 'parser': self.parse_battery_info, 'modulus': [4,2], }, # 0xe000k
        ]

        #self.POLAR_PFC_SERVICE = name_to_uuid("Polar Feature Configuration Service")


    def service_check(self, services):
        flag = self.BT_TH_DATA_SERVICE in services
        xreport('Renogy', 'service_check', services)
        xreport('Renogy', 'service_check', flag)
        return flag

    def data_check(self, uuid):
        flag = uuid in self.notify_list
        xreport('Renogy', 'data_check', uuid)
        xreport('Renogy', 'self.notify_list', self.notify_list)
        xreport('Renogy', 'self.notify_list', flag)

    async def start(self, myclient, device_name, services):
        # get PFC features
        try:
            #xreport('Renogy', f'notification {self.BT_TH_DATA}')
            #await myclient.start_notify(self.BT_TH_DATA, self.notification, supported_devices=None)

            xreport('Renogy', 'Starting Renogy')
            await self.read_registers(myclient)
        except Exception as e:
            logging.exception(f"Exception in Renogy.start: {e}")



    def notification(self, uuid, data, device_name=None, statistics=None):
        xreport('Renogy', 'notification', 'renogy %s:%s XXX' % (sender.uuid, len(data), ))
        pass


    async def read_registers(self, myclient):
        #if self.stopped('read_registers'): return
        if not self.registers:
            self.registers_index = 0
        else:
            self.registers += 1
        index = self.registers_index

        #self.read_timeout = self.loop.call_later(READ_TIMEOUT, self.on_read_timeout)
        #logging.info(f"read_registers: {self.registers[index]} *****************")

        name = self.registers[index]['name']
        logging.info(f"read_registers[{index}]: {name} => 0x{self.registers[index]['register']:02x} ({self.registers[index]['words']})")
        request = self.create_generic_read_request(self.device_id, 3, self.registers[index]['register'], self.registers[index]['words']) 
        xreport('Renogy', 'read_registers', f"request: {request} ({len(request)})")
        #if self.stopped('read request'): return
        xreport('Renogy', 'read_registers', f"BT_TH Write: {self.BT_TH_WRITE}")
        await myclient.write_gatt_char(self.BT_TH_WRITE, request, )
        xreport('Renogy', 'read_registers', f"BT_TH Write done: {self.BT_TH_WRITE}")


    def create_generic_read_request(self, device_id, function, regAddr, readWrd):
        data = None
        data = []
        data.append(device_id)
        data.append(function)
        if regAddr != None and readWrd != None:
            data.append(int_to_bytes(regAddr, 0))
            data.append(int_to_bytes(regAddr, 1))
            data.append(int_to_bytes(readWrd, 0))
            data.append(int_to_bytes(readWrd, 1))
        
        crc = crc16_modbus(bytes(data))
        data.append(crc[0])
        data.append(crc[1])
        logging.debug("{} {} => {}".format("create_request_payload", regAddr, data)) 
        return data

    def parse_device_info(self, bs):
        #logging.info("")
        #logging.info(f"parse_device_info: -----------------------------------------------------------------")
        #logging.info(f"parse_device_info: {bs.hex()} {len(bs)}")
        #logging.info(f"parse_device_info: {[hex(a) for a in bs]} {len(bs)}")
        logging.info(f"parse_device_info: {self.ble_manager.device.name}")
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        data['device_name'] = (0, self.ble_manager.device.name, False)

        def xget_nickname(device_name):
            return next((name for m, name in nicknames if m == device_name), None)

        def get_nickname(device_name):
            logging.info(f"get_nickname: device_name: {device_name}")
            logging.info(f"get_nickname: nicknames: {self.nicknames}")
            #return next((name for m, name in self.nicknames if m == device_name), 'N/F')
            return next((name for m, name in self.nicknames if m.strip() == device_name.strip()), '')


        #def get_nickname(name):
        #    if self.nicknames is None: return None
        #    return next((name for m, name in self.nicknames if m == name), None)

        data['device_nickname'] = (0, get_nickname(self.ble_manager.device.name), False)
        logging.info(f"parse_device_info: device_nickname: {data['device_nickname']}")


        #data['model'] = (0, (bs[3:19]).decode('utf-8').strip(), False)

        data['max_voltage_rated_current'] = (0x0a, bytes_to_int(bs, 3, 2), False)
        data['discharging_current_product_type'] = (0x0b, bytes_to_int(bs, 5, 2), False)
        data['model'] = (0x0c, (bs[7:23]).decode('utf-8').strip(), False)
        #data['software_version'] = (0x14, (bs[24:27]).decode('utf-8').strip(), False)
        #data['hardware_version'] = (0x16, (bs[28:31]).decode('utf-8').strip(), False)
        #data['serial_number'] = (0x18, (bs[28:31]).decode('utf-8').strip(), False)
        data['device_id_raw'] = (0x1a, bytes_to_int(bs, 32, 2), False)
        data['device_id_low'] = (0x1a, bytes_to_int(bs, 32, 2)&0xff, False)
        data['device_id_high'] = (0x1a, bytes_to_int(bs, 32, 2)>>8, False)
        data['device_id'] = (0x1a, bytes_to_int(bs, 32, 2)&0xff, False)
        logging.info(f"parse_device_info: {data}")
        self.data.update(data)

    def parse_device_address(self, bs):
        #logging.info("")
        #logging.info(f"parse_device_address: -----------------------------------------------------------------")
        data = {}
        data['device_id'] = (0x1a, bytes_to_int(bs, 4, 1), False)
        self.data.update(data)



    def parse_charging_info(self, bs):

        #logging.info("")
        #logging.info(f"parse_charging_info: -----------------------------------------------------------------")

        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0x100
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)

        data = {}
        temp_unit = 'F'

        registers = [
            ('battery_percentage',           0x100, 2, 1),
            ('battery_voltage',              0x101, 2, 0.1),
            ('battery_current',              0x102, 2, 0.01),
            ('temperatures',                 0x103, 2, None),
            ('load_voltage',                 0x104, 2,  0.1),
            ('load_current',                 0x105, 2, 0.01),
            ('load_power_raw',               0x106, 2, 1),      # see below, compute load_power from V*A
            ('pv_voltage',                   0x107, 2, 0.1),
            ('pv_current',                   0x108, 2, 0.01),
            ('pv_power_raw',                 0x109, 2, 1),      # see below, compute pv_power from V*A
            ]
        for name, addr, length, scale, in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False, )

        data['pv_power'] = (0, data['pv_voltage'][1] * data['pv_current'][1], False, )
        data['load_power'] = (0, data['load_voltage'][1] * data['load_current'][1], False, )
        data['battery_power'] = (0, data['battery_voltage'][1] * data['battery_current'][1], False, )
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False, )
        temp = bytes_to_int_offset(bs, 0x103, 2)
        data['battery_temperature'] = (0, parse_temperature(temp&0xff, temp_unit), False)  # 0x103 - low byte
        data['controller_temperature'] = (0, parse_temperature(temp>>8, temp_unit), False) # 0x103 - high byte

        self.data.update(data)


    def parse_load_state(self, bs):
        logging.info("")
        logging.info(f"parse_load_state: -----------------------------------------------------------------")

        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0x120
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)

        data = {}
        temp_unit = 'F'

        registers = [
            ('light_and_charging_state',    0x120, 2, None),
            ('controller_fault_warnings_121',0x121, 2, None),
            ('controller_fault_warnings_122',0x122, 2, None),
            ]
        for name, addr, length, scale, in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False, )

        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False, )
        temp = bytes_to_int_offset(bs, 0x103, 2)
        data['battery_temperature'] = (0, parse_temperature(temp&0xff, temp_unit), False)  # 0x103 - low byte
        data['controller_temperature'] = (0, parse_temperature(temp>>8, temp_unit), False) # 0x103 - high byte

        data['Light On/Off write only'] = (0, None, False, )


        status = data['light_and_charging_state'][1]
        logging.info(f"status: {status:04x} load:{status >> 7:02x} charging:{status & 0xff:02x} ")

        data['light_charging_state'] = (0x120, [hex(status>>7), hex(status&0xff)], False, ) # high byte first, low byte second
        data['load_status'] = (0x120, LOAD_STATE.get(status >> 7+8), False)                      # high byte
        self.load_status = data['load_status'][1]
        data['charging_status'] = (0x44, CHARGING_STATE.get(status & 0xff), False)             # low byte

        fault121 = data['controller_fault_warnings_121'][1]
        fault122 = data['controller_fault_warnings_122'][1]
        logging.info(f"faults: {fault121:04x} {fault122:04x} ")
        faults = [hex(fault121>>7), hex(fault121&0xff), hex(fault122>>7), hex(fault122&0xff)]
        logging.info(f"faults: {faults} ")
        data['controller_fault_warnings'] = (0x121, faults, False)                      # high byte
        #data['controller_fault_warnings'] = (0, f"{data['controller_fault_warnings_raw'][1]:08x}", False, )


        self.data.update(data)
        self.check_events_queues(data)

    def parse_history_info(self, bs):
        #logging.info("")
        #logging.info(f"parse_history_info: -----------------------------------------------------------------")

        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0x10b
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)

        data = {}
        temp_unit = 'F'

        registers = [
            ('battery_min_voltage today',    0x10b, 2, 0.1),
            ('battery_max_voltage today',    0x10c, 2, 0.1),
            ('max_charging_current_today',   0x01d, 2, 1),
            ('max_discharging_current_today',0x01e, 2, 1),
            ('max_charging_power_today',     0x10f, 2, 1),
            ('max_discharging_power_today',  0x110, 2, 1),
            ('charging_amp_hours_today',     0x111, 2, 1),
            ('discharging_amp_hours_today',  0x112, 2, 1),
            ('power_generation_today',       0x113, 2, 1),
            ('power_consumption_today',      0x114, 2, 1),
            ('total_operating_days',         0x115, 2, 1),
            ('total_battery_over_discharges',0x116, 2, 1),
            ('total_battery_full_discharges',0x117, 2, 1),
            ('total_battery_full_charges',   0x118, 2, 1),
            ('power_generation_total',       0x11c, 4, 1),
            ('power_consumption_total',      0x11e, 4, 1),
            ('light_and_charging_state',    0x120, 2, None),
            ('controller_fault_warnings_121',0x121, 2, None),
            ('controller_fault_warnings_122',0x122, 2, None),
            ]
        for name, addr, length, scale, in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False, )

        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False, )
        temp = bytes_to_int_offset(bs, 0x103, 2)
        data['battery_temperature'] = (0, parse_temperature(temp&0xff, temp_unit), False)  # 0x103 - low byte
        data['controller_temperature'] = (0, parse_temperature(temp>>8, temp_unit), False) # 0x103 - high byte

        data['Light On/Off write only'] = (0, None, False, )


        status = data['light_and_charging_state'][1]
        logging.info(f"status: {status:04x} load:{status >> 7:02x} charging:{status & 0xff:02x} ")

        data['light_charging_state'] = (0x120, [hex(status>>7), hex(status&0xff)], False, ) # high byte first, low byte second
        data['load_status'] = (0x120, LOAD_STATE.get(status >> 7+8), False)                      # high byte
        self.load_status = data['load_status'][1]
        data['charging_status'] = (0x44, CHARGING_STATE.get(status & 0xff), False)             # low byte

        fault121 = data['controller_fault_warnings_121'][1]
        fault122 = data['controller_fault_warnings_122'][1]
        logging.info(f"faults: {fault121:04x} {fault122:04x} ")
        faults = [hex(fault121>>7), hex(fault121&0xff), hex(fault122>>7), hex(fault122&0xff)]
        logging.info(f"faults: {faults} ")
        data['controller_fault_warnings'] = (0x121, faults, False)                      # high byte
        #data['controller_fault_warnings'] = (0, f"{data['controller_fault_warnings_raw'][1]:08x}", False, )


        self.data.update(data)
        self.check_events_queues(data)



   #def parse_battery_type(self, bs):
   #    data = {}
   #    data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
   #    data['battery_type_raw'] = (0xe004, bytes_to_int(bs, 3+6, 2), True)            # 0xe004 - 0x03   
   #    data['battery_type'] = (0xe004, BATTERY_TYPE.get(bytes_to_int(bs, 3+6, 2)), False)            # 0xe004 - 0x03   
   #    data['over_voltage_threshold'] = (bytes_to_int(bs, 5+6, 2)            # 0xe004 - 0x03   
   #    self.data.update(data)
   #    tl = [ ]
   #    for key, value in data.items():
   #        tl.append((key, value))
   #    tl_table = tabulate(tl, headers=['Name', 'Value'], tablefmt='grid')
   #    tl_lines = tl_table.split('\n')
   #    for l in tl_lines:
   #        logging.info(f"parse_battery_type: {l}")

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
    def parse_battery_info(self, bs):
        #logging.info("")
        #logging.info(f"parse_battery_info: -----------------------------------------------------------------")
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        data['battery_type_raw1'] = (0xe004, bytes_to_int(bs, 3+6, 2), False)            # 0xe004 - 0x03   
        data['battery_type1'] = (0, BATTERY_TYPE.get(data['battery_type_raw1']), False)            # 0xe004 - 0x03   
        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0xe001
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)
        for name, addr, length, scale, editable in self.battery_info_registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), editable)

        data['battery_type'] = (0, BATTERY_TYPE.get(data['battery_type_raw']), True)           # 0xe004 - 0x03   
        data['end_of_discharge_soc'] = (0, (data['end_of'][1] & 0x7f) * 0.1, False)                # low byte
        data['end_of_charge_soc'] = (0, (data['end_of'][1] >> 8) * 0.1, False)                     # high byte
        data['system_voltage'] = (0, data['voltage_settings'][1] >> 8, True)                      # high byte
        data['recognized_voltage'] = (0, data['voltage_settings'][1] & 0x7f, False )               # low byte
        self.data.update(data)
        #tl = [ ]
        #for key, value in data.items():
        #    tl.append((key, value))
        #tl_table = tabulate(tl, headers=['Name', 'Value'], tablefmt='grid')
        #tl_lines = tl_table.split('\n')
        #for l in tl_lines:
        #    logging.info(f"parse_battery_info: {l}")

    def parse_set_load_response(self, bs):
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        #data['load_status'] = (bytes_to_int(bs, 5, 1)
        data['load_status'] = (0x120, LOAD_STATE.get(bytes_to_int(bs, 5, 1)), False)                      # 0x120
        self.data.update(data)

    def parse_write_response(self, bs):
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)))
        response = bytes_to_int(bs, 5, 2)
        #logging.info(f"parse_write_response: {response:04x}")
        #self.data.update(data)



    def parse_device_info(self, bs):
        #logging.info("")
        #logging.info(f"parse_device_info: -----------------------------------------------------------------")
        #logging.info(f"parse_device_info: {bs.hex()} {len(bs)}")
        #logging.info(f"parse_device_info: {[hex(a) for a in bs]} {len(bs)}")
        logging.info(f"parse_device_info: {self.ble_manager.device.name}")
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        data['device_name'] = (0, self.ble_manager.device.name, False)

        def xget_nickname(device_name):
            return next((name for m, name in nicknames if m == device_name), None)

        def get_nickname(device_name):
            logging.info(f"get_nickname: device_name: {device_name}")
            logging.info(f"get_nickname: nicknames: {self.nicknames}")
            #return next((name for m, name in self.nicknames if m == device_name), 'N/F')
            return next((name for m, name in self.nicknames if m.strip() == device_name.strip()), '')


        #def get_nickname(name):
        #    if self.nicknames is None: return None
        #    return next((name for m, name in self.nicknames if m == name), None)

        data['device_nickname'] = (0, get_nickname(self.ble_manager.device.name), False)
        logging.info(f"parse_device_info: device_nickname: {data['device_nickname']}")


        #data['model'] = (0, (bs[3:19]).decode('utf-8').strip(), False)

        data['max_voltage_rated_current'] = (0x0a, bytes_to_int(bs, 3, 2), False)
        data['discharging_current_product_type'] = (0x0b, bytes_to_int(bs, 5, 2), False)
        data['model'] = (0x0c, (bs[7:23]).decode('utf-8').strip(), False)
        #data['software_version'] = (0x14, (bs[24:27]).decode('utf-8').strip(), False)
        #data['hardware_version'] = (0x16, (bs[28:31]).decode('utf-8').strip(), False)
        #data['serial_number'] = (0x18, (bs[28:31]).decode('utf-8').strip(), False)
        data['device_id_raw'] = (0x1a, bytes_to_int(bs, 32, 2), False)
        data['device_id_low'] = (0x1a, bytes_to_int(bs, 32, 2)&0xff, False)
        data['device_id_high'] = (0x1a, bytes_to_int(bs, 32, 2)>>8, False)
        data['device_id'] = (0x1a, bytes_to_int(bs, 32, 2)&0xff, False)
        logging.info(f"parse_device_info: {data}")
        self.data.update(data)
        #self.sections.pop(0) # remove device info from sections

    def parse_device_address(self, bs):
        #logging.info("")
        #logging.info(f"parse_device_address: -----------------------------------------------------------------")
        data = {}
        data['device_id'] = (0x1a, bytes_to_int(bs, 4, 1), False)
        self.data.update(data)



    def parse_charging_info(self, bs):

        #logging.info("")
        #logging.info(f"parse_charging_info: -----------------------------------------------------------------")

        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0x100
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)

        data = {}
        temp_unit = 'F'

        registers = [
            ('battery_percentage',           0x100, 2, 1),
            ('battery_voltage',              0x101, 2, 0.1),
            ('battery_current',              0x102, 2, 0.01),
            ('temperatures',                 0x103, 2, None),
            ('load_voltage',                 0x104, 2,  0.1),
            ('load_current',                 0x105, 2, 0.01),
            ('load_power_raw',               0x106, 2, 1),      # see below, compute load_power from V*A
            ('pv_voltage',                   0x107, 2, 0.1),
            ('pv_current',                   0x108, 2, 0.01),
            ('pv_power_raw',                 0x109, 2, 1),      # see below, compute pv_power from V*A
            ]
        for name, addr, length, scale, in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False, )

        data['pv_power'] = (0, data['pv_voltage'][1] * data['pv_current'][1], False, )
        data['load_power'] = (0, data['load_voltage'][1] * data['load_current'][1], False, )
        data['battery_power'] = (0, data['battery_voltage'][1] * data['battery_current'][1], False, )
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False, )
        temp = bytes_to_int_offset(bs, 0x103, 2)
        data['battery_temperature'] = (0, parse_temperature(temp&0xff, temp_unit), False)  # 0x103 - low byte
        data['controller_temperature'] = (0, parse_temperature(temp>>8, temp_unit), False) # 0x103 - high byte

        self.data.update(data)


    def parse_load_state(self, bs):
        logging.info("")
        logging.info(f"parse_load_state: -----------------------------------------------------------------")

        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0x120
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)

        data = {}
        temp_unit = 'F'

        registers = [
            ('light_and_charging_state',    0x120, 2, None),
            ('controller_fault_warnings_121',0x121, 2, None),
            ('controller_fault_warnings_122',0x122, 2, None),
            ]
        for name, addr, length, scale, in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False, )

        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False, )
        temp = bytes_to_int_offset(bs, 0x103, 2)
        data['battery_temperature'] = (0, parse_temperature(temp&0xff, temp_unit), False)  # 0x103 - low byte
        data['controller_temperature'] = (0, parse_temperature(temp>>8, temp_unit), False) # 0x103 - high byte

        data['Light On/Off write only'] = (0, None, False, )


        status = data['light_and_charging_state'][1]
        logging.info(f"status: {status:04x} load:{status >> 7:02x} charging:{status & 0xff:02x} ")

        data['light_charging_state'] = (0x120, [hex(status>>7), hex(status&0xff)], False, ) # high byte first, low byte second
        data['load_status'] = (0x120, LOAD_STATE.get(status >> 7+8), False)                      # high byte
        self.load_status = data['load_status'][1]
        data['charging_status'] = (0x44, CHARGING_STATE.get(status & 0xff), False)             # low byte

        fault121 = data['controller_fault_warnings_121'][1]
        fault122 = data['controller_fault_warnings_122'][1]
        logging.info(f"faults: {fault121:04x} {fault122:04x} ")
        faults = [hex(fault121>>7), hex(fault121&0xff), hex(fault122>>7), hex(fault122&0xff)]
        logging.info(f"faults: {faults} ")
        data['controller_fault_warnings'] = (0x121, faults, False)                      # high byte
        #data['controller_fault_warnings'] = (0, f"{data['controller_fault_warnings_raw'][1]:08x}", False, )


        self.data.update(data)
        self.check_events_queues(data)

    def parse_history_info(self, bs):
        #logging.info("")
        #logging.info(f"parse_history_info: -----------------------------------------------------------------")

        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0x10b
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)

        data = {}
        temp_unit = 'F'

        registers = [
            ('battery_min_voltage today',    0x10b, 2, 0.1),
            ('battery_max_voltage today',    0x10c, 2, 0.1),
            ('max_charging_current_today',   0x01d, 2, 1),
            ('max_discharging_current_today',0x01e, 2, 1),
            ('max_charging_power_today',     0x10f, 2, 1),
            ('max_discharging_power_today',  0x110, 2, 1),
            ('charging_amp_hours_today',     0x111, 2, 1),
            ('discharging_amp_hours_today',  0x112, 2, 1),
            ('power_generation_today',       0x113, 2, 1),
            ('power_consumption_today',      0x114, 2, 1),
            ('total_operating_days',         0x115, 2, 1),
            ('total_battery_over_discharges',0x116, 2, 1),
            ('total_battery_full_discharges',0x117, 2, 1),
            ('total_battery_full_charges',   0x118, 2, 1),
            ('power_generation_total',       0x11c, 4, 1),
            ('power_consumption_total',      0x11e, 4, 1),
            ('light_and_charging_state',    0x120, 2, None),
            ('controller_fault_warnings_121',0x121, 2, None),
            ('controller_fault_warnings_122',0x122, 2, None),
            ]
        for name, addr, length, scale, in registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), False, )

        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False, )
        temp = bytes_to_int_offset(bs, 0x103, 2)
        data['battery_temperature'] = (0, parse_temperature(temp&0xff, temp_unit), False)  # 0x103 - low byte
        data['controller_temperature'] = (0, parse_temperature(temp>>8, temp_unit), False) # 0x103 - high byte

        data['Light On/Off write only'] = (0, None, False, )


        status = data['light_and_charging_state'][1]
        logging.info(f"status: {status:04x} load:{status >> 7:02x} charging:{status & 0xff:02x} ")

        data['light_charging_state'] = (0x120, [hex(status>>7), hex(status&0xff)], False, ) # high byte first, low byte second
        data['load_status'] = (0x120, LOAD_STATE.get(status >> 7+8), False)                      # high byte
        self.load_status = data['load_status'][1]
        data['charging_status'] = (0x44, CHARGING_STATE.get(status & 0xff), False)             # low byte

        fault121 = data['controller_fault_warnings_121'][1]
        fault122 = data['controller_fault_warnings_122'][1]
        logging.info(f"faults: {fault121:04x} {fault122:04x} ")
        faults = [hex(fault121>>7), hex(fault121&0xff), hex(fault122>>7), hex(fault122&0xff)]
        logging.info(f"faults: {faults} ")
        data['controller_fault_warnings'] = (0x121, faults, False)                      # high byte
        #data['controller_fault_warnings'] = (0, f"{data['controller_fault_warnings_raw'][1]:08x}", False, )


        self.data.update(data)
        self.check_events_queues(data)



   #def parse_battery_type(self, bs):
   #    data = {}
   #    data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
   #    data['battery_type_raw'] = (0xe004, bytes_to_int(bs, 3+6, 2), True)            # 0xe004 - 0x03   
   #    data['battery_type'] = (0xe004, BATTERY_TYPE.get(bytes_to_int(bs, 3+6, 2)), False)            # 0xe004 - 0x03   
   #    data['over_voltage_threshold'] = (bytes_to_int(bs, 5+6, 2)            # 0xe004 - 0x03   
   #    self.data.update(data)
   #    tl = [ ]
   #    for key, value in data.items():
   #        tl.append((key, value))
   #    tl_table = tabulate(tl, headers=['Name', 'Value'], tablefmt='grid')
   #    tl_lines = tl_table.split('\n')
   #    for l in tl_lines:
   #        logging.info(f"parse_battery_type: {l}")

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
    def parse_battery_info(self, bs):
        #logging.info("")
        #logging.info(f"parse_battery_info: -----------------------------------------------------------------")
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        data['battery_type_raw1'] = (0xe004, bytes_to_int(bs, 3+6, 2), False)            # 0xe004 - 0x03   
        data['battery_type1'] = (0, BATTERY_TYPE.get(data['battery_type_raw1']), False)            # 0xe004 - 0x03   
        # there are 3 bytes ahead of payload, and documentation is in 2 byte words
        def bytes_to_int_offset(bytes, addr, length, scale=None):
            base = 0xe001
            offset = (addr - base) * 2 + 3
            #logging.info(f"offset: {offset} addr: {addr} length: {length}")
            return bytes_to_int(bytes, offset, length, scale=scale)
        for name, addr, length, scale, editable in self.battery_info_registers:
            data[name] = (f"{addr:04x}", bytes_to_int_offset(bs, addr, length, scale=scale), editable)

        data['battery_type'] = (0, BATTERY_TYPE.get(data['battery_type_raw']), True)           # 0xe004 - 0x03   
        data['end_of_discharge_soc'] = (0, (data['end_of'][1] & 0x7f) * 0.1, False)                # low byte
        data['end_of_charge_soc'] = (0, (data['end_of'][1] >> 8) * 0.1, False)                     # high byte
        data['system_voltage'] = (0, data['voltage_settings'][1] >> 8, True)                      # high byte
        data['recognized_voltage'] = (0, data['voltage_settings'][1] & 0x7f, False )               # low byte
        self.data.update(data)
        #tl = [ ]
        #for key, value in data.items():
        #    tl.append((key, value))
        #tl_table = tabulate(tl, headers=['Name', 'Value'], tablefmt='grid')
        #tl_lines = tl_table.split('\n')
        #for l in tl_lines:
        #    logging.info(f"parse_battery_info: {l}")

    def parse_set_load_response(self, bs):
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        #data['load_status'] = (bytes_to_int(bs, 5, 1)
        data['load_status'] = (0x120, LOAD_STATE.get(bytes_to_int(bs, 5, 1)), False)                      # 0x120
        self.data.update(data)

    def parse_write_response(self, bs):
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)))
        response = bytes_to_int(bs, 5, 2)
        #logging.info(f"parse_write_response: {response:04x}")
        #self.data.update(data)


