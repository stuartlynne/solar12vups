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
from types import SimpleNamespace

import traceback
from lib.lib import bytes2str, uuid_to_name, name_to_uuid
#from polar import polar, pmd_data_notification, POLAR_PMD_DATA, Polar_Supported_Characteristics, Polar_UUIDS
#from polar import Polar

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

class BleakClientEx(BleakClient):

    def __init__(self, device, active=None, aevents=None, controlQueue=None, dataQueue=None, *args, **kwargs):
        self.device = device if not isinstance(device, dict) else SimpleNamespace(**device)
        self.device_name = getattr(self.device, 'name', '').strip()
        self.device_address = getattr(self.device, 'address', None)
        self.aevents = aevents
        self.controlQueue = controlQueue
        self.dataQueue = dataQueue
        self.no_data_restart_seconds = None
        self.start_time = time()
        self.last_data_time = time()
        self.closing = False
        self.disconnect_called = False
        self.disconnected_callback_called = False
        self.first_data_event = asyncio.Event()
        self.poll_task = None

        bleak_target = kwargs.pop('bleak_target', None)
        if bleak_target is None:
            bleak_target = self.device_address if self.device_address else self.device

        super().__init__(bleak_target, *args, **kwargs)
        logging.info(f"BleakClientEx: %s controlQueue: %s dataQueue: %s" % (self.device_name, controlQueue, dataQueue, ))

        #self.device = device
        #self.start_time = time()
        #xreport('bleak_client', '__init__', 'start %s' % (self.device.name, ), green=True, )
        #self.aevents = kwargs.get('aevents', None)

    def no_data_restart_needed(self):
        try:
            if self.no_data_restart_seconds is None:
                return False
            if self.last_data_time is None:
                return False
            if time() - self.last_data_time > self.no_data_restart_seconds:
                xreport(self.device.name, 'no_data_restart_need', 'last data < %d seconds, need restart' % (time() - self.last_data_time, ), red=True, )
                return True
            #xreport(self.device.name, 'no_data_restart_need', 'no data for %d seconds, restart not needed' % (time() - self.last_data_time, ), red=True, )
            return False
        except Exception as e:
            logging.exception('no_data_restart_needed error: %s', e)
            print(traceback.format_exc(), file=sys.stderr)
    @property
    def is_connected(self):
        return super().is_connected


    async def read_gatt_char(self, char_uuid, ):

        #if self.task_stop_event.is_set():
        if self.aevents.is_shutdown():
            xreport('read_gatt_char', '%s task_stop_event set' % (uuid_to_name(char_uuid), ))
            return None

        response = None
        try:
            #xreport('read_gatt_char', '%s: start' % (char_uuid, ))
            #xreport('read_gatt_char', '%s: start' % (uuid_to_name(char_uuid), ))
            #response = await self.read_gatt_char(char_uuid)
            response = await super().read_gatt_char(char_uuid)

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

    async def start_notify(self, char_uuid, notification, ):

        #if self.task_stop_event.is_set():
        if self.aevents.is_shutdown():
            xreport('start_notify', '%s task_stop_event set' % (uuid_to_name(char_uuid), ))
            return False

        xreport('start_notify', '%s' % (uuid_to_name(char_uuid), ))
        try:
            #await self.start_notify(char_uuid, partial(self.notification, device_name=self.device.name, supported_devices=supported_devices, ))
            #response = await super().start_notify(char_uuid, partial(self.notification, device_name=self.device.name, ))
            response = await super().start_notify(char_uuid, self.notification)
            #response = await super().start_notify(char_uuid, partial(self.notification, device_name=self.device_name, ))

        except BleakError as e:
            xreport('start_notify', 'BleakDBusError %s ...' % (e, ), red=True, )
            await asyncio.sleep(2)
            return False
        xreport('start_notify', '%s OK' % (uuid_to_name(char_uuid), ))
        return True

    async def start(self):
        xreport('ClientEx.start', self.device_name, self.notify_list, yellow=True, )
        # ensure bleak is ready for us and has the services
        #await self.get_services()
        #await self.services
        try:
            _ = self.services
        except BleakError as e:
            xreport('start_notify', 'BleakDBusError %s ...' % (e, ), red=True, )
            await asyncio.sleep(2)
            return False

        for i, (uuid, notification) in enumerate(self.notify_list):
            try:
                await self.start_notify(uuid, notification, )
            except BleakError as e:
                xreport('start_notify', 'BleakDBusError %s ...' % (e, ), red=True, )
                await asyncio.sleep(2)
                return False
            xreport('start_notify', '%s OK' % (uuid_to_name(uuid), ))

        return True

    async def notification(self, characteristic, data, ):
        uuid = characteristic.uuid
        xreport(self.device_name, uuid_to_name(uuid), bytes2str(data), )

    async def disconnect(self):
        self.closing = True
        self.disconnect_called = True
        if self.poll_task is not None:
            self.poll_task.cancel()
            self.poll_task = None
        for uuid, _notification in getattr(self, 'notify_list', []):
            try:
                await super().stop_notify(uuid)
            except Exception:
                pass
        try:
            await super().disconnect()
        except (EOFError, BleakError):
            pass
