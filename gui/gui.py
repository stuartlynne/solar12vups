import asyncio
import configparser
import os
import tkinter as tk
import queue
import re
from tkinter import ttk
from tkinter import Canvas, Frame, Scrollbar
from datetime import datetime, timedelta
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from collections import deque
import time
import matplotlib.dates as mdates
import traceback

from gui.frameex import FrameEx
from gui.labelex import LabelEditEx
from gui.settingstab import SettingsTab
from gui.powergauge import PowerGaugeTab

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

TRACE_GUI_UPDATES = False
USE_SIMPLE_DEVICE_PLACEHOLDER = False

# Setup logging
#logging.basicConfig(level=logging.INFO)
logging.info("Starting SolarApp Client")

# GUI update interval in ms
UPDATE_INTERVAL = 1000

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self._window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        def _resize_inner_frame(event):
            # Set inner frame width to canvas width
            self.canvas.itemconfig(self._window, width=event.width)

        self.canvas.bind("<Configure>", _resize_inner_frame)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")



class SolarMonitorApp:
    data_history = {
        'time': [],
        'device_nickname': [],
        'battery_voltage': [],
        'load_voltage': [],
        'pv_voltage': [],
        'battery_current': [],
        'load_current': [],
        'pv_current': [],
        'load_power': [],
        'pv_power': [],
        'battery_percentage': [],
        'load_status': [],
        'controller_fault_codes': [],
        'controller_fault_warnings_121': [],
        'controller_fault_warnings_122': [],
    }

    def __init__(self, root=None, client=None, aevents=None, controlQueues=None, shutdownEvent=None, active=None, incoming_queue=None, ):
        self.root = root
        self.client = client
        self.aevents = aevents
        self.controlQueues = controlQueues
        self.shutdownEvent = shutdownEvent
        self.setLoadEvent = None
        self.active = active if active is not None else {'devices': {}}
        self.active.setdefault('devices', {})
        self.root.title("Solar 12Vdc UPS Monitor")
        self.load = 0
        self.ui_update_queue = queue.SimpleQueue()
        self.incoming_queue = incoming_queue
        self.pending_ui_updates = {}
        self._save_geometry_after_id = None

        self._restore_window_geometry()
        self.root.bind("<Configure>", self._on_root_configure)

        xreport('SolarMonitorApp', 'Initializing SolarMonitorApp ', f"root: {self.root} aevents: {self.aevents} controlQueues: {self.controlQueues}", yellow=True)

        self.info = { }

        self.batterySOCSamples = deque()    

        self.settings_tabs = {}
        #self.settings_widgets = {}  # Store FrameEx widgets by key
        #self.values_widgets = {}  # Store values for each FrameEx widget
        self.create_widgets()

        self.check_shutdown()  # Start checking for shutdown events
        self.process_ui_updates()
        self.firstime = datetime.now()

    def _valid_geometry(self, geometry):
        return bool(re.fullmatch(r"\d+x\d+\+\d+\+\d+", str(geometry or "")))

    def _restore_window_geometry(self):
        geometry = self.active.get('window_geometry')
        if self._valid_geometry(geometry):
            self.root.geometry(geometry)
        else:
            self.root.geometry("800x400")

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        if self._save_geometry_after_id:
            try:
                self.root.after_cancel(self._save_geometry_after_id)
            except Exception:
                pass
        self._save_geometry_after_id = self.root.after(300, self._save_window_geometry)

    def _save_window_geometry(self):
        self._save_geometry_after_id = None
        try:
            geometry = self.root.geometry()
            if self._valid_geometry(geometry):
                self.active['window_geometry'] = geometry
        except Exception:
            pass

    def init_device_history(self):
        history = {k: [] for k in self.data_history}
        history['device_nickname'] = ['']
        history['controller_fault_codes'] = ['OK']
        history['controller_fault_warnings_121'] = [0]
        history['controller_fault_warnings_122'] = [0]
        return history

    def _normalize_field_value(self, value, default=''):
        if isinstance(value, tuple) and len(value) >= 2:
            value = value[1]
        if value is None:
            return default
        return value

    def check_shutdown(self):
        if self.shutdownEvent and self.shutdownEvent.is_set():
            xreport('SolarMonitorApp', '', 'Shutdown event detected, closing GUI', blue=True)
            self.root.quit()  # or self.root.destroy()
        else:
            #xreport('SolarMonitorApp', '', 'Shutdown not detected', blue=True)
            self.root.after(2000, self.check_shutdown)  # check again in 1 second

    def enqueue_data_received(self, device_name, data):
        self.ui_update_queue.put((device_name, data))

    def process_ui_updates(self):
        try:
            if self.incoming_queue is not None:
                while True:
                    device_name, data = self.incoming_queue.get_nowait()
                    if '__ui_event__' in data:
                        event_value = data['__ui_event__'][1] if isinstance(data['__ui_event__'], tuple) and len(data['__ui_event__']) > 1 else data['__ui_event__']
                        if event_value == 'device_ready':
                            self.on_data_received(device_name, data)
                            continue
                    self.pending_ui_updates[device_name] = data
            while True:
                device_name, data = self.ui_update_queue.get_nowait()
                if '__ui_event__' in data:
                    event_value = data['__ui_event__'][1] if isinstance(data['__ui_event__'], tuple) and len(data['__ui_event__']) > 1 else data['__ui_event__']
                    if event_value == 'device_ready':
                        self.on_data_received(device_name, data)
                        continue
                self.pending_ui_updates[device_name] = data
        except queue.Empty:
            pass
        finally:
            processed = 0
            for device_name in list(self.pending_ui_updates.keys()):
                data = self.pending_ui_updates.pop(device_name)
                self.on_data_received(device_name, data)
                processed += 1
                # Keep the Tk main loop responsive while data is streaming.
                if processed >= 1:
                    break
            self.root.after(150, self.process_ui_updates)

    def x_expandlist(self, ranges=None):
        return [i for r in ranges for i in (range(r[0], r[1] + 1) if len(r) == 2 else [r[0]])]

    def expandlist(self, ranges=None):
        result = []
        for item in ranges:
            if item is None or item == ():
                result.append(None)
            elif isinstance(item, int):
                result.append(item)
            elif isinstance(item, tuple):
                if len(item) == 2:
                    result.extend(range(item[0], item[1] + 1))
                elif len(item) == 1:
                    result.append(item[0])
                else:
                    result.append(None)
            else:
                result.append(None)
        return result


    def settings_callback(self, addr, description, value):
        logging.info(f"Settings callback: addr={addr}, description={description} value={value}")
        #xreport('SolarMonitorApp', 'settings_callback', f"addr={addr}, description={description}, value={value}", grey=True)
        # XXX
        #if self.setRegQueue:
        #    self.setRegQueue.put((addr, description, value))

    def xpopulate_tab_grid(self, addrRange=None, tab=None, msg=None):
        # Container inside the tab
        logging.info(f"populate_tab_grid: {msg} {addrRange}")
        reglist = self.expandlist(ranges=addrRange)

        widgets = {}  # Store FrameEx widgets by key

        columns = 4
        row = 0
        col = 0

        for addr in reglist:
            if addr is not None:
                key = f"{addr:04x}"
                f = LabelEditEx(tab, description=f"{addr:04x}", addr=addr, value='n/a', editable=False, option=2, callback=self.settings_callback, )
                f.grid(row=row, column=col, padx=10, pady=5, sticky="ew")
                #f.set_text(description=f"{addr:04x}", addr=addr, value='n/a', editable=False)
                widgets[key] = f
            col += 1
            if col >= columns:
                col = 0
                row += 1
        logging.info(f"populate_tab_grid: {msg} {widgets.keys()}")
        return widgets


    def create_widgets(self):
        self.devices_frame = ttk.Frame(self.root)
        self.devices_frame.pack(fill="both", expand=True)
        self.device_notebooks = {}

    def ensure_device_notebook(self, device_name):
        if device_name in self.device_notebooks:
            if TRACE_GUI_UPDATES:
                logging.info("GUI:ensure_device_notebook existing device=%s", device_name)
            return self.device_notebooks[device_name]

        if device_name not in self.active['devices']:
            self.active['devices'][device_name] = {
                'battery_capacity': 8,
                'batteries': 1,
                'device_nickname': '',
                'battery_chemistry': 'LiFePo4',
            }

        xreport(device_name, 'device_notebook', f"Creating notebook for device: {device_name}", blue=True)
        xreport(device_name, 'device_notebook', f"device_notebooks: {self.device_notebooks.keys()}", blue=True)

        container = ttk.LabelFrame(self.devices_frame, text=device_name)
        container.pack(fill="x", expand=False, pady=6, padx=8, anchor="n")
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, padx=4, pady=4)

        close_button = None

        info_keys = ['device_nickname', 'device_name', 'model', 'load_status', 'charging_status']
        info = self.info.setdefault(device_name, {k: '' for k in info_keys})
        xreport(device_name, 'device_notebook', f"Creating tabs for device: {device_name} with info: {info}", yellow=True)

        data_history = self.init_device_history()
        if USE_SIMPLE_DEVICE_PLACEHOLDER:
            power_tab = ttk.Frame(notebook)
            notebook.add(power_tab, text="Power Flow")
            title_label = ttk.Label(
                power_tab,
                text=f"DEVICE READY\n{device_name}",
                anchor="center",
                justify="center",
            )
            title_label.pack(fill="x", expand=False, padx=24, pady=(24, 8))
            status_var = tk.StringVar(value="Waiting for device status...")
            status_label = ttk.Label(
                power_tab,
                textvariable=status_var,
                anchor="center",
                justify="center",
                wraplength=600,
            )
            status_label.pack(fill="both", expand=True, padx=24, pady=(0, 24))
            powergauge_tab = None
        else:
            powergauge_tab = PowerGaugeTab(
                root=self.root,
                device_name=device_name,
                tab_control=notebook,
                aevents=self.aevents,
                controlQueues=self.controlQueues,
                shutdownEvent=self.shutdownEvent,
                active=self.active['devices'][device_name],
                info=info,
                close_callback=lambda: self.close_device_notebook(device_name),
            )

        chargingSettings = [
                 (0xe005,0xe006),0xe00c,None,
                 0xe008,0xe00a,0xe012,None,
                 0xe009, None, None, None,
                 0xe007,0xe011,0xe013, None,
                 0xe00b,0xe00d,0xe00e, 0xe010,
        ]
        settings_tab = SettingsTab(device_name=device_name, tab_control=notebook, addrRange=chargingSettings, text="Settings", )
        values_tab = SettingsTab(
            device_name=device_name,
            tab_control=notebook,
            addrRange=[(0x0100, 0x0109), None, 0x0121],
            text="Operating Values",
            labels={0x0121: "Controller Faults"},
        )

        self.device_notebooks[device_name] = {
            'notebook': notebook,
            'powergauge_tab': powergauge_tab,
            'settings_tab': settings_tab,
            'values_tab': values_tab,
            'data_history': data_history,
            'container': container,
            'close_button': close_button,
            'static_ready': False,
            'status_var': status_var if USE_SIMPLE_DEVICE_PLACEHOLDER else None,
            'status_label': status_label if USE_SIMPLE_DEVICE_PLACEHOLDER else None,
        }
        if not USE_SIMPLE_DEVICE_PLACEHOLDER:
            self.root.after_idle(lambda dn=device_name: self._render_device_placeholder(dn))
        else:
            self.device_notebooks[device_name]['static_ready'] = True
        xreport(device_name, 'device_notebook', f"device_notebooks: {self.device_notebooks.keys()} added", blue=True)
        return self.device_notebooks[device_name]

    def update_device_status(self, device_name, data):
        devinfo = self.ensure_device_notebook(device_name)
        status_text = self._normalize_field_value(data.get('status_text'), default='Waiting for device status...')
        status_level = str(self._normalize_field_value(data.get('status_level'), default='info')).lower()

        if TRACE_GUI_UPDATES:
            logging.info(
                "GUI:update_device_status device=%s level=%s text=%s",
                device_name,
                status_level,
                status_text,
            )

        if USE_SIMPLE_DEVICE_PLACEHOLDER and devinfo.get('status_var') is not None:
            devinfo['status_var'].set(status_text)
            status_label = devinfo.get('status_label')
            if status_label is not None:
                foreground = {
                    'ok': 'dark green',
                    'error': 'dark red',
                    'warn': '#8a5a00',
                    'warning': '#8a5a00',
                    'info': '#204a87',
                }.get(status_level, 'black')
                try:
                    status_label.configure(foreground=foreground)
                except Exception:
                    pass

        info = self.info.setdefault(device_name, {})
        info['status_text'] = status_text
        info['status_level'] = status_level
        if not USE_SIMPLE_DEVICE_PLACEHOLDER and devinfo.get('powergauge_tab') is not None:
            devinfo['powergauge_tab'].update_placeholder_status()

    def _render_device_placeholder(self, device_name):
        devinfo = self.device_notebooks.get(device_name)
        if not devinfo:
            return
        data_history = devinfo['data_history']
        devinfo['powergauge_tab'].render_static_placeholder()
        devinfo['static_ready'] = True
        if TRACE_GUI_UPDATES:
            logging.info(
                "GUI:ensure_device_notebook initialized static placeholder device=%s history_keys=%s",
                device_name,
                {k: len(v) if isinstance(v, list) else None for k, v in data_history.items()},
            )


    def toggle_load(self):
        self.load = not self.load
        logging.info(f"Toggle Load: {self.load}")
        logging.info(f"Toggle Load: {self.client}")
        self.load_button.configure(style="Clicked.TButton")
        self.root.after(1000, lambda: self.load_button.configure(style="TButton"))
        self.setLoadEvent.set() 


    def make_scrollable_tab(parent, height=320):
        canvas = Canvas(parent, height=height)
        scrollbar = Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return frame

    def close_device_notebook(self, device_name):
        devinfo = self.device_notebooks.pop(device_name, None)
        if devinfo:
            if 'powergauge_tab' in devinfo and devinfo['powergauge_tab'] is not None:
                devinfo['powergauge_tab'].close()
            devinfo['notebook'].destroy()
            if 'container' in devinfo:
                if devinfo['container'] is not None:
                    devinfo['container'].destroy()
            # If you added a close button above, destroy it too (track it in devinfo or pack it as a child frame)
            # Optionally clean up other per-device data
            xreport(device_name, 'close_device_notebook', 'Notebook removed by user', yellow=True)


    #  
    # INFO:root:BLETHREAD: on_data_received: BT-TH-6A6B8730     => {
    #   'function': 'READ', 'model': 'RNG-CTRL-WND10', 'device_id': 16, 
    #   'battery_percentage': 100, 'battery_voltage': 13.2, 'battery_current': 0.0, 
    #   'battery_temperature': 32.0, 'controller_temperature': 78.8, 
    #   'load_status': 'off', 'load_voltage': 0.0, 'load_current': 0.0, 'load_power': 0, 
    #   'pv_voltage': 0.0, 'pv_current': 0.0, 'pv_power': 0, 
    #   'max_charging_power_today': 0, 'max_discharging_power_today': 0, 
    #   'charging_amp_hours_today': 0, 'discharging_amp_hours_today': 0, 
    #   'power_generation_today': 0, 'power_consumption_today': 0, 'power_generation_total': 0, 
    #   'charging_status': 'deactivated', 'battery_type': 'lithium', 
    #   '__device': 'BT-TH-6A6B8730', '__client': 'RoverClient'}
    def on_data_received(self, device_name, data):
        # Append current time
        #logging.info(f"on_data_received: {device_name}")
        #xreport(device_name, 'on_data_received', f"Received data: {data}", yellow=True)

        if '__ui_event__' in data:
            event_value = data['__ui_event__'][1] if isinstance(data['__ui_event__'], tuple) and len(data['__ui_event__']) > 1 else data['__ui_event__']
            if event_value == 'device_ready':
                if TRACE_GUI_UPDATES:
                    logging.info("GUI:on_data_received device_ready device=%s", device_name)
                self.ensure_device_notebook(device_name)
                return
            if event_value == 'device_status':
                self.update_device_status(device_name, data)
                return

        if device_name not in self.device_notebooks:
            if TRACE_GUI_UPDATES:
                logging.info("GUI:on_data_received dropping data before notebook ready device=%s keys=%s", device_name, list(data.keys()))
            return

        info_keys = ['device_nickname', 'device_name', 'model', 'load_status', 'charging_status']
        if device_name not in self.info:
            #self.info[device_name] = { 'device_nickname': '', 'device_name': '', 'model': '', 'load_status': 'off', 'charging_status': 'deactivated', }
            self.info[device_name] = { k:'' for k in info_keys }

        for key in info_keys:
            if key in data:
                #logging.info(f"on_data_received: updating info {key} {data[key][1]}")
                self.info[device_name][key] = data[key][1].strip() if isinstance(data[key][1], str) else data[key][1]
            #xreport(device_name, 'on_data_received', f"info updated: {self.info[device_name]}", yellow=True)

        devinfo = self.ensure_device_notebook(device_name)
        if not devinfo.get('static_ready'):
            if TRACE_GUI_UPDATES:
                logging.info("GUI:on_data_received dropping data until static_ready device=%s keys=%s", device_name, list(data.keys()))
            return
        data_history = devinfo['data_history']

        data_history['time'].append((None, datetime.now()))
        if 'device_nickname' in data:
            data_history['device_nickname'].append(data['device_nickname'][1])
        elif data_history['device_nickname']:
            data_history['device_nickname'].append(data_history['device_nickname'][-1])
        else:
            data_history['device_nickname'].append('')
        #logging.info(f"on_data_received: {data_history['time'][-1]}")
        #logging.info(f"on_data_received: {data_history['device_nickname'][-1]}")


        # Append each relevant value
        for key in data_history:
            if key in ('time', 'device_nickname'):
                continue
            if key in data:
                addr, value, editable = data[key]
                data_history[key].append(value)
            elif data_history[key]:
                data_history[key].append(data_history[key][-1])
            else:
                data_history[key].append(0)

        if (
            'controller_fault_codes' in data
            or 'controller_fault_warnings_121' in data
            or 'controller_fault_warnings_122' in data
        ):
            controller_fault_121 = data.get('controller_fault_warnings_121', (None, None, None))[1] if 'controller_fault_warnings_121' in data else None
            controller_fault_122 = data.get('controller_fault_warnings_122', (None, None, None))[1] if 'controller_fault_warnings_122' in data else None
            if TRACE_GUI_UPDATES:
                logging.info(f"on_data_received: controller_faults: {controller_fault_121} {controller_fault_122}")
                logging.info(
                    "FAULTTRACE gui.on_data_received device=%s packet_codes=%r packet_hi=%r packet_lo=%r hist_codes=%r hist_hi=%r hist_lo=%r",
                    device_name,
                    data.get('controller_fault_codes', (None, None, None))[1] if 'controller_fault_codes' in data else None,
                    data.get('controller_fault_warnings_121', (None, None, None))[1] if 'controller_fault_warnings_121' in data else None,
                    data.get('controller_fault_warnings_122', (None, None, None))[1] if 'controller_fault_warnings_122' in data else None,
                    data_history['controller_fault_codes'][-1] if data_history['controller_fault_codes'] else None,
                    data_history['controller_fault_warnings_121'][-1] if data_history['controller_fault_warnings_121'] else None,
                    data_history['controller_fault_warnings_122'][-1] if data_history['controller_fault_warnings_122'] else None,
                )

        if True:
            # Limit history to the last 100 samples
            if len(data_history['time']) > 100:
                for key in data_history:
                    data_history[key] = data_history[key][-100:]

         
        if 'battery_voltage' in data or 'controller_fault_warnings_122' in data or 'controller_fault_warnings_121' in data:
            devinfo['powergauge_tab'].update_gauges(data_history=data_history)
        if any(item[0] in devinfo['values_tab'].widgets for item in data.values() if isinstance(item, tuple) and len(item) >= 1):
            devinfo['values_tab'].update_tab_display(data=data, msg="Operating Values")
        if 'voltage_settings' in data:
            devinfo['settings_tab'].update_tab_display(data=data, msg="Settings" )


    def on_error(client, error):
        logging.error(f"on_error: {error}")



  # In a real application, you might use a more robust mechanism
  # for managing the lifecycle of background tasks

if __name__ == "__main__":
  asyncio.run(main())
