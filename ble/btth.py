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

from time import time
from enum import Enum, IntEnum

import traceback
import ast

from lib.utils import bytes_to_int, crc16_modbus, int_to_bytes
from bleak.exc import BleakError

from lib.lib import bytes2str, name_to_uuid, uuid_to_name
from ble.clientex import BleakClientEx
import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)


BT_TH_UUIDS = {
    "0000ffd0-0000-1000-8000-00805f9b34fb": "BT_TH Write Service",
    "0000ffd1-0000-1000-8000-00805f9b34fb": "BT_TH Write",

    "0000fff0-0000-1000-8000-00805f9b34fb": "BT_TH Data Service",
    "0000fff1-0000-1000-8000-00805f9b34fb": "BT_TH Data",
}


FUNCTION = {
    3: "READ",
    6: "WRITE"
}
            
CHARGING_STATE = {
    0: 'deactivated',
    1: 'activated',
    2: 'mppt',
    3: 'equalizing',
    4: 'boost',
    5: 'floating',
    6: 'current limiting'
}                                                   

LOAD_STATE = {  
  0: 'off',
  1: 'on'
}
    
BATTERY_TYPE = {
    1: 'open',
    2: 'sealed',
    3: 'gel',
    4: 'lithium',
    5: 'custom'
}

def parse_temperature(raw_value, unit):
    sign = raw_value >> 7
    celcius = -(raw_value - 128) if sign == 1 else raw_value
    return format_temperature(celcius, unit)
                 
def format_temperature(celcius, unit = 'F'):
    return (celcius * 9/5) + 32 if unit.strip() == 'F' else celcius



class BtThBleakClient(BleakClientEx):

    name = 'BT-TH'

    def __init__(self, device, aevents=None, *args, **kwargs):
        register_uuids(BT_TH_UUIDS)

        self.BT_TH_WRITE_SERVICE = name_to_uuid("BT_TH Write Service")
        self.BT_TH_WRITE = name_to_uuid("BT_TH Write")
        self.BT_TH_DATA_SERVICE = name_to_uuid("BT_TH DATA Service")
        self.BT_TH_DATA = name_to_uuid("BT_TH Data")

        self.notify_list = [ (self.BT_TH_DATA, self.notification), ]

        super(BtThBleakClient, self).__init__(device, aevents=aevents, *args, **kwargs)

        self.no_data_restart_seconds = 10

        self.device_id = 255
        self.nicknames = []

        self.model = None
        self.device_nickname = None
        self.registers_first = True
        self.registers_index = None
        self.register_reads_reset = 0
        self.registers = [
            {'name': 'Charging Info',  'register': 0x100, 'words': 10, 'parser': self.parse_charging_info, }, # 0x100
            {'name': 'Load State',     'register': 0x120, 'words': 8, 'parser': self.parse_load_state, 'modulus': [4,0], }, # 0x100

            # XXX these two can be collapsed into one request
            {'name': 'Device Info',    'register': 0x0a, 'words': 0x10, 'parser': self.parse_device_info, 'once': True, },     # 0x0c
            {'name': 'Device Address', 'register': 0x1a, 'words': 1, 'parser': self.parse_device_address, 'once': True,  }, # 0x1a

            {'name': 'History Info',   'register': 0x10b, 'words': 23, 'parser': self.parse_history_info, 'modulus': [4,0], }, # 0x100
            {'name': 'Battery Info',   'register': 0xe001, 'words': 40, 'parser': self.parse_battery_info, 'modulus': [4,2], }, # 0xe000k
        ]


    async def start(self, ):
        await super(BtThBleakClient, self).start()
        try:
            #logging.info(f"BtThBleakClient.start: {self.device_name} {self.device_id} {self.rawnicknames} index:{self.registers_index}")
            await self.read_registers('start')
        except Exception as e:
            logging.exception(f"Exception in BtTh.start: {e}")


    async def notification(self, characteristic, data, ):
        try:
            xreport('BtThBleakClient.notification', self.device_name, f"entered", yellow=True, )
            if self.disconnect_called:
                xreport('BtThBleakClient.notification', self.device_name, f"disconnect_called is True", yellow=True, )
                return
            if self.disconnected_callback_called:
                xreport('BtThBleakClient.notification', self.device_name, f"disconnected_callback_called is True", yellow=True, )
                return
            # defensive test against disconnection in progress
            if not getattr(self, 'is_connected', True):
                xreport('notification', 'not connected, ignoring notification from %s' % (uuid_to_name(sender.uuid), ), red=True, )
                return
            try:
                _ = self.services
            except BleakError as e:
                xreport('BtThBleakClient', 'BleakDBusError %s ...' % (e, ), red=True, )
                await asyncio.sleep(2)
                return 
            self.last_data_time = time()
            uuid = characteristic.uuid
            uuid_name = uuid_to_name(uuid)
            #self.dataQueue.put((self.device_name, uuid_name, data, ))
            index = self.registers_index
            try:
                self.registers[index]['parser'](data)
            except Exception as e:
                logging.exception(f"Exception in BtTh.notification: {e}")
                print(traceback.format_exc(), file=sys.stderr)

            #if not self.controlQueue.is_empty():
            #    control = self.controlQueue.get()
            #    logging.info(f"BtThBleakClient.notification: control: {control}")
                #if control['name'] == 'Light On/Off':
                #    # write light on/off
                #    request = self.create_generic_read_request(self.device_id, 6, 0x120, 1)
            await asyncio.sleep(1)
            await self.read_registers('notification')  # restart reading registers
        except BleakError as e:
            logging.exception(f"BleakError in BtTh.notification: {e}")
            print(traceback.format_exc(), file=sys.stderr)
        except Exception as e:
            logging.exception(f"Exception in BtTh.notification: {e}")
            print(traceback.format_exc(), file=sys.stderr)

    async def read_registers(self, msg):

        logging.info(f"read_registers[{msg}]: {self.device_name} controlQeueue: {self.controlQueue.qsize()} dataQueue: {self.dataQueue.qsize()}")
        if not self.controlQueue.empty():
            control = self.controlQueue.get()
            xreport('BtThBleakClient', self.device_name, f"read_registers: control: {control} load_status: {self.load_status}", yellow=True)
            if self.device_name.lower() == control[0].lower():
                match control[1]:
                    case 'set':
                        device_name, op, addr, description, value = control
                        await self.check_events_queues(control)
                        pass
                    case 'toggle_load':
                        try:
                            await self.set_register(0x10a, 1 if self.load_status=='off' else 0,)
                            return
                        except Exception as e:
                            logging.info(f"Failed to set load: {e}")
                            logging.info(traceback.print_exc())
                        pass
            else:
                xreport('BtThBleakClient', self.device_name, f"read_registers: control: {control} does not match device_name: {self.device_name}", yellow=True)
                return


        old_index = self.registers_index
        self.registers_index = 0 if self.registers_index is None else self.registers_index + 1

        #logging.info(f"read_registers[{msg}:{self.registers_index}] first: {self.registers_first} model: {self.model} nickname: {self.device_nickname}, len: {len(self.registers)}")

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

        name = self.registers[index]['name']
        #logging.info(f"read_registers[{msg}:{index}] {name} first: {self.registers_first} old: {old_index} {self.registers[index]['register']:04x}:{self.registers[index]['words']}")
        request = self.create_generic_read_request(self.device_id, 3, self.registers[index]['register'], self.registers[index]['words']) 
        await self.write_gatt_char(self.BT_TH_WRITE, request, )


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

    def queueData(self, data):
        #xreport('BtThBleakClient', self.device_name, f"queueData: {data}", yellow=True)
        self.dataQueue.put((self.device_name, data, ))

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
        #logging.info(f"status: {status:04x} load:{status >> 7:02x} charging:{status & 0xff:02x} ")

        data['light_charging_state'] = (0x120, [hex(status>>7), hex(status&0xff)], False, ) # high byte first, low byte second
        data['load_status'] = (0x120, LOAD_STATE.get(status >> 7+8), False)                      # high byte
        self.load_status = data['load_status'][1]
        data['charging_status'] = (0x44, CHARGING_STATE.get(status & 0xff), False)             # low byte

        fault121 = data['controller_fault_warnings_121'][1]
        fault122 = data['controller_fault_warnings_122'][1]
        #logging.info(f"faults: {fault121:04x} {fault122:04x} ")
        faults = [hex(fault121>>7), hex(fault121&0xff), hex(fault122>>7), hex(fault122&0xff)]
        #logging.info(f"faults: {faults} ")
        data['controller_fault_warnings'] = (0x121, faults, False)                      # high byte
        #data['controller_fault_warnings'] = (0, f"{data['controller_fault_warnings_raw'][1]:08x}", False, )


        #self.check_events_queues(data)
        #self.data.update(data)
        self.queueData(data)

    # YYY
    def parse_device_info(self, bs):
        #logging.info(f"parse_device_info: {self.device_name}")
        try:
            data = {}
            data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
            data['device_name'] = (0, self.device_name, False)

            def xget_nickname(device_name):
                return next((name for m, name in nicknames if m == device_name), None)

            def get_nickname(device_name):
                #logging.debug(f"get_nickname: device_name: {device_name}")
                #logging.debug(f"get_nickname: nicknames: {self.nicknames}")
                #return next((name for m, name in self.nicknames if m == device_name), 'N/F')
                return next((name for m, name in self.nicknames if m.strip() == device_name.strip()), '')


            #def get_nickname(name):
            #    if self.nicknames is None: return None
            #    return next((name for m, name in self.nicknames if m == name), None)

            device_nickname = get_nickname(self.device_name)
            data['device_nickname'] = (0, device_nickname, False)
            self.device_nickname = device_nickname
            #logging.info(f"parse_device_info: device_nickname: {data['device_nickname']}")


            data['max_voltage_rated_current'] = (0x0a, bytes_to_int(bs, 3, 2), False)
            data['discharging_current_product_type'] = (0x0b, bytes_to_int(bs, 5, 2), False)
            #logging.info(f"model bs[7:23]: {bs[7:23]}")
            model = (bs[7:23]).decode('utf-8').strip()
            data['model'] = (0x0c, model, False)
            self.model = model
            #logging.info(f"parse_device_info: model: {self.model}")

            #data['software_version'] = (0x14, (bs[24:27]).decode('utf-8').strip(), False)
            #data['hardware_version'] = (0x16, (bs[28:31]).decode('utf-8').strip(), False)
            #data['serial_number'] = (0x18, (bs[28:31]).decode('utf-8').strip(), False)
            data['device_id_raw'] = (0x1a, bytes_to_int(bs, 32, 2), False)
            data['device_id_low'] = (0x1a, bytes_to_int(bs, 32, 2)&0xff, False)
            data['device_id_high'] = (0x1a, bytes_to_int(bs, 32, 2)>>8, False)
            data['device_id'] = (0x1a, bytes_to_int(bs, 32, 2)&0xff, False)
            #logging.info(f"parse_device_info: {data}")
            #self.data.update(data)
            self.queueData(data)
            #self.sections.pop(0) # remove device info from sections
        except Exception as e:
            #logging.exception(f"Exception in BtThBleakClient.parse_device_info: {e}")
            print(traceback.format_exc(), file=sys.stderr)

        #xreport('BtThBleakClient', self.device_name, f"parse_device_info: {data}", yellow=True,)
        self.queueData(data)

    def parse_device_address(self, bs):
        #logging.info("")
        #logging.info(f"parse_device_address: -----------------------------------------------------------------")
        data = {}
        data['device_id'] = (0x1a, bytes_to_int(bs, 4, 1), False)
        #self.data.update(data)
        self.queueData(data)



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

        #self.data.update(data)
        self.queueData(data)


    def parse_load_state(self, bs):
        #logging.info("")
        #logging.info(f"parse_load_state: -----------------------------------------------------------------")

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
        #logging.info(f"status: {status:04x} load:{status >> 7:02x} charging:{status & 0xff:02x} ")

        data['light_charging_state'] = (0x120, [hex(status>>7), hex(status&0xff)], False, ) # high byte first, low byte second
        data['load_status'] = (0x120, LOAD_STATE.get(status >> 7+8), False)                      # high byte
        self.load_status = data['load_status'][1]
        data['charging_status'] = (0x44, CHARGING_STATE.get(status & 0xff), False)             # low byte

        fault121 = data['controller_fault_warnings_121'][1]
        fault122 = data['controller_fault_warnings_122'][1]
        #logging.info(f"faults: {fault121:04x} {fault122:04x} ")
        faults = [hex(fault121>>7), hex(fault121&0xff), hex(fault122>>7), hex(fault122&0xff)]
        #logging.info(f"faults: {faults} ")
        data['controller_fault_warnings'] = (0x121, faults, False)                      # high byte
        #data['controller_fault_warnings'] = (0, f"{data['controller_fault_warnings_raw'][1]:08x}", False, )


        #self.data.update(data)
        self.queueData(data)
        #self.check_events_queues(data)

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
        #self.data.update(data)
        #xreport('BtThBleakClient', self.device_name, f"parse_battery_info: {data}", yellow=True,)
        self.queueData(data)
        #tl = [ ]
        #for key, value in data.items():
        #    tl.append((key, value))
        #tl_table = tabulate(tl, headers=['Name', 'Value'], tablefmt='grid')
        #tl_lines = tl_table.split('\n')
        #for l in tl_lines:
        #    logging.info(f"parse_battery_info: {l}")

    def parse_set_load_response(self, bs):
        xreport('BtThBleakClient', self.device_name, f"parse_set_load_response: {bs}", yellow=True,)
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)), False)
        #data['load_status'] = (bytes_to_int(bs, 5, 1)
        data['load_status'] = (0x120, LOAD_STATE.get(bytes_to_int(bs, 5, 1)), False)                      # 0x120
        #self.data.update(data)
        xreport('BtThBleakClient', self.device_name, f"parse_set_load_response: {data}", yellow=True,)
        self.queueData(data)

    def parse_write_response(self, bs):
        data = {}
        data['function'] = (0, FUNCTION.get(bytes_to_int(bs, 1, 1)))
        response = bytes_to_int(bs, 5, 2)
        #logging.info(f"parse_write_response: {response:04x}")
        #self.data.update(data)

    def reset_factory(self):
        #logging.info(f"reset_factory")
        request = self.create_generic_read_request(self.device_id, 0x78, None, None)
        #logging.info(f"set_register: {[hex(v) for v in request]} {value}")
        #asyncio.create_task(self.ble_manager.characteristic_write_value(request))

    def reset_history(self):
        #logging.info(f"reset_history")
        request = self.create_generic_read_request(self.device_id, 0x79, None, None)
        #logging.info(f"set_register: {[hex(v) for v in request]} {value}")
        #asyncio.create_task(self.ble_manager.characteristic_write_value(request))

    async def set_register(self, register, value):
        try:
            xreport('BtThBleakClient', self.device_name, f"set_register: {register:04x} {value}", yellow=True)
            #logging.info(f"set_register: {register:04x} {value}")
            request = self.create_generic_read_request(self.device_id, 6, register, value)
            await self.write_gatt_char(self.BT_TH_WRITE, request, )
            #logging.info(f"set_register: {[hex(v) for v in request]} {value}")
            #asyncio.create_task(self.ble_manager.characteristic_write_value(request))
        except Exception as e:
            logging.info(f"Failed to set register: {e}")
            logging.info(traceback.print_exc())

    async def set_load(self, value = 0):
        #request = self.create_generic_read_request(self.device_id, self.set_load_params["function"], self.set_load_params["register"], value)
        #asyncio.create_task(self.ble_manager.characteristic_write_value(request))
        xreport('BtThBleakClient', self.device_name, f"set_load: {value}", yellow=True)
        try:
            await self.set_register(0x10a, value)
        except Exception as e:
            logging.info(f"Failed to set load: {e}")
            logging.info(traceback.print_exc())



    async def check_events_queues(self, register, description, value_str):
        try:
            # Step 1: normalize register
            #register = int(register_raw, 0)  # handles int or '0xe008' style

            # Step 2: look up register definition
            regdef = next(
                (r for r in self.battery_info_registers if r[0] == description and r[1] == register),
                None
            )
            if not regdef:
                logging.warning(f"No matching register found for {description} ({register:04x})")
                return

            desc, addr, nbytes, scale, editable = regdef

            if not editable:
                logging.warning(f"Register {desc} ({addr:04x}) is not editable")
                return

            # Step 3: convert value
            value_f = float(value_str)
            scaled = round(value_f / scale)

            logging.info(f"Writing to {desc} @ {addr:04x}: raw={value_f} scaled={scaled}")
            await self.set_register(addr, scaled)

        except Exception as e:
            logging.info(f"Failed to process register update: {register_raw}, {description}, {value_str}")
            logging.info(traceback.print_exc())
  

