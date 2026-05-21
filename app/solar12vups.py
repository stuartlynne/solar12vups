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
import concurrent.futures
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
from enum import Enum, IntEnum
from types import SimpleNamespace

import traceback
from lib.lib import bytes2str, uuid_to_name, name_to_uuid

from gui.gui import SolarMonitorApp
from ble.task import device_task
from remote.task import remote_server_task, DEFAULT_REMOTE_HOST, DEFAULT_REMOTE_PORT

import logging
from lib.log import setup_logger, xreport
if __name__ == '__main__':
    logger = setup_logger()
    pass
#else:                                     
logger = logging.getLogger(__name__)
logger.info("bleexplorer LOGGER TEST")

DEFAULT_BLE_NAME_PREFIXES = ("BT-TH", "BT-1")
ENABLE_REMOTE_BRIDGE = True


import subprocess
import re
from time import sleep
from app.bleio import start_ble_data_io_process, stop_ble_data_io_process

class ActiveJSON:

    def __init__(self, activepath=None, ):

        self.activepath = os.path.expanduser(activepath if activepath else "~/solarups_active.json")
        self.active = {'devices': {}, 'controllers': {}}

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
                self.active = {'devices': {}, 'controllers': {}}
        self.active.setdefault('devices', {})
        self.active.setdefault('controllers', {})
        return self.active

    def save_active(self):
        try:
            with open(self.activepath, 'w') as fp:
                json.dump(self.active, fp, indent=4)
            xreport('blemain:', 'save_active', 'Active devices saved to %s' % (self.activepath, ), grey=True, )
        except Exception as e:
            logging.exception('save_active: writing active.json failed: %s' % (e, ))
            print(traceback.format_exc(), file=sys.stderr)


def disconnect_devices_by_name(name_substring: str, remove=False):
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
            # Give BlueZ and the BT module time to settle before reconnect attempts.
            for _ in range(10):
                info_result = subprocess.run(
                    ['bluetoothctl', 'info', mac],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                info_text = info_result.stdout or ""
                if "Connected: yes" not in info_text:
                    break
                sleep(0.5)
            if remove:
                remove_result = subprocess.run(
                    ['bluetoothctl', 'remove', mac],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                xreport('solar12vups', 'Remove Result', f"{remove_result.stdout.strip()}", red=True, )
            sleep(1.0)
        if not devices:
            xreport('solar12vups', 'Disconnect Devices', f"No devices found matching '{name_substring}'", red=True, )
    except Exception as e:
        logging.exception('disconnect_devices_by_name: Exception %s' % (e, ))
        print(traceback.format_exc(), file=sys.stderr)



def handle_task_result(task):
    logger.info('handle_task_result: task: %s' % (task, ))
    if hasattr(task, 'get_name'):
        name = task.get_name()
    else:
        name = getattr(task, 'name', None) or repr(task)
    try:
        value = task.result()
        xreport(name, 'Finished', yellow=True)
    except asyncio.CancelledError:
        logger.info('handle_task_result: task cancelled: %s', name)
    except concurrent.futures.CancelledError:
        logger.info('handle_task_result: future cancelled: %s', name)
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


def start_ble_discovery_process(matchlist):
    discovery_script = os.path.join(os.path.dirname(__file__), '..', 'tools', 'ble_discovery_worker.py')
    discovery_process = subprocess.Popen(
        [sys.executable, '-u', discovery_script, *matchlist],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    discovery_queue = queue.Queue()

    def read_stdout():
        try:
            for line in iter(discovery_process.stdout.readline, ''):
                line = line.strip()
                if not line:
                    continue
                try:
                    discovery_queue.put(json.loads(line))
                except json.JSONDecodeError:
                    discovery_queue.put({'error': f'invalid discovery json: {line}'})
        finally:
            try:
                discovery_process.stdout.close()
            except Exception:
                pass

    def read_stderr():
        try:
            for line in iter(discovery_process.stderr.readline, ''):
                line = line.strip()
                if line:
                    discovery_queue.put({'error': line})
        finally:
            try:
                discovery_process.stderr.close()
            except Exception:
                pass

    Thread(target=read_stdout, name='BLEDiscoveryStdout', daemon=True).start()
    Thread(target=read_stderr, name='BLEDiscoveryStderr', daemon=True).start()
    return discovery_process, discovery_queue


def stop_ble_discovery_process(discovery_process):
    if discovery_process is None:
        return
    try:
        if discovery_process.poll() is None:
            discovery_process.terminate()
            discovery_process.wait(timeout=5)
    except Exception:
        try:
            discovery_process.kill()
        except Exception:
            pass


async def blemaintask(active=None, shutdown=None, aevents=None, controlQueues=None, dataQueue=None, argv=None, discoveryQueue=None, discoveryProcess=None, ):


    # get the event loop
    loop = asyncio.get_running_loop()
    # set the exception handler
    loop.set_exception_handler(exception_handler)

    logger = logging.getLogger()
    if argv is None:
        raw_matchlist = []
    elif isinstance(argv, str):
        raw_matchlist = [argv]
    else:
        raw_matchlist = list(argv)
    matchlist = [arg.lower().strip() for arg in raw_matchlist if arg and arg.strip()]
    logger.info('blemaintask: matchlist=%s raw=%r', matchlist, argv)
    aevents.start()
    logger.info('blemaintask: aevents started')

    if controlQueues is None or dataQueue is None:
        print('blemaintask: controlQueues and dataQueue must be provided')
        raise ValueError("controlQueues and dataQueue must be provided")

    xreport('blemaintask', 'Scanning', '%s' % (argv), )
    tasks = {}
    try:
        while not aevents.is_shutdown():
            tasks = {k: v for k, v in tasks.items() if not v.done()}
            scanner_results = {}
            if discoveryProcess is not None and discoveryProcess.poll() is not None:
                raise RuntimeError(f"discovery worker exited rc={discoveryProcess.returncode}")

            while discoveryQueue is not None:
                try:
                    message = discoveryQueue.get_nowait()
                except queue.Empty:
                    break

                if 'error' in message:
                    xreport('blemaintask', 'Discovery', message['error'], red=True)
                    continue

                for info in message.get('devices', []):
                    devname = info['name'].strip().lower()
                    if devname in tasks or devname in scanner_results:
                        continue
                    xreport('blemaintask', 'Found', devname, blue=True, )
                    scanner_results[devname] = SimpleNamespace(
                        name=info['name'],
                        address=info['address'],
                    )

            if not scanner_results:
                await asyncio.sleep(1)
                continue

            for devname, dev in list(scanner_results.items()):
                xreport('blemaintask', devname, f"tasks: {tasks}", blue=True, )
                if devname not in tasks:
                    xreport('blemaintask', devname, f"adding", blue=True, )
                    controlQueue = Queue()
                    controlQueues[devname] = controlQueue
                    tasks[devname] = asyncio.create_task(
                        device_task(
                            dev,
                            active=active,
                            aevents=aevents,
                            controlQueue=controlQueue,
                            dataQueue=dataQueue,
                        ),
                        name=devname,
                    )
                    tasks[devname].add_done_callback(handle_task_result)
                    xreport('blemaintask', devname, f"tasks: {tasks} added", blue=True, )
            await asyncio.sleep(1)




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
        await asyncio.sleep(1)
        xreport('blemaintask', 'Shutdown', '...', yello=True, )

    xreport('blemaintask', 'Shutdown', 'Complete, exiting blemaintask ...', grey=True, )


def blemainthread(name, root=None, app=None, active=None, aevents=None, 
                  shutdown=None, sigintEvent=None, shutdownEvent=None, controlQueues=None, dataQueue=None, argv=None,
                  enable_remote=True, enable_discovery=True ):

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
    remote_asyncman = AsyncTaskManager()
    remote_asyncman.start()
    device_asyncman = AsyncTaskManager()
    device_asyncman.start()
    raw_matchlist = [part.lower().strip() for part in name.split(',') if part.strip()]
    discoveryProcess = discoveryQueue = None
    if enable_discovery:
        discoveryProcess, discoveryQueue = start_ble_discovery_process(raw_matchlist)
    xreport('BLEMainThread', 'blemainthread: Starting AEvents', '%s' % (name, ), )
    logger.info('blemainthread: Starting AEvents')
    aevents.loop = device_asyncman.loop
    aevents.start()
    if enable_remote:
        remote_asyncman.run(
            'remote_server_task',
            remote_server_task(
                active=active,
                shutdown=shutdown,
                aevents=aevents,
                controlQueues=controlQueues,
                dataQueue=dataQueue,
                host=DEFAULT_REMOTE_HOST,
                port=DEFAULT_REMOTE_PORT,
            ),
        )

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
        device_tasks = {}
        try:
            while not shutdownEvent.is_set() and not sigintEvent.is_set():
                for devname, task in list(device_tasks.items()):
                    if task.done():
                        handle_task_result(task)
                        device_tasks.pop(devname, None)
                        controlQueues.pop(devname, None)

                if enable_discovery and discoveryProcess is None:
                    discoveryProcess, discoveryQueue = start_ble_discovery_process(raw_matchlist)

                if enable_discovery and discoveryProcess is not None and discoveryProcess.poll() is not None:
                    stderr_text = ''
                    try:
                        stderr_text = discoveryProcess.stderr.read().strip()
                    except Exception:
                        pass
                    xreport('blemainthread', 'Discovery Exit', f"rc={discoveryProcess.returncode} {stderr_text}", red=True)
                    discoveryProcess = None

                if enable_discovery:
                    pending_devices = []
                    while True:
                        try:
                            message = discoveryQueue.get_nowait()
                        except queue.Empty:
                            break

                        if 'error' in message:
                            xreport('blemainthread', 'Discovery', message['error'], red=True)
                            continue

                        for info in message.get('devices', []):
                            devname = info['name'].strip().lower()
                            if devname in device_tasks:
                                continue
                            xreport('blemaintask', 'Found', devname, blue=True, )
                            pending_devices.append(info)

                    for info in pending_devices:
                        devname = info['name'].strip().lower()
                        if devname in device_tasks:
                            continue
                        controlQueue = Queue()
                        controlQueues[devname] = controlQueue
                        device = SimpleNamespace(name=info['name'], address=info['address'])
                        xreport('blemaintask', devname, "adding", blue=True, )
                        task = device_asyncman.run(
                            devname,
                            device_task(
                                device,
                                active=active,
                                aevents=aevents,
                                controlQueue=controlQueue,
                                dataQueue=dataQueue,
                            ),
                        )
                        task.name = devname
                        task.add_done_callback(handle_task_result)
                        device_tasks[devname] = task

                shutdownEvent.wait(timeout=1)
        except Exception as e:
            logging.exception('__main__: exception: %s' % (e, ))

    xreport('BLEMainThread', 'blemainthread: Stopping AsyncTaskManager', '%s' % (name, ), )
    remote_asyncman.shutdown()
    device_asyncman.shutdown()
    stop_ble_discovery_process(discoveryProcess)
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



def SolarMain(enable_ble=True, enable_bleio=True, ble_thread_only=False):

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

    names = list(DEFAULT_BLE_NAME_PREFIXES)

    #controlQueue = Queue()
    controlQueues = {}
    bleDataProcess = bleDataInputQueue = bleDataGuiQueue = bleDataStopEvent = None
    if enable_bleio:
        bleDataProcess, bleDataInputQueue, bleDataGuiQueue, bleDataStopEvent = start_ble_data_io_process()


    shutdown = Shutdown()
    events = shutdown.events()
    sigintEvent, shutdownEvent = events[0], events[1]
    #shutdown.add_queue(controlQueue)
    app = None
    root = None

    if enable_ble:
        for name in names:
            disconnect_devices_by_name(name)

    blemain_thread = None
    try:
        aevents = AEvents(shutdown, )
        if True:
            root = tk.Tk()
            if sys.platform == "win32":
                root.iconbitmap("favicon.ico")
            else:
                icon = tk.PhotoImage(file="favicon-strict.png")
                root.iconphoto(True, icon)

            xreport('solar12vups', 'Tkinter', f"Starting SolarMonitorApp ... root: {root}", grey=True, )
            app = SolarMonitorApp(
                root=root,
                client=None,
                controlQueues=controlQueues,
                aevents=aevents,
                active=active,
                shutdownEvent=shutdownEvent,
                incoming_queue=bleDataGuiQueue,
            )

        if enable_ble or ble_thread_only:
            xreport('solar12vups', 'Starting BLEMainThread', '%s' % (names, ), yellow=True, )
            blemain_thread = Thread(target=blemainthread, 
                                    kwargs={
                                        'root': root,
                                        'aevents': aevents,
                                        'active': active,
                                        'app': app,
                                        'name': ",".join(names),
                                        'shutdown': shutdown,
                                        'sigintEvent': events[0],
                                        'shutdownEvent': events[1],
                                        'controlQueues': controlQueues,
                                        'dataQueue': bleDataInputQueue,
                                        'argv': names,
                                        'enable_remote': enable_ble and ENABLE_REMOTE_BRIDGE,
                                        'enable_discovery': enable_ble,
                                    },
                                    name='BLEMainThread', daemon=True)
            blemain_thread.start()
        else:
            xreport('solar12vups', 'BLE Disabled', 'Starting Tkinter without BLE/discovery threads', yellow=True)

        if root and app:
            xreport('solar12vups', 'Starting SolarMonitorApp', '%s' % (names, ), yellow=True, )
            root.mainloop()
            xreport('solar12vups', 'SolarMonitorApp', 'mainloop() exited ...', yellow=True, )
            shutdown.set('blemaintask', )
        else:
            logger.info('asyncio_stop_event set, waiting for stop_event ...')
            shutdownEvent.wait()

        activeJSON.save_active()

        if blemain_thread is not None:
            xreport('solar12vups', 'Waiting for BLEMainThread to finish ...', red=True, )
            for count in range(10):
                if not blemain_thread.is_alive():
                    break
                xreport('solar12vups', count, 'BLEMainThread is still alive, waiting ...', red=True, )
                blemain_thread.join(timeout=1)

            xreport('solar12vups', 'BLEMainThread finished ...', red=True, )
    finally:
        if bleDataProcess is not None:
            stop_ble_data_io_process(bleDataProcess, bleDataInputQueue, bleDataStopEvent)
        if enable_ble:
            for name in names:
                disconnect_devices_by_name(name, remove=True)

if __name__ == "__main__":
    SolarMain()
