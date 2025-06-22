import sys
import asyncio
import async_timeout
import signal
from colored import cprint, fg, bg, attr, set_tty_aware
from time import time, sleep
from datetime import timedelta, datetime
from bleak import BleakClient
from bleak.exc import BleakError
from bleak.uuids import uuid16_dict, uuid128_dict, uuidstr_to_str, register_uuids

#from bleak.backends.corebluetooth import CBCharacteristicProperties

#from bleak_retry_connector import establish_connection

import platform
from functools import partial
from bleak import BleakScanner
from enum import Enum, IntEnum

import traceback
from lib.lib import bytes2str, uuid_to_name, name_to_uuid

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

#register_uuids(Polar_UUIDS)

#OxySmart_UUIDS = {
#}
#6e400001-b5a3-f393-e0a9-e50e24dcca9e (Handle: 6): Nordic UART Service
#6e400002-b5a3-f393-e0a9-e50e24dcca9e (Handle: 7): Nordic UART RX (write-without-response,write), Value: None
#6e400003-b5a3-f393-e0a9-e50e24dcca9e (Handle: 9): Nordic UART TX (notify), Value: None

statistics = {}

# super class ble client to handle notifications and data collection and get consistent exception handling
class MyClient:
    def __init__(self, device, client, aevents, ):
        self.device = device
        self.client = client
        self.aevents = aevents
        self.services = {}
        self.characteristics = {}
        self.start_time = time()
        xreport('myclient', '__init__', 'start %s' % (self.device.name, ), green=True, )

    #def notification(self, sender, data, device_name=None, supported_devices=None ):
    def notification(self, sender, data, device_name=None, ):
        try:
            xreport('notification', 'notification %s %s' % (uuid_to_name(sender.uuid), bytes2str(data), ), yellow=True, )
            found = False
            if device_name not in statistics:
                statistics[device_name] = {}

            if False:
                supported_devices = []
                for device in supported_devices:
                    if device.data_check(sender.uuid):
                        #xreport('notification', 'data_check %s True' % (device.name), )
                        device.notification(sender.uuid, data, device_name=device_name, statistics=statistics)
                        #  def notification(self, uuid, data, device_name=None, statistics=None):
                        found = True
                    #else:
                    #    xreport('notification', 'data_check %s False' % (device.name), )

            if not found:
                xreport('notification', '%s:%s' % (uuid_to_name(sender.uuid), len(data), ))
            #if sender.uuid == POLAR_PMD_DATA:
            #    notification(sender, data, device_name)
            #    return
            measurement_name = uuid_to_name(sender.uuid)
            if measurement_name not in statistics[device_name]:
                statistics[device_name][measurement_name] = 0
            statistics[device_name][measurement_name] += 1
        except Exception as e:
            print(e)
            print(traceback.format_exc(), file=sys.stderr)

    
    def report(self, operation='', msg='-', yellow=False, red=False, green=False, blue=False ):
        #elapsed = int(time() - self.start_time)
        #cprint ('[%3d:%02d %-20s %22s] %s' % (elapsed//60, elapsed%60, self.device.name, operation, msg), file=sys.stderr, fore_256=fore, back_256=back)
        xreport(self.device.name, operation, msg, yellow=yellow, red=red, green=green, blue=blue, )

    def disconnected_callback(self, client, device_name=None, aevents=None):
        xreport(operation='disconnected', msg='', red=True, )
        #disconnect_event.set()

    def is_connected(self):
        return self.client.is_connected

    async def disconnect(self):
        return await self.client.disconnect()

    async def write_gatt_char(self, char_uuid, command, ):

        if self.aevents.is_shutdown():
            xreport('write_gatt_char', '%s %s task_stop_event set' % (char_uuid, bytes2str(command ), uuid_to_name(char_uuid), ))
            return False

       # print('[%-30s %4s] %s %s' % (name, service, bytes2str(command), msg), file=sys.stderr)
        try:
            await self.client.write_gatt_char(char_uuid, command)

        except EOFError as e:
            #self.task_stop_event.set()
            xreport('write_gatt_char', 'EOFError %s ...' % (e, ), red=True, )
            await asyncio.sleep(2)
            return False
            #print('[%-30s %4s] EOFError %s ...' % (name, service, e), file=sys.stderr)
        except BleakError as e:
            #self.task_stop_event.set()
            xreport('write_gatt_char', 'BleakDBusError %s ...' % (e, ), red=True, )
            await asyncio.sleep(2)
            return False
        except Exception as e:
            await asyncio.sleep(2)
            print(traceback.format_exc(), file=sys.stderr)
            return False
        return True

    async def read_gatt_char(self, char_uuid, ):

        #if self.task_stop_event.is_set():
        if self.aevents.is_shutdown():
            xreport('read_gatt_char', '%s task_stop_event set' % (uuid_to_name(char_uuid), ))
            return None

        response = None
        try:
            #xreport('read_gatt_char', '%s: start' % (char_uuid, ))
            #xreport('read_gatt_char', '%s: start' % (uuid_to_name(char_uuid), ))
            response = await self.client.read_gatt_char(char_uuid)

        except EOFError as e:
            #self.task_stop_event.set()
            xreport('read_gatt_char', 'EOFError %s ...' % (e, ), red=True, )
            await asyncio.sleep(2)
            return None
        except BleakError as e:
            #self.task_stop_event.set()
            xreport('read_gatt_char', 'BleakDBusError %s ...' % (e, ), red=True, )
            print(traceback.format_exc(), file=sys.stderr)
            await asyncio.sleep(2)
            return None
        xreport('read_gatt_char', '%s: %s' % (uuid_to_name(char_uuid), bytes2str(response) if response else 'None'))
        return response

    #async def start_notify(self, char_uuid, notification, supported_devices, ):
    async def start_notify(self, char_uuid, notification, ):

        #if self.task_stop_event.is_set():
        if self.aevents.is_shutdown():
            xreport('start_notify', '%s task_stop_event set' % (uuid_to_name(char_uuid), ))
            return False

        xreport('start_notify', '%s' % (uuid_to_name(char_uuid), ))
        try:
            #await self.client.start_notify(char_uuid, partial(self.notification, device_name=self.device.name, supported_devices=supported_devices, ))
            await self.client.start_notify(char_uuid, partial(self.notification, device_name=self.device.name, ))

        except BleakError as e:
            xreport('start_notify', 'BleakDBusError %s ...' % (e, ), red=True, )
            await asyncio.sleep(2)
            return False
        xreport('start_notify', '%s OK' % (uuid_to_name(char_uuid), ))
        return True

    

