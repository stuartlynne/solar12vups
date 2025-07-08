#!/usr/bin/env python3.13
# 
# Copyright(c)2025 stuart.lynne@gmail.com
# Made available under the MIT License
# See LICENSE.md
#
# 
import sys
import os
import json
import asyncio
import async_timeout
import signal
from colored import cprint, fg, bg, attr, set_tty_aware
from time import time, sleep
from datetime import timedelta, datetime
from bleak import BleakClient
from bleak.exc import BleakError
from bleak.uuids import uuid16_dict, uuid128_dict, uuidstr_to_str, register_uuids
from threading import Thread, Event
import queue
from queue import Queue
from lib.aevents import AEvents
import traceback
from lib.shutdown import Shutdown
from lib.asyncman import AsyncTaskManager
import tkinter as tk

#from bleak.backends.corebluetooth import CBCharacteristicProperties

#from bleak_retry_connector import establish_connection

import platform
from functools import partial
from bleak import BleakScanner
from enum import Enum, IntEnum

import traceback
from lib.lib import bytes2str, uuid_to_name, name_to_uuid

from gui.gui import SolarMonitorApp
from ble.task import device_task

import logging
from lib.log import setup_logger, xreport
if __name__ == '__main__':
    logger = setup_logger()
    pass
#else:                                     
logger = logging.getLogger(__name__)
logger.info("bleexplorer LOGGER TEST")


import subprocess
import re

class ActiveJSON:

    def __init__(self, activepath=None, ):

        self.activepath = os.path.expanduser(activepath if activepath else "~/solarups_active.json")
        self.active = {'devices': {}}

    def load_active(self):
        if not os.path.exists(self.activepath):
            return self.active
        else:
            f = open(self.activepath, 'r')
            try:
                self.active = json.load(f)
            except json.JSONDecodeError as e:
                logging.exception('load_active: Exception %s' % (e, ))
                print(traceback.format_exc(), file=sys.stderr)
                self.active = { 'devices': {} }
        return self.active

    def save_active(self):
        try:
            with open(self.activepath, 'w') as fp:
                json.dump(self.active, fp, indent=4)
            xreport('blemain:', 'save_active', 'Active devices saved to %s' % (self.activepath, ), grey=True, )
        except Exception as e:
            logging.exception('save_active: writing active.json failed: %s' % (e, ))
            print(traceback.format_exc(), file=sys.stderr)


def disconnect_devices_by_name(name_substring: str):
    if platform.system() != 'Linux':
        return

    """
    Disconnect all Bluetooth devices whose name contains the given substring (case-insensitive)
    using bluetoothctl.
    """
    try:
        # Get device list from bluetoothctl
        result = subprocess.run(
            ['bluetoothctl', 'devices'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        device_lines = result.stdout.strip().split('\n')
        devices = []
        name_substring_lc = name_substring.lower()
        for line in device_lines:
            m = re.match(r"Device ([0-9A-F:]+) (.+)", line)
            if m:
                mac, name = m.groups()
                if name_substring_lc in name.lower():
                    devices.append((mac, name))

        for mac, name in devices:
            xreport('solar12vups', 'Disconnecting', f"{mac} ({name})", red=True, )
            disconnect_result = subprocess.run(
                ['bluetoothctl', 'disconnect', mac],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            xreport('solar12vups', 'Disconnect Result', f"{disconnect_result.stdout.strip()}", red=True, )
        if not devices:
            xreport('solar12vups', 'Disconnect Devices', f"No devices found matching '{name_substring}'", red=True, )
    except Exception as e:
        logging.exception('disconnect_devices_by_name: Exception %s' % (e, ))
        print(traceback.format_exc(), file=sys.stderr)



def handle_task_result(task):
    logger.info('handle_task_result: task: %s' % (task, ))
    name = task.get_name()
    try:
        value = task.result()
        xreport(name, 'Finished', yellow=True)
    except asyncio.CancelledError as e:
        logging.exception('handle_task_result: exception: %s' % (e, ))
    except Exception as e:
        logging.exception('handle_task_result: exception: %s' % (e, ))
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        pass
        

#statistics = {}

# define an exception handler
def exception_handler(loop, context):
    # get details of the exception
    exception = context['exception']
    message = context['message']
    task = context.get('task', None) 
    future = context.get('future', None)
    # log exception
    logging.error(f'Task failed, msg={message}, exception={exception} task={task} future={future}')


async def blemaintask(active=None, shutdown=None, aevents=None, controlQueues=None, dataQueue=None, argv=None, ):


    # get the event loop
    loop = asyncio.get_running_loop()
    # set the exception handler
    loop.set_exception_handler(exception_handler)

    logger = logging.getLogger()
    matchlist = [arg.lower().strip() for arg in argv]
    aevents.start()
    logger.info('blemaintask: aevents started')

    if controlQueues is None or dataQueue is None:
        print('blemaintask: controlQueues and dataQueue must be provided')
        raise ValueError("controlQueues and dataQueue must be provided")

    xreport('blemaintask', 'Scanning', '%s' % (argv), )
    #task_stop_events = {}
    #restart_event = asyncio.Event()


    # detection_callback is called by the scanner when it finds a device.
    # the scanner_control event is used to pause the scanner to allow the bluez
    # stack to manage the client connection.
    tasks = {}
    detection_callbacks = 0
    detection_lasttime = time()
    scanner_results = []
    async def detection_callback(dev=None, ad=None, ):
        #global detection_callbacks
        #global detection_lasttime
        nonlocal detection_callbacks, detection_lasttime, tasks, scanner_results
        detection_callbacks += 1
        # this gives us a tick to show if the scanner is still running


        if False:
            if (time() - detection_lasttime) > 10:
                xreport('blemaintask', 'Detection', '%s' % (detection_callbacks, ), )
                xreport('blemaintask', 'Tasks', '%s' % ([t for t in tasks.keys()]))
                detection_lasttime = time()


        # if the device name is not None and it is not already in the tasks list, then we will check if
        # it is in the supported devices list and if so, we will create an asyncio task for it.
        done = {k:v for k, v in tasks.items() if v.done()  }
        tasks = {k:v for k, v in tasks.items() if not v.done()  }
        devname = dev.name.strip().lower() if dev.name is not None else None
        #logger.info('[%-35s] detection_callback devname: %s matchlist: %s' % ('BleakScanner', devname, matchlist ))
        if devname and any(devname.startswith(prefix) for prefix in matchlist) and devname not in tasks:
            xreport('blemaintask', 'Found', devname, blue=True, )
            scanner_results.append((devname, dev))
            aevents.set('scanner_control')
    try:
        # BleakScanner will run actively scanning. As it finds matching devices it will call the detection_callback.
        # This process will continue inside the with statement until the stop_event is set.
        # The process will wait for the scanner_control event to be set before stopping the scanner.
        # scanner_control will be set when there are scanner results to process OR when the shutdownFlag has been set.
        # N.b. The scanner will stop when the with statement block is exited.
        while not aevents.is_shutdown():
            async with BleakScanner(detection_callback=detection_callback, scanning_mode="active") as scanner:
                while not aevents.is_shutdown():
                    await aevents.wait('scanner_control', )
                    status = aevents.status('scanner_control', )
                    aevents.clear('scanner_control', )
                    #xreport('blemaintask', 'Control', 'Status: %s' % (status, ), )
                    await scanner.stop()
                    if status == aevents.EventStatus.SHUTDOWN:
                        #xreport('blemaintask', 'Shutdown', 'Stopping scanner ...', )
                        break
                    #if aevents.shutdownFlag:
                    #    break
                    for devname, dev in scanner_results:
                        xreport('blemaintask', devname, f"tasks: {tasks}", blue=True, )
                        if devname not in tasks:
                            xreport('blemaintask', devname, f"adding", blue=True, )
                            controlQueue = Queue()
                            controlQueues[devname] = controlQueue
                            tasks[devname] = asyncio.create_task(device_task(dev, active=active,
                                     aevents=aevents, controlQueue=controlQueue, dataQueue=dataQueue,), name=devname,)
                            tasks[devname].add_done_callback(handle_task_result)   
                            xreport('blemaintask', devname, f"tasks: {tasks} added", blue=True, )
                            #xreport('blemaintask', 'sleep 10', devname, )
                            await asyncio.sleep(10)  # give the scanner a tick to process
                    scanner_results = []
                    #xreport('blemaintask', 'Restarting', 'Waiting for scanner_control ...', blue=True, )
                    try:
                        await scanner.start()
                    except AttributeError as e:
                        xreport(f"blemaintask: scanner.stop() skipped: {e}", grey=True)
                    except Exception as e:
                        logging.exception(f"blemaintask: scanner.stop() exception: {e}")




        for name, task in tasks.items():
            #task.stop()
            xreport('blemaintask', 'Stopping', name, )
            was_cancelled = task.cancel()
            try:
                await task
                value = task.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logging.exception('blemaintask: exception: %s' % (e, ))
                pass
        xreport('blemaintask', 'Gathering', '%s' % ([t for t in tasks.keys()]), yellow=True,)
        #done_list = [x for x in tasks if x.done() ]
        for name, task in tasks.items():
            if not task.done():
                xreport('blemaintask', 'Cancelling', name, yellow=True, )
                await task
                #task.cancel()
        await asyncio.gather(*[ task for name, task in tasks.items()], return_exceptions=True)
        xreport('blemaintask', 'Tasks Gathered', '', yellow=True, )

        #for device_name, stats in statistics.items():
        #    logging.info('')
        #    for measurement_name, count in stats.items():
        #        xreport(device_name, measurement_name, 'Count: %d' % (count), )
        #logging.info('')

    except (asyncio.CancelledError, asyncio.exceptions.CancelledError) as e:
        xreport('blemaintask', 'CancelledError', f"CancelledError: {e}", yellow=True, )
    except BleakError as e:
        logging.exception('blemaintask: exception: %s' % (e, ))
        if platform.system() == 'Linux':
            logger.info('[%-30s     ] You may need to restart Linux Bluetooth!' % (''))
        await asyncio.sleep(2)
    except OSError as e:
        logging.exception('blemaintask: exception: %s' % (e, ))
        await asyncio.sleep(2)
    except Exception as e:
        logging.exception('blemaintask: exception: %s' % (e, ))
        await asyncio.sleep(2)
    finally:
        # stop the scanner
        await aevents.set('scanner_control', aevents.EventStatus.SHUTDOWN)
        await asyncio.sleep(1)
        xreport('blemaintask', 'Shutdown', '...', yello=True, )

    xreport('blemaintask', 'Shutdown', 'Complete, exiting blemaintask ...', grey=True, )


def blemainthread(name, root=None, app=None, active=None, aevents=None, 
                  shutdown=None, sigintEvent=None, shutdownEvent=None, controlQueues=None, dataQueue=None, argv=None, ):

    logging.info(f"blemainThread: Starting BLEMainThread ... app: {app}, " )
    logging.info(f"blemainThread: Starting BLEMainThread ... controlQueues: {controlQueues}, " )
    logger = logging.getLogger('BLEMainThread')
    #if not app:
    #    print('blemainthread: app must be provided')
    #    raise ValueError("app must be provided")
    if controlQueues is None or dataQueue is None:
        print('blemainthread: controlQueues and dataQueue must be provided', file=sys.stderr)
        print(f'blemainthread: controlQueues {controlQueues}', file=sys.stderr)
        print(f'blemainthread: dataQueue {dataQueue}', file=sys.stderr)
        raise ValueError("controlQueues and dataQueue must be provided")
    logger = logging.getLogger('BLEMainThread')
    xreport('BLEMainThread', 'blemainthread: Starting AsyncTaskManger', '%s' % (name, ), )
    logger.info('blemainthread: Starting AsyncTaskManager')
    asyncman = AsyncTaskManager()
    asyncman.start()
    xreport('BLEMainThread', 'blemainthread: Starting AEvents', '%s' % (name, ), )
    logger.info('blemainthread: Starting AEvents')
    #aevents = AEvents(shutdown, )
    asyncman.run('blemaintask', blemaintask(active=active, shutdown=shutdown, aevents=aevents, controlQueues=controlQueues, dataQueue=dataQueue, argv=argv, ))

    if False and sys.version_info >= (3, 13): 
        try:
            #while not shutdownEvent.is_set():
            # dataQueue will be ShutDown by the Shutdown handler.
            while True:
                data = dataQueue.get()
                #xreport('blemainthread', 'DataQueue', f"Data: {data[0]} {len(data[1].keys())}") 
                if app:
                    self.app.on_data_received(data[0], data[1])
                else:
                    #xreport('blemainthread', data[0], f"Data: {len(data[1].keys())} {data[1].keys() if data[1] else 'None'}")
                    xreport('blemainthread', data[0], f"Data: {len(data[1].keys())}")
        except queue.ShutDown as e:
            logging.info('blemainthread: queue.ShutDown exception: %s' % (e, ))
        except Exception as e:
            logging.exception('blemainthread: exception: %s' % (e, ))
            print(traceback.format_exc(), file=sys.stderr)
    else:
        logging.info(f"blemainthread: checking ... app: {app}, " )
        try:
            #result = shutdownEvent.wait()
            while not shutdownEvent.is_set() and not sigintEvent.is_set():
                result = shutdownEvent.wait(timeout=1)
                xreport('blemainthread', 'shutdowEvent result', f"result: {result}", blue=True, )
                if not result:
                    while not dataQueue.empty():
                        data = dataQueue.get()
                        #logging.info(f"blemainthread: checking ... app: {app}, " )
                        #xreport('solar12vups', 'DataQueue', f"Data: {data}")
                        if app:
                            app.on_data_received(data[0], data[1])
                        else:
                            #xreport('blemainthread', data[0], f"Data: {len(data[1].keys())} {data[1].keys() if data[1] else 'None'}")
                            try:
                                xreport('blemainthread', data[0], f"Data: {len(data[1].keys())}")
                            except:
                                xreport('blemainthread', data[0], f"Data: {len(data[1])}")
                        continue
        except Exception as e:
            logging.exception('__main__: exception: %s' % (e, ))

    xreport('BLEMainThread', 'blemainthread: Stopping AsyncTaskManager', '%s' % (name, ), )
    asyncman.shutdown()
    shutdown.set('blemaintask', )

    if root:
        xreport('BLEMainThread', 'Shutdown', 'Complete, root.quit() ...', grey=True, )
        root.quit()
        #root.destroy()
        xreport('BLEMainThread', 'Shutdown', 'Complete, cleaning up root.quit() ...', grey=True, )
    xreport('BLEMainThread', 'Shutdown', 'Complete, exiting blemainthread ...', grey=True, )


def join(target_thread=None, count=0):
    if target_thread is None:
        xreport('blemain.join', 'NO THREAD', f"{target_thread} return True", grey=True, )
        return True

    # Do nothing if exit code already exists
    #if target_thread.exitcode is not None:
    #    xreport('blemain.join', 'EXIT CODE', f"{target_thread.exitcode} return True", grey=True, )
    #    return True

    # No exit code, so join
    #if (count > 1):
    #    xreport('dashboard.main', 'TERMINATE', f"count: {count}", grey=True, )
    #    target_thread.terminate()
    xreport('blemain.join', 'JOINING', f"{target_thread}", grey=True, )
    target_thread.join(timeout=.5)

    # check exit code
    #if target_thread.exitcode is not None and target_thread.exitcode == 1:
    #    xreport('blemain.join', 'EXIT CODE', f"{target_thread.exitcode} return True", grey=True, )
    #    return True

    # no exit code, return False
    xreport('blemain.join', 'NO EXIT CODE', f"{target_thread} return False", grey=True, )
    return False



def SolarMain():

    #print('Solar12VUPS SolarMain starting...', file=sys.stderr)
    activeJSON = ActiveJSON(activepath='~/solarups_active.json', )
    active = activeJSON.load_active()

    #setup_logger()
    #logger = logging.getLogger(__name__).info("Starting blemain")
    #logger = setup_logger()
    #logger.info("blemain LOGGER TEST")

    #if len(sys.argv) < 1:
    #    logger.info('Usage: %s <device names>' % (sys.argv[0], ))
    #    sys.exit(1)
    #name = 'Polar' if len(sys.argv) == 1 else sys.argv[1]
    #for i in range(60):
    #    logger.info(f'{i} waiting for logger to start ...')
    #    xreport('solar12vups', 'Waiting for logger to start', '%s' % (i, ), )
    #    sleep(2)
    #logger.info('argv: %s' % (sys.argv, ))

    name = 'BT-TH' 

    #controlQueue = Queue()
    controlQueues = {}
    dataQueue = Queue()


    shutdown = Shutdown()
    events = shutdown.events()
    sigintEvent, shutdownEvent = events[0], events[1]
    #shutdown.add_queue(controlQueue)
    shutdown.add_queue(dataQueue)
    app = None
    root = None

    disconnect_devices_by_name(name)

    aevents = AEvents(shutdown, )
    if True:
        root = tk.Tk()
        if sys.platform == "win32":
            root.iconbitmap("favicon.ico")
        else:
            icon = tk.PhotoImage(file="favicon-strict.png")
            root.iconphoto(True, icon)
        #    root.title("Solar 12V UPS Monitor")

        xreport('solar12vups', 'Tkinter', f"Starting SolarMonitorApp ... root: {root}", grey=True, )
        app = SolarMonitorApp(root=root, client=None, controlQueues=controlQueues, aevents=aevents, active=active, shutdownEvent=shutdownEvent)

    xreport('solar12vups', 'Starting BLEMainThread', '%s' % (name, ), yellow=True, )
    blemain_thread = Thread(target=blemainthread, 
                            kwargs={
                                'root': root,
                                'aevents': aevents,
                                'active': active,
                                'app': app,
                                'name': name,
                                'shutdown': shutdown,
                                'sigintEvent': events[0],
                                'shutdownEvent': events[1],
                                'controlQueues': controlQueues,
                                'dataQueue': dataQueue,
                                #'argv': sys.argv[1:]
                                'argv': name,
                            },
                            name='BLEMainThread', daemon=True)
    blemain_thread.start()


    if root and app:
        xreport('solar12vups', 'Starting SolarMonitorApp', '%s' % (name, ), yellow=True, )
        root.mainloop()
        xreport('solar12vups', 'SolarMonitorApp', 'mainloop() exited ...', yellow=True, )
        shutdown.set('blemaintask', )
    else:
        logger.info('asyncio_stop_event set, waiting for stop_event ...')
        shutdownEvent.wait()

    activeJSON.save_active()

    #asyncio_stop_event.wait()
    xreport('solar12vups', 'Waiting for BLEMainThread to finish ...', red=True, )
    for count in range(10):
        if not blemain_thread.is_alive():
            break
        xreport('solar12vups', count, 'BLEMainThread is still alive, waiting ...', red=True, )
        blemain_thread.join(timeout=1)


    xreport('solar12vups', 'BLEMainThread finished ...', red=True, )

if __name__ == "__main__":
    SolarMain()
