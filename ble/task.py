import sys
import asyncio
import async_timeout
import signal
from time import time, sleep
from datetime import timedelta, datetime
from bleak import BleakClient
from bleak.exc import BleakError
from bleak.uuids import uuid16_dict, uuid128_dict, uuidstr_to_str, register_uuids
import random
import platform
from functools import partial
from bleak import BleakScanner
from enum import Enum, IntEnum
import traceback

from lib.lib import bytes2str, uuid_to_name, name_to_uuid

from ble.btth import BtThBleakClient
from ble.client import MyClient

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

SupportedDevices = {
#        'Moxy5': MoxyBleakClient,
        'BT-TH': BtThBleakClient,
        'Unknown': BleakClient,
}



#register_uuids(Polar_UUIDS)

#OxySmart_UUIDS = {
#}
#6e400001-b5a3-f393-e0a9-e50e24dcca9e (Handle: 6): Nordic UART Service
#6e400002-b5a3-f393-e0a9-e50e24dcca9e (Handle: 7): Nordic UART RX (write-without-response,write), Value: None
#6e400003-b5a3-f393-e0a9-e50e24dcca9e (Handle: 9): Nordic UART TX (notify), Value: None

statistics = {}

supported_characteristics = {
    'Battery Service': {
        'read': ['Battery Level'],
        'notify': [],
        'ignore': [],
    },
    'Current Time Service': None, 
    'Heart Rate': {
        'read': ['Heart Rate Control Point'],
        'notify': ['Heart Rate Measurement'],
        'ignore': ['Body Sensor Location'],
    },
    'Device Information': {
        'read': [
            'Manufacturer Name String', 'Model Number String', 'Serial Number String', 
            'Hardware Revision String', 'Firmware Revision String', 'Software Revision String', 
            ],
        'ignore': ['PnP ID', 'System ID', 'IEEE 11073-20601 Regulatory Certification Data List', ],
    },
}
old_supported_characteristics = {
    "Moxy SMO2 Service": { 
        'read': [],
        'notify': ["Moxy SMO2 Data"],
        'ignore': [
            "Moxy SMO2 Data Packet",
            "Moxy SMO2 Data Point Value",
            "Moxy SMO2 Data Point Control",
            "Moxy SMO2 Data Range Request",
            "Moxy SMO2 Data Point Upload",
        ]
    },
    "Polar Feature Configuration Service": { 
        'notify': ["Polar PFC Control Point"],
    },
    "Polar Measurement Data Service": {
        'notify': [
            "Polar PMD Control Point",
            "Polar PMD Data",
        ],
    }, 
    "ZwiftPlay Service": {
        'notify': ["ZwiftPlay Data", "ZwiftPlay Left", "ZwiftPlay Right", "ZwiftPlay Response" ],
        #'notify': ["ZWIFTPLAY_DATA", ],
        #'read': ["ZWIFTPLAY_CP", ],
    },
    "VO2_MASTER_CUSTOM_SERVICE": {
        'notify': ["COM_OUT_UUID", 
                   "AMBIENT_GAS_CALIBRATION_CHARACTERISTIC",
                   "VENTILATORY_CHARACTERISTIC",
                   "GAS_EXCHANGE_CHARACTERISTIC",
                   "SYRINGE_FLOW_CALIBRATION_CHARACTERISTIC",
                   "ENVIRONMENT_CHARACTERISTIC",
                   ],
    },

    "Nordic UART Service": {
        'notify': ["Nordic UART TX", "Nordic UART RX", ],
    },
    "BT_TH Data Service": {
        'read': [],
        'notify': ["BT_TH Data"],
        'ignore': [ ""]
    },
    "BT_TH Write Service": {
        'read': [],
        'notify': [""],
        'ignore': [ "BT_TH Write"]
    }, 
}



# explore the device, use start_notify to receive updates of characteristics and start data collection,
# await stop_notify to stop receiving updates and stop data collection
#async def device_explore(myclient, device, aevents, supported_devices,):
async def device_explore(client, device, aevents, ):


    xreport('Connected', f'{device.name}', green=True)
    #print(f"device_explore {client}", file=sys.stderr)

    def supported_characteristic(service_name, characteristic_name, characteristic_type):

        xreport('supported_characteristic', 'type: %s service: %s name: %s' % (characteristic_type, service_name, characteristic_name), blue=True, )
        if service_name not in supported_characteristics or supported_characteristics[service_name] is None:
            xreport('service not supported', '%s %s:%s UNKNOWN' % (characteristic_type, service_name, characteristic_name), )
            return False
        if characteristic_type not in supported_characteristics[service_name]:
            xreport('characteristic not supported', '%s %s:%s NONE' % (characteristic_type, service_name, characteristic_name), )
            return False
        if uuid_to_name(char_uuid) not in supported_characteristics[service_name][characteristic_type]:
            xreport('uuid not supported', '%s %s:%s' % (characteristic_type, service_name, characteristic_name), )
            return False
        return True

    device_name = device.name

    # Look at Services
    try:
        services = {}
        xreport('service', device_name, 'Reviewing generic services', green=False, )
        for i, service in enumerate(client.services):
            xreport('service', device_name, '-------------------------------------------------------------------------------------------')
            xreport(f"service[{i}]", f'{service}', green=True)
            xreport(f"service[{i}]", f'{service.characteristics}', green=True)
            service_name = uuid_to_name(service.uuid)
            services[service.uuid] = []
            xreport(f"service[{i}]", '%s' % (service_name, ), green=True, )

            chars = [ char.uuid for char in service.characteristics ]

            reads = [ char.uuid for char in service.characteristics if 'read' in char.properties ]
            read_names = [ uuid_to_name(char.uuid) for char in service.characteristics if 'read' in char.properties ]
            notifications = [ char.uuid for char in service.characteristics if 'notify' in char.properties or 'indicate' in char.properties ]
            notification_names = [ uuid_to_name(char.uuid) for char in service.characteristics if 'notify' in char.properties or 'indicate' in char.properties ]

            xreport(f"service[{i}]", '%s: %d characteristics' % (service_name, len(service.characteristics), ), blue=False, )
            #xreport('service_name', '%s: %d characteristics' % (uuid_to_name(service_name), len(service.characteristics), ), blue=True, )


            xreport(f"service[{i}]", 'chars', '%s characteristics' % (reads, ), blue=True, )
            xreport(f"service[{i}]", 'reads', '%s read characteristics' % (reads, ), blue=False, )
            xreport(f"service[{i}]", 'read_names', '%s read names' % (read_names, ), blue=False, )
            xreport(f"service[{i}]", 'notifications', '%s notification characteristics' % (notifications, ), blue=False, )
            xreport(f"service[{i}]", 'notification_names', '%s notification names' % (notification_names, ), blue=True, )


            if reads != []:
                for k, r in enumerate(read_names):
                    xreport(f"service[{i}]", 'reads', '%d: %s' % (k, r, ), green=True, )

            if notifications != []:
                #myclient.report('notifications', '%s' % (notifications, ))
                for k, n in enumerate(notification_names):
                    xreport(f"service[{i}]", 'notifications', '%d: %s' % (k, n, ), green=True, )

            for j, char_uuid in enumerate(reads):
                characteristic_name = uuid_to_name(char_uuid)
                if not supported_characteristic(service_name, characteristic_name, 'read'):
                    continue
                response = await client.read_gatt_char(char_uuid)
                #print('READ: %s' % (char_uuid, ), file=sys.stderr)
                #print('READ: %s' % (uuid_to_name(char_uuid), ), file=sys.stderr)
                if response is None:
                    xreport(f"service[{i}:{j}]", 'read', '%s read failed' % (char_uuid, ), yellow=True,)
                    return False
                if 'string' in uuid_to_name(char_uuid):
                    response = bytes2str(response)
                xreport(f"service[{i}:{j}], read", '%s:%s %s' % 
                    (service_name, characteristic_name,
                     ''.join(map(chr, response)) if 'string' in uuid_to_name(char_uuid).lower() else bytes2str(response), 
                                                          ), green=True,)

            xreport(f"service[{i}]", 'notifications', 'Looking for notifications', notifications, green=True, )
            for j, char_uuid in enumerate(notifications):
                xreport(f"service[{i}:{j}]", 'notifications', 'check %s' % (char_uuid, ), green=True, )
                if not supported_characteristic(service_name, uuid_to_name(char_uuid), 'notify'):
                    continue
                xreport(f"service[{i}:{j}]", 'start_notify', char_uuid, green=True, ) 
                #if not await myclient.start_notify(char_uuid, myclient.notification, supported_devices, ):
                if not await client.start_notify(char_uuid, client.notification, ):
                    xreport(f"service[{i}:{j}]", 'start_notify', 'Failed', yellow=True, ) 
                    return False
    except Exception as e:
        logging.exception('f"service[{i}]", device_explore: generic %s' % (e, ))
        print('Exception: %s' % (e, ), file=sys.stderr)
        traceback.print_exc()
        return False
    return True

def get_bleak_client_class(device_name: str):
    for prefix, client_class in SupportedDevices.items():
        if device_name.startswith(prefix):
            return client_class
    return SupportedDevices["Unknown"]


# disconnected_callback is called when the device is disconnected, set the disconnect_event to notify the device_task to stop
def disconnected_callback(client, aevents=None, device_name=None, disconnect_event=None):
    try:
        xreport(device_name, 'disconnected_callback', 'Device disconnected', red=True, )
        client.disconnected_callback_called = True
        aevents.set(disconnect_event)
    except Exception as e:
        logging.exception('Exception in disconnected_callback')
        print(traceback.format_exc(), file=sys.stderr)


async def device_task(device, active=None, aevents=None, controlQueue=None, dataQueue=None,  ):
    device_name = device.name
    if not controlQueue or not dataQueue:
        print('device_task: controlQueue and dataQueue must be provided')
        raise ValueError("controlQueue and dataQueue must be provided")

    logging.info(f"device_task: %s controlQueue: %s dataQueue: %s" % (device_name, controlQueue, dataQueue, ))
    try:
        xreport(device_name, 'device_task starting', blue=True, )
        client_task_event = f"{device_name.strip()}_client_task_event"
        await aevents.wait(client_task_event, timeout=0.001, )  # creates the event

        while not aevents.is_shutdown():
            try:
                bleak_client = get_bleak_client_class(device_name)
                async with bleak_client(device, active=None, aevents=aevents, controlQueue=controlQueue, dataQueue=dataQueue, timeout=10.0,
                                        disconnected_callback=partial(disconnected_callback, aevents=aevents, device_name=device_name, disconnect_event=client_task_event)
                                        ) as client:
                    try:
                        if False:
                            result = await device_explore(client, device, aevents, )
                            xreport(client_task_event, 'waiting for stop event')
                            await aevents.wait(client_task_event, timeout=1.0, )  # wait for the task to be stopped
                            aevents.clear(client_task_event)  # reset the event so we can wait again

                        xreport(device_name, 'Start',  blue=True, )
                        await client.start()
                        status = aevents.status(client_task_event)
                        if status == aevents.EventStatus.SET:
                            xreport(device_name, client_task_event, f"Event {status}, exiting loop", blue=True, )
                            break
                        xreport(device_name, 'Wait for shutdown',  blue=True, )

                        # Wait for:
                        #   - monitor for lack of data, will restart if no data received for a while
                        #   - stop event to be set, which will stop the task
                        #   - disconnect - this will be handled by the disconnected_callback which will set the client_task_event
                        #
                        while not aevents.is_shutdown():
                            result = await aevents.wait(client_task_event, timeout=5.0, )  # wait for the task to be stopped
                            status = aevents.status(client_task_event)
                            #xreport(device_name, client_task_event, 'wait status: %s is_set: %s' % (status, aevents.is_set(client_task_event)), blue=True, )
                            aevents.clear(client_task_event)  # reset the event so we can wait again
                            if status == aevents.EventStatus.TIMEOUT:
                                if client.no_data_restart_needed():
                                    xreport(device_name, client_task_event, 'No data received, restarting client', red=True, )
                                    break
                                continue
                            if status == aevents.EventStatus.SET:
                                xreport(device_name, client_task_event, f"Event {status}", blue=True, )
                                continue
                            break
                                    #print('device_task status: %s' % (status, ), file=sys.stderr)
                            #if aevents.is_shutdown():
                            #    xreport(device_name, 'device_task', 'Shutdown event set, exiting', yellow=True, )
                            #    break
                            xreport(device_name, 'device_task', 'Waiting for stop event', blue=True, )
                    except Exception as e:
                        logging.exception('Exception in device_task')
                        print(traceback.format_exc(), file=sys.stderr)
                        break
                    finally:
                        try:
                            xreport(device_name, 'device_task', 'Finally Disconnecting', blue=True, )
                            if client.is_connected:
                                await client.disconnect()
                                xreport(device_name, 'device_task', 'Finally Disconnecting', yellow=True, )
                        except Exception as e:
                            xreport(device_name, 'device_task', 'Exception %s' % (e, ), red=True, )
                            print(traceback.format_exc(), file=sys.stderr)

                xreport(device_name, 'device_task', 'Normal Disconnect', grey=True, )
            
            # catch exceptions and retry or exit as necessary
            except asyncio.exceptions.TimeoutError as e:
                xreport('Connection', 'Timeout e: %s NORMAL')
                #print(traceback.format_exc(), file=sys.stderr)
                #self.task_stop_event.set()
                continue
            except BleakError as e:
                logging.exception('BleakError waiting for client.connect')
                xreport('BleakError waiting for client.connect e: %s NORMAL' % (e), yellow=True, )
                print(traceback.format_exc(), file=sys.stderr)
                #self.task_stop_event.set()
                return
            except Exception as e:
                logging.exception('Exception waiting for client.connect')
                print(traceback.format_exc(), file=sys.stderr)
                #self.task_stop_event.set()
                continue

            xreport(device_name, 'device_task', 'exiting with', yellow=True, )
            break

    except (asyncio.CancelledError, asyncio.exceptions.CancelledError) as e:
        xreport('device_task', 'asyncio.CancelledError in device_task')
        #raise asyncio.CancelledError()
    except Exception as e: 
        logging.exception('Exception in device_task')
        raise asyncio.exceptions.CancelledError()
    finally:
        try:
            xreport(device.name, 'device_task', 'Finally Disconnecting', yellow=True)
            #await myclient.disconnect()
            xreport(device.name, 'Connection', 'Final Disconnect')
        except Exception as e:
            logging.exception('Exception in device_task finally block')
        finally:
            xreport(device.name, 'device_task', 'finished', yellow=True)
        return True

