import asyncio
import configparser
import os
import tkinter as tk
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

    def __init__(self, root=None, client=None, aevents=None, controlQueues=None, shutdownEvent=None, active=None, ):
        self.root = root
        self.root.geometry("800x400")
        self.client = client
        self.aevents = aevents
        self.controlQueues = controlQueues
        self.shutdownEvent = shutdownEvent
        self.setLoadEvent = None
        self.active = active
        self.root.title("Solar 12Vdc UPS Monitor")
        self.load = 0

        xreport('SolarMonitorApp', 'Initializing SolarMonitorApp ', f"root: {self.root} aevents: {self.aevents} controlQueues: {self.controlQueues}", yellow=True)

        self.info = { }

        self.batterySOCSamples = deque()    

        self.settings_tabs = {}
        #self.settings_widgets = {}  # Store FrameEx widgets by key
        #self.values_widgets = {}  # Store values for each FrameEx widget
        self.create_widgets()

        self.check_shutdown()  # Start checking for shutdown events
        self.firstime = datetime.now()

    def init_device_history(self):
        history = {k: [] for k in self.data_history}
        history['device_nickname'] = ['']
        history['controller_fault_codes'] = ['OK']
        history['controller_fault_warnings_121'] = [0]
        history['controller_fault_warnings_122'] = [0]
        return history

    def check_shutdown(self):
        if self.shutdownEvent and self.shutdownEvent.is_set():
            xreport('SolarMonitorApp', '', 'Shutdown event detected, closing GUI', blue=True)
            self.root.quit()  # or self.root.destroy()
        else:
            #xreport('SolarMonitorApp', '', 'Shutdown not detected', blue=True)
            self.root.after(2000, self.check_shutdown)  # check again in 1 second

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
        # Status Panel (left)
        #self.status_frame = FrameEx( self.root, labelframe=True, text=" Status ", padding=10, outerFlag=True, grid={"row": 0, "column": 0, "sticky": "nw"},)

        self.scroll_frame = ScrollableFrame(self.root)
        self.scroll_frame.pack(fill="both", expand=True)
        self.device_notebooks = {}


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

        info_keys = ['device_nickname', 'device_name', 'model', 'load_status', 'charging_status']
        if device_name not in self.info:
            #self.info[device_name] = { 'device_nickname': '', 'device_name': '', 'model': '', 'load_status': 'off', 'charging_status': 'deactivated', }
            self.info[device_name] = { k:'' for k in info_keys }

        for key in info_keys:
            if key in data:
                #logging.info(f"on_data_received: updating info {key} {data[key][1]}")
                self.info[device_name][key] = data[key][1].strip() if isinstance(data[key][1], str) else data[key][1]
            #xreport(device_name, 'on_data_received', f"info updated: {self.info[device_name]}", yellow=True)

        if device_name not in self.device_notebooks:
            if device_name not in self.active['devices']:
                self.active['devices'][device_name] = {'battery_capacity': 8, 'batteries': 1, 'device_nickname': '', 'battery_chemistry':'LiFePo4', }

            xreport(device_name, 'on_data_received', f"Creating new notebook for device: {device_name}", blue=True)
            xreport(device_name, 'on_data_received', f"device_notebooks: {self.device_notebooks.keys()}", blue=True)

            notebook = ttk.Notebook(self.scroll_frame.scrollable_frame)
            notebook.pack(fill="both", expand=True, pady=6, padx=8, )

            close_button = None
            container = None
            if False:
                # Frame to contain the notebook and close button
                container = ttk.Frame(self.scroll_frame.scrollable_frame)
                container.pack(fill="x", pady=6, padx=8)

                # Close button
                close_btn = ttk.Button(
                    container, text="✖", width=2,
                    command=lambda dn=device_name: self.close_device_notebook(dn)
                )
                #close_btn.pack(side="right", padx=4)
                #close_btn.place(in_=notebook, relx=1.0, x=-26, y=2, anchor="ne")  # Tune x/y for best alignment
                #close_btn.place(relx=1.0, x=-26, y=2, anchor="ne")
                close_btn.place(relx=1.0, y=32, anchor="ne")


            if len(self.device_notebooks) == 1:
                self.root.update_idletasks()  # Make sure geometry info is current
                x = self.root.winfo_x()
                y = self.root.winfo_y()

                # Change size AND preserve position
                self.root.geometry(f"800x800+{x}+{y}")


            info = self.info[device_name]  # Get dict for this device info
            xreport(device_name, 'on_data_received', f"Creating tabs for device: {device_name} with info: {info}", yellow=True)
            powergauge_tab = PowerGaugeTab(root=self.root, device_name=device_name, tab_control=notebook, aevents=self.aevents, controlQueues=self.controlQueues,
                                           shutdownEvent=self.shutdownEvent, active=self.active['devices'][device_name], info=info,
                                           close_callback=lambda: self.close_device_notebook(device_name),
                                           )
            # Create settings/other tabs as needed
            chargingSettings = [
                     (0xe005,0xe006),0xe00c,None,     # safety limits
                     0xe008,0xe00a,0xe012,None,     # boost charging
                     0xe009, None, None, None,      # floating
                     0xe007,0xe011,0xe013, None,    # equalization
                     0xe00b,0xe00d,0xe00e, 0xe010,  # over discharge protection
                     #0xe021, 
            ]
            settings_tab = SettingsTab(device_name=device_name, tab_control=notebook, addrRange=chargingSettings, text="Settings", )
            values_tab = SettingsTab(
                device_name=device_name,
                tab_control=notebook,
                addrRange=[(0x0100, 0x0109), None, 0x0121],
                text="Operating Values",
                labels={0x0121: "Controller Faults"},
            )

            #notebook.add(notebook, text=f"{device_name} \u2716",)

            self.device_notebooks[device_name] = {
                'notebook': notebook,
                'powergauge_tab': powergauge_tab,
                'settings_tab': settings_tab,
                'values_tab': values_tab,
                'data_history': self.init_device_history(),
                'container': container,
                'close_button': close_button,
            }
            xreport(device_name, 'on_data_received', f"device_notebooks: {self.device_notebooks.keys()} added", blue=True)

        devinfo = self.device_notebooks[device_name]
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
