import asyncio
import configparser
import os
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import time
import traceback

from gui.labelex import LabelEditEx

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

class SettingsTab:
    def x__init__(self, device_name=None, tab_control=None, text=None, addrRange=None, controlQueue=None): 
        self.tab_control = tab_control
        self.device_name = device_name
        self.tab = None
        self.text = text
        self.addrRange = addrRange
        self.controlQueue = controlQueue

        self.tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab, text=text)
        self.widgets = {}

        self.widgets = self.populate_tab_grid(addrRange=addrRange, msg="Settings" )

    def __init__(self, device_name=None, tab_control=None, text=None, addrRange=None, controlQueue=None): 
        self.tab_control = tab_control
        self.device_name = device_name
        self.tab = None
        self.text = text
        self.addrRange = addrRange
        self.controlQueue = controlQueue

        # Create a Frame as tab for this tab_control (notebook)
        self.tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab, text=text)
        self.widgets = {}

        # --- Add Scrollable Frame inside tab ---
        self.canvas = tk.Canvas(self.tab, borderwidth=0, highlightthickness=0, height=330)
        self.scrollbar = ttk.Scrollbar(self.tab, orient="vertical", command=self.canvas.yview)
        self.inner_frame = ttk.Frame(self.canvas)
        self.inner_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # --- Add your settings widgets to self.inner_frame, NOT self.tab! ---
        self.widgets = self.populate_tab_grid(addrRange=addrRange, msg="Settings")



    def populate_tab_grid(self, addrRange=None, msg=None):
        # Container inside the tab
        #logging.info(f"populate_tab_grid: {msg} {addrRange}")
        reglist = self.expandlist(ranges=addrRange)

        widgets = {}  # Store FrameEx widgets by key

        columns = 4
        row = 0
        col = 0

        for addr in reglist:
            if addr is not None:
                key = f"{addr:04x}"
                f = LabelEditEx(self.inner_frame, description=f"{addr:04x}", addr=addr, value='n/a', editable=False, option=2, callback=self.settings_callback, )
                f.grid(row=row, column=col, padx=10, pady=5, sticky="ew")
                #f.set_text(description=f"{addr:04x}", addr=addr, value='n/a', editable=False)
                widgets[key] = f
            col += 1
            if col >= columns:
                col = 0
                row += 1
        #logging.info(f"populate_tab_grid: {msg} {widgets.keys()}")
        return widgets

    def settings_callback(self, addr, description, value):
        logging.info(f"{self.text} callback: addr={addr}, description={description} value={value}")
        if self.controlQueue:
            self.controlQueue.put((self.device_name, 'set', addr, description, value))


    def expandlist(self, ranges=None):
        result = []
        for item in ranges:
            if item is None or item == ():
                result.append(None)
            elif isinstance(item, int):
                result.append(item)
            elif isinstance(item, tuple):                                                                                                                                           
                if len(item) == 2:                                                                                                                                                                                           result.extend(range(item[0], item[1] + 1))
                elif len(item) == 1:
                    result.append(item[0])
                else:
                    result.append(None)
            else:
                result.append(None)
        return result

    def update_tab_display(self, data=None, msg=None):

        #logging.info(f"update_tab_display[{msg}] widget keys {self.widgets.keys()}")
        #logging.info(f"update_tab_display[{msg}] data keys {data.keys()}")
        #xreport(self.device_name, self.text, f"data keys: {data.keys()}", blue=True,)
        #xreport(self.device_name, self.text, f" data: {data}", blue=True, )
        #xreport(self.device_name, self.text, f"widget keys: {self.widgets.keys()}", blue=True,)

        map = { k:v[0] for k, v in data.items() if v[0] in self.widgets.keys() }

        #xreport(self.device_name, self.text, f"map: {map}", blue=True, )
        try:
            for k, v in map.items():
                #logging.info(f"update_tab_display data[{k}]: {data[k]}")
                #xreport(self.device_name, self.text, f"update_tab_display data[{k}]: {data[k]}", blue=True, )
                addr, value, editable = data[k]
                #def set_text(self, description=None, addr=None, value=None, editable=False):
                self.widgets[v].set_text(description=k, value=value, editable=editable)
                #if editable:
                #    widget.set_editable(True)
                #    widget.set_value(value)
                #else:
                #    widget.set_editable(False)
        except Exception as e:
            logging.error(f"update_tab_display[{msg}] error: {e}")
            logging.error(traceback.format_exc())
            pass
            
