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
from gui.historytab import HistoryTab
from gui.powergauge import PowerGaugeTab

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

TRACE_GUI_UPDATES = False
USE_SIMPLE_DEVICE_PLACEHOLDER = False
MAX_HISTORY_SAMPLES = 4000
PROFILE_WRITE_COOLDOWN_SECONDS = 4.0

LIFEPO4_PROFILE_NAME = "LiFePO4"
LIFEPO4_PROFILE_TARGETS = {
    'battery_type': 'lithium',
    'system_voltage': 12,
    'charging_voltage_limit': 14.5,
    'boost_charging_voltage': 14.2,
    'floating_charging_voltage': 13.8,
    'boost_charging_recovery_voltage': 13.2,
    'over_discharge_recovery_voltage': 12.5,
    'under_voltage_warning_level': 12.0,
    'over_discharge_voltage': 11.0,
    'discharge_limit_voltage': 10.8,
    'over_discharge_time_delay': 5,
    'equalizing_charging_interval': 0,
    'boost_charging_time': 120,
    'equalizing_charging_time': 0,
}
SETTING_REGISTERS = {
    'over_voltage_threshold': 0xe005,
    'charging_voltage_limit': 0xe006,
    'equalizing_charging_voltage': 0xe007,
    'boost_charging_voltage': 0xe008,
    'floating_charging_voltage': 0xe009,
    'boost_charging_recovery_voltage': 0xe00a,
    'over_discharge_recovery_voltage': 0xe00b,
    'under_voltage_warning_level': 0xe00c,
    'over_discharge_voltage': 0xe00d,
    'discharge_limit_voltage': 0xe00e,
    'over_discharge_time_delay': 0xe010,
    'equalizing_charging_interval': 0xe011,
    'boost_charging_time': 0xe012,
    'equalizing_charging_time': 0xe013,
}
SETTING_SCALES = {
    'over_voltage_threshold': 0.1,
    'charging_voltage_limit': 0.1,
    'equalizing_charging_voltage': 0.1,
    'boost_charging_voltage': 0.1,
    'floating_charging_voltage': 0.1,
    'boost_charging_recovery_voltage': 0.1,
    'over_discharge_recovery_voltage': 0.1,
    'under_voltage_warning_level': 0.1,
    'over_discharge_voltage': 0.1,
    'discharge_limit_voltage': 0.1,
    'over_discharge_time_delay': 1,
    'equalizing_charging_interval': 1,
    'boost_charging_time': 1,
    'equalizing_charging_time': 1,
}

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
        'battery_temperature': [],
        'controller_temperature': [],
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
        self.active.setdefault('controllers', {})
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

    @staticmethod
    def _merge_pending_data(existing, incoming):
        if existing is None:
            return incoming
        if not isinstance(existing, dict) or not isinstance(incoming, dict):
            return incoming
        merged = dict(existing)
        merged.update(incoming)
        return merged

    def process_ui_updates(self):
        try:
            if self.incoming_queue is not None:
                while True:
                    device_name, data = self.incoming_queue.get_nowait()
                    if '__ui_event__' in data:
                        self.on_data_received(device_name, data)
                        continue
                    self.pending_ui_updates[device_name] = self._merge_pending_data(
                        self.pending_ui_updates.get(device_name),
                        data,
                    )
            while True:
                device_name, data = self.ui_update_queue.get_nowait()
                if '__ui_event__' in data:
                    self.on_data_received(device_name, data)
                    continue
                self.pending_ui_updates[device_name] = self._merge_pending_data(
                    self.pending_ui_updates.get(device_name),
                    data,
                )
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
        self.devices_frame.grid_columnconfigure(0, weight=1)
        self.device_notebooks = {}

    def _parse_geometry(self):
        match = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", self.root.geometry())
        if not match:
            return None
        width, height, x, y = map(int, match.groups())
        return width, height, x, y

    def _relayout_device_notebooks(self):
        names = list(self.device_notebooks.keys())
        count = len(names)
        for row in range(max(count, self.devices_frame.grid_size()[1])):
            self.devices_frame.grid_rowconfigure(row, weight=0)

        for row, name in enumerate(names):
            devinfo = self.device_notebooks[name]
            container = devinfo['container']
            container.grid_forget()
            if count <= 1:
                self.devices_frame.grid_rowconfigure(row, weight=0)
                container.grid(row=row, column=0, sticky="ew", pady=6, padx=8)
            else:
                self.devices_frame.grid_rowconfigure(row, weight=1, uniform="devices")
                container.grid(row=row, column=0, sticky="nsew", pady=6, padx=8)

    def _grow_window_for_devices(self):
        # Preserve the user's chosen window size. New device notebooks should
        # fit within the existing geometry instead of growing the root window.
        return

    def _format_device_container_title(self, device_name):
        info = self.info.get(device_name, {})
        nickname = str(info.get('device_nickname') or '').strip()
        if not nickname:
            active_device = self.active.get('devices', {}).get(device_name, {})
            if active_device:
                nickname = str(active_device.get('device_nickname') or '').strip()
        controller_uid = str(info.get('controller_uid') or info.get('serial_number') or '').strip()
        if nickname:
            return nickname
        if controller_uid:
            return controller_uid
        return f"{nickname} {device_name}".strip() if nickname else device_name

    def _controller_profile_key(self, info):
        if not isinstance(info, dict):
            return ''
        model = str(info.get('model') or '').strip()
        controller_uid = str(info.get('controller_uid') or info.get('serial_number') or '').strip()
        if model and controller_uid:
            return f"{model}::{controller_uid}"
        return controller_uid

    def _apply_controller_profile(self, device_name):
        info = self.info.get(device_name, {})
        key = self._controller_profile_key(info)
        if not key:
            return
        controllers = self.active.setdefault('controllers', {})
        controller_profile = controllers.setdefault(key, {})
        controller_profile.setdefault('battery_profile', LIFEPO4_PROFILE_NAME)
        controller_profile.setdefault('renogy_defaults', {})
        controller_profile.setdefault('model', str(info.get('model') or '').strip())
        controller_profile.setdefault('controller_uid', str(info.get('controller_uid') or info.get('serial_number') or '').strip())
        nickname = str(controller_profile.get('device_nickname') or '').strip()
        if not nickname:
            return
        info['device_nickname'] = nickname
        self.active.setdefault('devices', {}).setdefault(device_name, {}).update({'device_nickname': nickname})

    def _set_device_nickname(self, device_name, nickname):
        nickname = str(nickname or '').strip()
        self.active.setdefault('devices', {}).setdefault(device_name, {})['device_nickname'] = nickname
        info = self.info.setdefault(device_name, {})
        info['device_nickname'] = nickname
        key = self._controller_profile_key(info)
        if key:
            controllers = self.active.setdefault('controllers', {})
            profile = controllers.setdefault(key, {})
            profile['device_nickname'] = nickname
            profile['model'] = str(info.get('model') or '').strip()
            profile['controller_uid'] = str(info.get('controller_uid') or info.get('serial_number') or '').strip()
            profile.setdefault('battery_profile', LIFEPO4_PROFILE_NAME)
            profile.setdefault('renogy_defaults', {})

    def _get_controller_profile(self, device_name):
        info = self.info.get(device_name, {})
        key = self._controller_profile_key(info)
        if not key:
            return None
        controllers = self.active.setdefault('controllers', {})
        profile = controllers.setdefault(key, {})
        profile.setdefault('battery_profile', LIFEPO4_PROFILE_NAME)
        profile.setdefault('renogy_defaults', {})
        profile['model'] = str(info.get('model') or '').strip()
        profile['controller_uid'] = str(info.get('controller_uid') or info.get('serial_number') or '').strip()
        return profile

    def _capture_renogy_defaults(self, device_name, data):
        profile = self._get_controller_profile(device_name)
        if not profile:
            return
        defaults = profile.setdefault('renogy_defaults', {})
        tracked_keys = {'battery_type', 'system_voltage'} | set(SETTING_REGISTERS.keys())
        changed = False
        for key in tracked_keys:
            if key not in defaults and key in data:
                value = data[key][1]
                if isinstance(value, str):
                    value = value.strip()
                defaults[key] = value
                changed = True
        if changed and device_name in self.device_notebooks:
            self.device_notebooks[device_name]['settings_tab'].set_default_values(defaults)

    def _profile_target_map(self, device_name):
        profile = self._get_controller_profile(device_name)
        if not profile:
            return None
        battery_profile = str(profile.get('battery_profile') or LIFEPO4_PROFILE_NAME).strip()
        if battery_profile == LIFEPO4_PROFILE_NAME:
            return LIFEPO4_PROFILE_TARGETS
        return None

    def _values_differ(self, expected, actual):
        if actual is None or actual == '':
            return False
        if isinstance(expected, str):
            return str(actual).strip().lower() != expected.strip().lower()
        try:
            return abs(float(actual) - float(expected)) > 0.05
        except Exception:
            return actual != expected

    def _queue_device_write(self, device_name, register, description, value):
        control_queue = self.controlQueues.get(device_name.lower()) if self.controlQueues else None
        if control_queue is None:
            return False
        if description == 'battery_type_raw':
            scaled_value = int(value)
        elif description == 'voltage_settings':
            scaled_value = int(value)
        else:
            scale = SETTING_SCALES.get(description, 1)
            try:
                scaled_value = int(round(float(value) / float(scale)))
            except Exception:
                scaled_value = value
        control_queue.put((device_name.lower(), 'set', register, description, scaled_value))
        return True

    def _maybe_apply_battery_profile(self, device_name, data):
        targets = self._profile_target_map(device_name)
        if not targets:
            return
        info = self.info.get(device_name, {})
        device_state = self.active.setdefault('devices', {}).setdefault(device_name, {})
        profile_sync = device_state.setdefault('profile_sync', {})
        now = time.time()
        last_write_at = float(profile_sync.get('last_write_at') or 0.0)
        if now - last_write_at < PROFILE_WRITE_COOLDOWN_SECONDS:
            return

        battery_type = str(info.get('battery_type') or '').strip().lower()
        if battery_type and self._values_differ(targets['battery_type'], battery_type):
            if self._queue_device_write(device_name, 0xe004, 'battery_type_raw', 4):
                profile_sync['last_write_at'] = now
                profile_sync['last_write_key'] = 'battery_type'
            return

        system_voltage = info.get('system_voltage')
        recognized_voltage = info.get('recognized_voltage')
        if system_voltage not in ('', None) and self._values_differ(targets['system_voltage'], system_voltage):
            try:
                recognized_voltage_int = int(recognized_voltage or 0) & 0x7f
                voltage_settings = ((int(targets['system_voltage']) & 0xff) << 8) | recognized_voltage_int
                if self._queue_device_write(device_name, 0xe003, 'voltage_settings', voltage_settings):
                    profile_sync['last_write_at'] = now
                    profile_sync['last_write_key'] = 'system_voltage'
            except Exception:
                pass
            return

        ordered_setting_keys = [
            'charging_voltage_limit',
            'boost_charging_voltage',
            'floating_charging_voltage',
            'boost_charging_recovery_voltage',
            'over_discharge_recovery_voltage',
            'under_voltage_warning_level',
            'over_discharge_voltage',
            'discharge_limit_voltage',
            'over_discharge_time_delay',
            'equalizing_charging_interval',
            'boost_charging_time',
            'equalizing_charging_time',
        ]
        for key in ordered_setting_keys:
            if key not in data:
                continue
            current_value = data[key][1]
            expected_value = targets.get(key)
            if expected_value is None or not self._values_differ(expected_value, current_value):
                continue
            register = SETTING_REGISTERS.get(key)
            if register is None:
                continue
            if self._queue_device_write(device_name, register, key, expected_value):
                profile_sync['last_write_at'] = now
                profile_sync['last_write_key'] = key
            return

    def _refresh_device_container_title(self, device_name):
        devinfo = self.device_notebooks.get(device_name)
        if not devinfo:
            return
        container = devinfo.get('container')
        if container is None:
            return
        try:
            container.configure(text=self._format_device_container_title(device_name))
        except Exception:
            pass

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

        container = ttk.LabelFrame(self.devices_frame, text=self._format_device_container_title(device_name))
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True, padx=4, pady=4)

        close_button = None

        info_keys = [
            'device_nickname', 'device_name', 'model',
            'software_version', 'hardware_version', 'serial_number', 'controller_uid', 'transport_name',
            'load_status', 'charging_status', 'battery_type',
            'system_voltage', 'recognized_voltage',
        ]
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
                title_callback=lambda: self._refresh_device_container_title(device_name),
                nickname_callback=lambda nickname: self._set_device_nickname(device_name, nickname),
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
        controller_profile = self._get_controller_profile(device_name)
        if controller_profile:
            settings_tab.set_default_values(controller_profile.get('renogy_defaults', {}))
        values_tab = SettingsTab(
            device_name=device_name,
            tab_control=notebook,
            addrRange=[(0x0100, 0x0109), None, 0x0121],
            text="Operating Values",
            labels={0x0121: "Controller Faults"},
        )
        history_tab = HistoryTab(device_name=device_name, tab_control=notebook, text="History")

        self.device_notebooks[device_name] = {
            'notebook': notebook,
            'powergauge_tab': powergauge_tab,
            'settings_tab': settings_tab,
            'values_tab': values_tab,
            'history_tab': history_tab,
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
        self._relayout_device_notebooks()
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
        self._refresh_device_container_title(device_name)
        if not USE_SIMPLE_DEVICE_PLACEHOLDER and devinfo.get('powergauge_tab') is not None:
            powergauge_tab = devinfo['powergauge_tab']
            if getattr(powergauge_tab, "_last_data_history", None) is not None:
                powergauge_tab.update_gauges(powergauge_tab._last_data_history)
            else:
                powergauge_tab.render_static_placeholder()

    def _render_device_placeholder(self, device_name):
        devinfo = self.device_notebooks.get(device_name)
        if not devinfo:
            return
        data_history = devinfo['data_history']
        devinfo['powergauge_tab']._last_data_history = data_history
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
            self._relayout_device_notebooks()
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

        info_keys = [
            'device_nickname', 'device_name', 'model',
            'software_version', 'hardware_version', 'serial_number', 'controller_uid', 'transport_name',
            'load_status', 'charging_status', 'battery_type',
            'system_voltage', 'recognized_voltage',
        ]
        if device_name not in self.info:
            #self.info[device_name] = { 'device_nickname': '', 'device_name': '', 'model': '', 'load_status': 'off', 'charging_status': 'deactivated', }
            self.info[device_name] = { k:'' for k in info_keys }

        for key in info_keys:
            if key in data:
                #logging.info(f"on_data_received: updating info {key} {data[key][1]}")
                self.info[device_name][key] = data[key][1].strip() if isinstance(data[key][1], str) else data[key][1]
                if key == 'battery_type':
                    logging.info(
                        "GUI:battery_type device=%s value=%r",
                        device_name,
                        self.info[device_name][key],
                    )
            #xreport(device_name, 'on_data_received', f"info updated: {self.info[device_name]}", yellow=True)
        self._apply_controller_profile(device_name)
        self._refresh_device_container_title(device_name)
        self._capture_renogy_defaults(device_name, data)
        self._maybe_apply_battery_profile(device_name, data)

        if device_name not in self.device_notebooks:
            if TRACE_GUI_UPDATES:
                logging.info("GUI:on_data_received dropping data before notebook ready device=%s keys=%s", device_name, list(data.keys()))
            return

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
            # Keep enough samples for longer history windows such as 60m/120m.
            if len(data_history['time']) > MAX_HISTORY_SAMPLES:
                for key in data_history:
                    data_history[key] = data_history[key][-MAX_HISTORY_SAMPLES:]

        # Once real telemetry is flowing, clear any transient connection or
        # transport status so it does not overdraw the live gauge text.
        info = self.info.setdefault(device_name, {})
        info['status_text'] = ''
        info['status_level'] = ''

         
        if 'battery_voltage' in data or 'controller_fault_warnings_122' in data or 'controller_fault_warnings_121' in data:
            devinfo['powergauge_tab'].update_gauges(data_history=data_history)
            devinfo['history_tab'].update_history(data_history)
        if any(item[0] in devinfo['values_tab'].widgets for item in data.values() if isinstance(item, tuple) and len(item) >= 1):
            devinfo['values_tab'].update_tab_display(data=data, msg="Operating Values")
        if any(
            isinstance(item, tuple) and len(item) >= 1 and item[0] in devinfo['settings_tab'].widgets
            for item in data.values()
        ):
            controller_profile = self._get_controller_profile(device_name)
            if controller_profile:
                devinfo['settings_tab'].set_default_values(controller_profile.get('renogy_defaults', {}))
            devinfo['settings_tab'].update_tab_display(data=data, msg="Settings" )


    def on_error(client, error):
        logging.error(f"on_error: {error}")



  # In a real application, you might use a more robust mechanism
  # for managing the lifecycle of background tasks

if __name__ == "__main__":
  asyncio.run(main())
