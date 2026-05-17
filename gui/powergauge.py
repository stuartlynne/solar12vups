
import sys
import os
import tkinter as tk
from tkinter import ttk
import tkinter.simpledialog as simpledialog

from datetime import datetime, timedelta
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch
from matplotlib.path import Path
import time
import traceback
from enum import Enum
import tabulate
#import csv
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from gui.powerstate import PowerState, PowerStateHelp, LiFePo4, Power, PowerStateInfo
from gui.tooltip import ToolTipManager
from lib.drawanim import DrawAnimated


import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

TRACE_POWERGAUGE = False

# Implement a power gauge, this is three vertical sliders, one each for V, A and W.
# - This is replicated for PV/PS, Battery and Load.
# - They are connected to show the flow of power.
# - Effectively three states:
#    1. PV/PS (green) is can charge the battery (green) and power the load (red)
#    2. PV/PS is off (black), Battery (red) is discharging to power the load (red)
#    3. PV/PS (green) is charging the battery only (green), load is off (black)
# 
# - lines are used to show the connections between the three states.
# - power from PV/PS is green when providing power, black if not
# - power from the battery is red when providing power, black if not
# - V/A/W are shown on the lines when in use
#
#
#            PV or PS                     Battery                    Load
#         Volts Amps  Watts           Volts Amps  Watts          Volts Amps  Watts
#        +-----+-----+-----+         +-----+-----+-----+        +-----+-----+-----+
#        |     |     |     |         |     |     |     |        |     |     |     |
#        |     |     |     |         |     |     |     |        |     |     |     |
#        |-16V-|     |     |         |-16V-|     |     |        |-16V-|     |     |
#        |     |     |     |         |     |     |     |        |     |     |     |
#        |     |     |-30W-|         |     |     |-30W-|        |     |     |-30W-|
#        |     |     |     |         |     |     |     |        |     |     |     |
#        |     |-2A--|     |         |     |-2A--|     |        |     |-2A--|     |
#        |     |     |     |         |     |     |     |        |     |     |     |
#        |     |     |     |         |     |     |     |        |     |     |     |
#        +-----+-----+-----+         +-----+-----+-----+        +-----+-----+-----+
#                v v                        ^   v                      ^   ^
#                | |                        |   |                      |   |
#                | +-14.1V/1.3A/16W---------+   +------13.1V/1.3A/16W--+   |
#                |                                                         |
#                +---------------------13.1V/1.3A/18W----------------------+
#   



#class PowerGaugeGraph:
#    def __init__(self, tab_control=None, text="PowerGauge", figure=None):

class Gaugetype(Enum):
    PVPS = 0
    Battery = 1
    Load = 2


FAULT_CODE_TABLE = [
    (0x0001, "E01", "Battery over-discharged"),
    (0x0002, "E02", "Battery over-voltage"),
    (0x0004, "E03", "battery undervoltage"),
    (0x0008, "E04", "Load short circuit"),
    (0x0010, "E05", "Load overloaded"),
    (0x0020, "E06", "Controller over-temperature"),
    (0x0040, "E07", "External temperature sensor error"),
    (0x0080, "E08", "PV input over-current"),
    (0x0100, "E09", "PV input short circuit"),
    (0x0200, "E10", "PV over-voltage"),
    (0x0400, "E11", "PV reverse polarity"),
    (0x0800, "E12", "PV working point over-voltage"),
    (0x1000, "E13", "PV reverse connection"),
    (0x2000, "E14", "Battery reverse connection"),
    (0x4000, "E15", "Circuit charge MOS short circuit"),
    (0x8000, "E16", "Fan Alarm"),
]

FAULT_CODE_TABLE_HIGH = [
    (0x0001, "E17", "Battery low temperature protection"),
    (0x0002, "E18", "Battery short circuit protection"),
]

FAULT_TOOLTIP_TABLE = tabulate.tabulate(
    [("0x0000", "", "No error detected", "Low")]
    + [(f"0x{mask:04x}", code, description, "Low") for mask, code, description in FAULT_CODE_TABLE]
    + [(f"0x{mask:04x}", code, description, "High") for mask, code, description in FAULT_CODE_TABLE_HIGH],
    headers=["BitMask", "Error Number", "Description", "Word"],
    tablefmt="grid",
)

if False:
    class PowerState(Enum):
        NoPV_NoBattery = 0
        NoPV_BatteryIdle = 1
        PV_Charging_NoLoad = 2
        PV_Charging_Load = 3
        PV_Split_Load = 4
        Unknown = 6
        #NoPV_LoadFromBattery = 3
        #PV_LoadOnly = 5

    PowerStateHelp = {
        PowerState.NoPV_NoBattery:         ("No PV",       "No Battery",         "Load off", "pvps_v == 0 and battery_v < cutoff"),
        PowerState.NoPV_BatteryIdle:       ("No PV",       "Battery idle",       "Load off", "pvps_v == 0 and load_a == 0"),
        PowerState.PV_Charging_NoLoad:     ("PV/PS on",    "Charging",           "Load off", "pvps_v != 0 and load_a == 0"),
        #PowerState.NoPV_LoadFromBattery:   ("No PV",       "Battery discharging","Load on",  "pvps_v == 0 and load_a > 0"),
        PowerState.PV_Charging_Load:       ("PV/PS on",    "Charging",           "Load on",  "pvps_a >= load_a"),
        PowerState.PV_Split_Load:          ("PV/PS on",    "Battery discharging","Load on",  "pvps_a < load_a"),
        #PowerState.PV_LoadOnly:            ("PV/PS on",    "Battery idle",       "Load on",  "abs(pvps_a - load_a) < epsilon"),
        PowerState.Unknown:                ("Unknown",     "Unknown",            "Unknown",  "Unhandled combination"),
    }



class PowerGaugeTab:
    def __init__(self, root=None, device_name=None, tab_control=None, text="Power Flow", figure=None, aevents=None, 
                 controlQueues=None, shutdownEvent=None, setLoadEvent=None, active=None, info=None, 
                 title_callback=None, close_callback=None):
        self.root = root
        xreport(device_name, 'PowerGaugeTab', f"Initializing PowerGaugeTab {text} root: {self.root}", green=True, )
        self.tab_control = tab_control
        self.device_name = device_name
        self.close_callback = close_callback
        self.title_callback = title_callback
        self.text = text
        self.aevents = aevents
        #self.setLoadEvent = setLoadEvent
        self.controlQueues = controlQueues
        self.shutdownEvent = shutdownEvent
        self.active = active
        self.info = info
        self.powerState = PowerState.noPV_noBattery
        self.figure = figure or Figure(figsize=(7, 1.5))
        self.tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab, text=text)
        self.lastTime = time.time()
        self.lastTimeText = None
        self.client_task_event = f"{device_name.strip()}_client_task_event"
        self._clear_timer = None
        self._clear_highlight_after_id = None
        self._watchdog_after_id = None
        self._resize_after_id = None
        self._closed = False
        self._static_dirty = True
        self._static_artists = []
        self._dynamic_artists = []
        self._last_data_history = None
        self._draw_scheduled = False
        self._draw_after_id = None
        self._use_animated_render = False
        self._render_artists_animated = False
        self._placeholder_active = False
        self._placeholder_start_time = None
        self._placeholder_after_id = None
        self._placeholder_text_artist = None
        self._placeholder_info_artist = None
        self._placeholder_capacity_artist = None
        self._placeholder_time_artist = None
        self._placeholder_draw_inflight = False
        self._placeholder_static_ready = False
        self._ui_static_signature = None
        self._info_line_artist = None
        self._state_line_artist = None
        #self.ax = self.figure.add_subplot(111)



        self.ax = self.figure.add_axes([0.05, 0.04, 0.95, 0.94], frameon=False) # left, bottom, width, height
        self.ax.axis('off')
        self.figure.subplots_adjust(left=0.05, right=0.99, top=0.95, bottom=0.05)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.tab)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.draw()

        self.tooltip = ToolTipManager(self.root, self.canvas.get_tk_widget(), self.canvas, self.ax)
        self.power = Power(name=device_name, )
        self.drawanim = DrawAnimated(self.figure, name=device_name or text)
        self.drawanim.open(xaxis_dynamic=False, yaxis_dynamic=False, extra_static_artists=self._static_artists, debug=False, name=device_name or text)

        self.load_button_bounds = self.close_button_bounds = None
        self.name_button_bounds = self.capacity_button_list = None
        self.load_button_clicked = False
        self.figure.canvas.mpl_connect('button_press_event', self.on_click)
        self.figure.canvas.mpl_connect('resize_event', lambda event: self._queue_resize_refresh())

        self.nickname = None
        self.csvtitles = [ 'timestamp', 'powerState', 'pvps_v', 'pvps_a', 'pvps_w', 'batt_v', 'batt_a', 'batt_w', 'load_v', 'load_a', 'load_w', ]

        self.csvfile = None
        self.csvwriter = None
        self.csvfilename = None
        self.last_csv_day = None

        #self.battery_capacity = 
        #self.battery_chemistry = 

        self._start_watchdog()

        def sanity_tooltip_test():
            test = tk.Label(self.root, text="SANITY TEST", bg="red", fg="white")
            test.place(x=200, y=200)
            test.tkraise()
            logging.info("Sanity tooltip placed")

        #self.root.after(1000, sanity_tooltip_test)

    def get_fault_display(self, data_history):
        if data_history.get('controller_fault_codes'):
            fault_display = data_history['controller_fault_codes'][-1]
            if TRACE_POWERGAUGE:
                logging.info(
                    "FAULTTRACE powergauge.get_fault_display device=%s hist_codes=%r hist_hi=%r hist_lo=%r display=%r",
                    self.device_name,
                    fault_display,
                    data_history['controller_fault_warnings_121'][-1] if data_history.get('controller_fault_warnings_121') else None,
                    data_history['controller_fault_warnings_122'][-1] if data_history.get('controller_fault_warnings_122') else None,
                    fault_display,
                )
            return fault_display
        if TRACE_POWERGAUGE:
            logging.info("FAULTTRACE powergauge.get_fault_display device=%s hist_codes=None display='OK'", self.device_name)
        return "OK"

    def _start_watchdog(self):
        def check():
            if self._closed:
                return
            self._watchdog_tick()
            if self.shutdownEvent.is_set():
                xreport(self.device_name, 'WatchDog', 'Shutdown is set', grey=True, )
                return
            self._watchdog_after_id = self.canvas.get_tk_widget().after(1000, check)  # run every 1s
        check()

    def _safe_draw_idle(self):
        if self._closed:
            return
        try:
            widget = self.canvas.get_tk_widget()
            if not widget.winfo_exists():
                return
            if self.figure is None or self.figure.canvas is None:
                return
            self.root.after_idle(self.figure.canvas.draw_idle)
        except Exception as e:
            logging.debug("PowerGauge:_safe_draw_idle skipped: %s", e)

    def _invalidate_static(self):
        self._static_dirty = True
        self._static_artists.clear()
        self._ui_static_signature = None
        try:
            self.drawanim.reset('invalidate-static')
        except Exception:
            pass

    def _current_display_name(self):
        name = self.active.get('device_nickname', '')
        if name == '':
            if 'device_nickname' in self.info:
                name = self.info['device_nickname']
            else:
                name = self.device_name
        return name

    def _current_ui_static_signature(self):
        return (
            self._current_display_name(),
            bool(self.load_button_clicked),
        )

    def _track_dynamic_artist(self, artist):
        try:
            artist.set_animated(self._render_artists_animated)
        except Exception:
            pass
        self._dynamic_artists.append(artist)
        return artist

    def _track_static_artist(self, artist):
        try:
            artist.set_animated(self._render_artists_animated)
        except Exception:
            pass
        self._static_artists.append(artist)
        return artist

    def _replace_dynamic_text_artist(self, attr_name, x, y, text, **kwargs):
        old_artist = getattr(self, attr_name, None)
        if old_artist is not None:
            try:
                old_artist.remove()
            except Exception:
                pass
            try:
                self._dynamic_artists.remove(old_artist)
            except ValueError:
                pass
        artist = self._track_dynamic_artist(self.ax.text(x, y, text, **kwargs))
        setattr(self, attr_name, artist)
        return artist

    def _clear_dynamic_artists(self):
        for artist in self._dynamic_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self._dynamic_artists.clear()
        self._info_line_artist = None
        self._state_line_artist = None

    def _schedule_draw(self):
        if self._closed or self._draw_scheduled or not self._use_animated_render:
            return
        if TRACE_POWERGAUGE:
            logging.info("PowerGauge:_schedule_draw device=%s state=%s static=%d dynamic=%d",
                         self.device_name, self.drawanim.draw_state.name, len(self._static_artists), len(self._dynamic_artists))
        self._draw_scheduled = True
        self._draw_after_id = self.root.after(1, self._run_draw_stage)

    def _cancel_pending_draw(self):
        self._draw_scheduled = False
        if self._draw_after_id:
            try:
                self.root.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None

    def _drain_draw(self, max_steps=512):
        if self._closed:
            return
        if TRACE_POWERGAUGE:
            logging.info("PowerGauge:_drain_draw device=%s begin state=%s static=%d dynamic=%d",
                         self.device_name, self.drawanim.draw_state.name, len(self._static_artists), len(self._dynamic_artists))
        self._draw_scheduled = False
        if self._draw_after_id:
            try:
                self.root.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None
        try:
            for _ in range(max_steps):
                done = self.drawanim.draw_loop(pause_time=0.05, flush_events=False)
                if TRACE_POWERGAUGE:
                    logging.info("PowerGauge:_drain_draw device=%s step state=%s done=%s static=%d dynamic=%d",
                                 self.device_name, self.drawanim.draw_state.name, done, len(self._static_artists), len(self._dynamic_artists))
                if done:
                    break
            try:
                self.canvas.flush_events()
            except Exception:
                pass
            if TRACE_POWERGAUGE:
                logging.info("PowerGauge:_drain_draw device=%s end state=%s", self.device_name, self.drawanim.draw_state.name)
        except Exception as e:
            logging.debug("PowerGauge:_drain_draw falling back to canvas.draw: %s", e)
            self.canvas.draw()

    def _run_draw_stage(self):
        self._draw_after_id = None
        if self._closed:
            self._draw_scheduled = False
            return
        try:
            done = self.drawanim.draw_loop(pause_time=0.008, flush_events=False)
            if TRACE_POWERGAUGE:
                logging.info("PowerGauge:_run_draw_stage device=%s state=%s done=%s static=%d dynamic=%d",
                             self.device_name, self.drawanim.draw_state.name, done, len(self._static_artists), len(self._dynamic_artists))
        except Exception as e:
            self._draw_scheduled = False
            logging.debug("PowerGauge:_run_draw_stage falling back to canvas.draw: %s", e)
            self.canvas.draw()
            return
        if done:
            self._draw_scheduled = False
            return
        self._draw_after_id = self.root.after(1, self._run_draw_stage)

    def _queue_resize_refresh(self):
        if self._closed:
            return
        self._invalidate_static()
        self._cancel_pending_draw()
        if self._resize_after_id:
            try:
                self.root.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.root.after(80, self._on_resize_refresh)

    def _on_resize_refresh(self):
        self._resize_after_id = None
        if self._closed:
            return
        if self._last_data_history is not None:
            self.update_gauges(self._last_data_history)
            return
        self.render_static_placeholder()

    def _render_static_scene(self, animated=False):
        if TRACE_POWERGAUGE:
            logging.info("PowerGauge:_render_static_scene device=%s begin animated=%s", self.device_name, animated)
        self._render_artists_animated = animated
        self.ax.clear()
        self.ax.axis('off')
        self.ax.set_xlim(0, 6)
        self.ax.set_ylim(0, 2.2)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)
        self._static_artists.clear()

        block0_x = 0.5
        block1_x = 2.5
        block2_x = 4.5
        zero_y = 0.55

        self.tooltip.clear_tips()

        self.name_button_bounds = [-0.14, 1.98,1.70,.19]
        self.tooltip.add_tip_box(self.name_button_bounds, "Click to change BT-1 BLE Charge Controller nickname")

        self.load_button_bounds = [5.00, 2.098,.70,.09]
        self.tooltip.add_tip_box(self.load_button_bounds, "Turn load on and off")

        self.close_button_bounds = [5.84,2.098,.10,.10]
        self.tooltip.add_tip_box(self.close_button_bounds, "Close this tab")

        self.capacity_button_list = {
                'capacity_down':  { 'arrow': '\u25BC', 'bounds': [5.20, 0.022, .08, .08], 'active': 'battery_capacity', 'up': False, },
                'capacity_up':    { 'arrow': '\u25B2', 'bounds': [5.40, 0.022, .08, .08], 'active': 'battery_capacity', 'up': True, },
                'batteries_up':   { 'arrow': '\u25B2', 'bounds': [5.60, 0.022, .08, .08], 'active': 'batteries', 'up': True, },
                'batteries_down': { 'arrow': '\u25BC', 'bounds': [5.80, 0.022, .08, .08], 'active': 'batteries', 'up': False, },
                    }

        for button in self.capacity_button_list.values():
            self.tooltip.add_tip_box(button['bounds'], f"Click to change {button['active']} {'up' if button['up'] else 'down'}")

        self._track_static_artist(self.ax.text(
            -0.15, 2.0, f"{self._current_display_name()}",
            ha='left', va='bottom', backgroundcolor='lightgrey', fontsize=14, weight='bold'
        ))

        x, y, w, h = self.load_button_bounds
        self.ax.add_patch(self._track_static_artist(FancyBboxPatch(
            (x, y), w, h*.8,
            boxstyle="round,pad=0.02, rounding_size=0.020",
            facecolor='lightskyblue' if self.load_button_clicked else 'lightgray',
            edgecolor='black', alpha=0.8
        )))
        self._track_static_artist(self.ax.text(x + w / 2, y + h*.5, "Toggle Load", ha='center', va='center', fontsize=7, weight='bold'))

        x, y, w, h = self.close_button_bounds
        self.ax.add_patch(self._track_static_artist(FancyBboxPatch(
            (x, y), w, h*.8, boxstyle="round,pad=0.02, rounding_size=0.020",
            facecolor='white', edgecolor='black', alpha=0.8
        )))
        self._track_static_artist(self.ax.text(x + w / 2, y, "\u2716", ha='center', va='bottom', fontsize=6, weight='bold'))

        for button in self.capacity_button_list.values():
            x, y, w, h = button['bounds']
            self.ax.add_patch(self._track_static_artist(FancyBboxPatch(
                (x, y), w, h*.8,
                boxstyle="round,pad=0.02, rounding_size=0.020",
                facecolor='lightgray', edgecolor='black', alpha=0.8
            )))
            self._track_static_artist(self.ax.text(x + w / 2, y + h*.5, button['arrow'], ha='center', va='center', fontsize=6, weight='bold'))

        self.draw_block_static(block0_x, zero_y, gaugeType=Gaugetype.PVPS)
        self.draw_block_static(block1_x, zero_y, gaugeType=Gaugetype.Battery)
        self.draw_block_static(block2_x, zero_y, gaugeType=Gaugetype.Load)
        self._static_dirty = False
        self._ui_static_signature = self._current_ui_static_signature()
        if TRACE_POWERGAUGE:
            logging.info("PowerGauge:_render_static_scene device=%s end static=%d",
                         self.device_name, len(self._static_artists))

    def _placeholder_status_parts(self):
        status_text = ""
        status_level = "info"
        if isinstance(self.info, dict):
            status_text = str(self.info.get('status_text') or "")
            status_level = str(self.info.get('status_level') or "info").lower()
        status_color = {
            'ok': 'darkgreen',
            'error': 'darkred',
            'warn': '#8a5a00',
            'warning': '#8a5a00',
            'info': '#204a87',
        }.get(status_level, 'black')
        return status_text, status_level, status_color

    def _placeholder_info_text(self):
        if not isinstance(self.info, dict):
            return ""
        info_values = [
            str(v) for k, v in self.info.items()
            if v and k not in ('device_nickname', 'status_text', 'status_level') and v != 'N/A'
        ]
        return ", ".join(info_values)

    def _add_placeholder_banner(self, elapsed=None, animated=False, include_status=True):
        track = self._track_dynamic_artist if animated else self._track_static_artist
        status_text, _, status_color = self._placeholder_status_parts()
        if include_status and status_text:
            status_artist = track(self.ax.text(
                3.0, 0.10,
                status_text,
                ha='center',
                va='bottom',
                fontsize=11,
                color=status_color,
                wrap=True,
                bbox=dict(facecolor='white', edgecolor=status_color, boxstyle='round,pad=0.35'),
            ))
            self.tooltip.add_tip_artist(status_artist, "Remote bridge / controller status")
        if elapsed is not None:
            dynamic = (self._track_dynamic_artist if animated else self._track_static_artist)(self.ax.text(
                3.0, 0.65,
                f"DYNAMIC PLACEHOLDER {elapsed:0.1f}s",
                ha='center',
                va='center',
                fontsize=13,
                weight='bold',
                color='darkred',
                bbox=dict(facecolor='white', edgecolor='darkred', boxstyle='round,pad=0.3'),
            ))
            self.tooltip.add_tip_artist(dynamic, "Dynamic placeholder timer")
            self._placeholder_text_artist = dynamic

    def update_placeholder_status(self):
        if self._closed:
            return
        if not self._placeholder_static_ready:
            self.render_static_placeholder()
            return

        status_text, _, status_color = self._placeholder_status_parts()
        self._render_artists_animated = True

        for artist_name in (
            '_placeholder_capacity_artist',
            '_placeholder_time_artist',
        ):
            artist = getattr(self, artist_name)
            if artist is not None:
                try:
                    artist.remove()
                except Exception:
                    pass
                try:
                    self._dynamic_artists.remove(artist)
                except ValueError:
                    pass
                setattr(self, artist_name, None)

        info_text = self._placeholder_info_text()
        battery_capacity = self.active.get('battery_capacity', 8)
        batteries = self.active.get('batteries', 1)
        battery_button_str = f"{battery_capacity}Ah x{batteries}"

        if not status_text and not info_text:
            self._replace_dynamic_text_artist(
                '_info_line_artist',
                -0.15, 0.092,
                "",
                ha='left', va='bottom', fontsize=10, weight='bold', color='black'
            )
            self._replace_dynamic_text_artist(
                '_state_line_artist',
                -0.15, -0.05,
                "",
                ha='left', va='bottom', fontsize=10, weight='bold', color='black'
            )
            self.drawanim.reset('placeholder-status-clear')
            self._drain_draw(max_steps=64)
            return

        if info_text:
            self._replace_dynamic_text_artist(
                '_info_line_artist',
                -0.15, 0.092,
                info_text,
                ha='left',
                va='bottom',
                fontsize=10,
                weight='bold',
                color='black',
            )
        else:
            self._replace_dynamic_text_artist(
                '_info_line_artist',
                -0.15, 0.092,
                "",
                ha='left', va='bottom', fontsize=10, weight='bold', color='black'
            )

        if status_text:
            self._replace_dynamic_text_artist(
                '_state_line_artist',
                -0.15, -0.05,
                status_text,
                ha='left',
                va='bottom',
                fontsize=10,
                weight='bold',
                color=status_color,
            )
        else:
            self._replace_dynamic_text_artist(
                '_state_line_artist',
                -0.15, -0.05,
                "",
                ha='left', va='bottom', fontsize=10, weight='bold', color='black'
            )

        capacity_artist = self._track_dynamic_artist(
            self.ax.text(5.50, 0.128, battery_button_str, ha='center', va='bottom', fontsize=10, weight='bold')
        )
        self._placeholder_capacity_artist = capacity_artist

        timestamp_text = time.strftime("%H:%M:%S")
        time_artist = self._track_dynamic_artist(self.ax.text(
            3.70, 2.04,
            f"{timestamp_text}",
            ha='right',
            va='bottom',
            fontsize=10,
            weight='bold',
            color='#444444',
        ))
        self._placeholder_time_artist = time_artist
        self.drawanim.reset('placeholder-status-update')
        self._drain_draw(max_steps=128)

    def render_static_placeholder(self):
        if self._closed:
            return
        if TRACE_POWERGAUGE:
            logging.info("PowerGauge:render_static_placeholder device=%s", self.device_name)
        self._placeholder_active = False
        self._placeholder_start_time = None
        self._placeholder_text_artist = None
        self._placeholder_info_artist = None
        self._placeholder_capacity_artist = None
        self._placeholder_time_artist = None
        self._placeholder_static_ready = False
        self._use_animated_render = False
        self._render_artists_animated = False
        self._clear_dynamic_artists()
        self.tooltip.clear_tips()
        self._static_dirty = True
        self._render_static_scene(animated=False)
        self.canvas.draw()
        self._placeholder_static_ready = True
        try:
            self.canvas.get_tk_widget().update_idletasks()
        except Exception:
            pass

    def close(self):
        self._closed = True
        self.drawanim.close()
        try:
            self.tooltip._hide_tooltip()
        except Exception:
            pass
        if self._watchdog_after_id:
            try:
                self.canvas.get_tk_widget().after_cancel(self._watchdog_after_id)
            except Exception:
                pass
            self._watchdog_after_id = None
        if self._resize_after_id:
            try:
                self.root.after_cancel(self._resize_after_id)
            except Exception:
                pass
            self._resize_after_id = None
        if self._clear_highlight_after_id:
            try:
                self.root.after_cancel(self._clear_highlight_after_id)
            except Exception:
                pass
            self._clear_highlight_after_id = None
        if self._draw_after_id:
            try:
                self.root.after_cancel(self._draw_after_id)
            except Exception:
                pass
            self._draw_after_id = None
        if self._placeholder_after_id:
            try:
                self.root.after_cancel(self._placeholder_after_id)
            except Exception:
                pass
            self._placeholder_after_id = None

    def _watchdog_tick(self):
        if self._closed:
            return
        elapsed = time.time() - self.lastTime
        if not self.lastTimeText:
            return
        if elapsed < 5:
            #logging.info("PowerGauge:_watchdog_tick: lastTimeText not updated")
            return
        if elapsed > 30:
            color = 'red'
        elif elapsed > 15:
            color = 'orangered'
        elif elapsed > 6:
            color = 'orange'    # alternate oranagered
        else:
            color = 'green'

        if self.lastTimeText:
            self.lastTimeText.set_color(color)
            if self._use_animated_render:
                self._schedule_draw()
            else:
                try:
                    self.canvas.draw_idle()
                except Exception:
                    self.canvas.draw()

    def popup_and_get_string(self, prompt="Please enter something"):
        return simpledialog.askstring("Prompt", prompt, parent=self.root)


    def on_click(self, event):
        logging.info("PowerGauge:on_click: event=%s", event)
        
        try:
            if not hasattr(self, 'load_button_bounds'):
                return
            
            if event.xdata is None or event.ydata is None:
                return  # Click outside axes

            if self.name_button_bounds:
                x, y, w, h = self.name_button_bounds
                if x <= event.xdata <= x + w and y <= event.ydata <= y + h:
                    xreport(self.device_name, 'PowerGauge', 'Name button clicked', green=True, )
                    nickname = self.active.get('device_nickname', '')
                    new_nickname = self.popup_and_get_string(f"Enter nickname for {nickname} (current: {nickname})")
                    if new_nickname is None:
                        return
                    self.active['device_nickname'] = new_nickname
                    xreport(self.device_name, 'PowerGauge', f"Nickname set to {self.active['device_nickname']}", green=True, )
                    if self.title_callback is not None:
                        try:
                            self.title_callback()
                        except Exception:
                            pass
                    if self._last_data_history is not None:
                        self.update_gauges(self._last_data_history)
                    else:
                        self._invalidate_static()
                        self.render_static_placeholder()
                        try:
                            self.canvas.draw()
                            self.canvas.get_tk_widget().update_idletasks()
                        except Exception:
                            pass
            
            if self.load_button_bounds:
                x, y, w, h = self.load_button_bounds
                
                if x <= event.xdata <= x + w and y <= event.ydata <= y + h:
                    logging.info("PowerGauge:on_click: Load button clicked load_status")
                    logging.info(f"PowerGauge:on_click: controlQueues: {self.controlQueues} device_name: {self.device_name.lower()}")
                    #self.setLoadEvent.set()
                    if self.controlQueues and self.device_name.lower() in self.controlQueues:
                        logging.info(f"PowerGauge:on_click: queing toggle_load for {self.device_name}")
                        self.controlQueues[self.device_name.lower()].put((self.device_name.lower(), 'toggle_load',))
                    self.aevents.set(self.client_task_event, None, 'load_button_clicked')
                    self.load_button_clicked = True
                    if TRACE_POWERGAUGE:
                        logging.info("PowerGauge:clear_highlight: Setting load_button_clicked highlight")
                    # reset after 3800ms
                    self.update_gauges()
                    if not self._clear_highlight_after_id:
                        self._clear_highlight_after_id = self.root.after(3800, self.clear_highlight)
                else:
                    logging.info("PowerGauge:on_click: Click outside load button")

            if self.close_button_bounds:
                x, y, w, h = self.close_button_bounds
                if event.xdata is not None and event.ydata is not None:
                    if x <= event.xdata <= x + w and y <= event.ydata <= y + h:
                        xreport(self.device_name, 'PowerGauge', 'Close button clicked', grey=True, )
                        # User clicked close button!
                        #self.tooltip.clear_tips()
                        self.tooltip._hide_tooltip()
                        self.close_callback()
                    else:
                        logging.info("PowerGauge:on_click: outside close button bounds, not closing tab")

            if self.capacity_button_list:
                for k, button in self.capacity_button_list.items():
                    #'capacity_down':  { 'arrow': '\u25BC', 'bounds': [5.20, 0.022, .08, .08], 'active': 'battery_capacity', up: False, },
                    xreport(self.device_name, 'PowerGauge', f"Checking capacity button", blue=True, )
                    x, y, w, h = button['bounds']
                    active = button['active']
                    up = button['up']
                    if x <= event.xdata <= x + w and y <= event.ydata <= y + h:
                        previous_value = self.active[active]
                        self.active[active] += 1 if up else (-1 if previous_value > 1 else 0)
                        xreport(self.device_name, 'on_click', f"Capacity button clicked: {active} {previous_value} -> {self.active[active]}", blue=True, )
                        if self._last_data_history is not None:
                            self.update_gauges(self._last_data_history)
                        else:
                            self.render_static_placeholder()
                        break
        except Exception as e:
            logging.exception(f"PowerGauge:on_click: Error processing click event: {e}")

    def clear_highlight(self):
        if self._closed:
            self._clear_highlight_after_id = None
            return
        if TRACE_POWERGAUGE:
            logging.info("PowerGauge:clear_highlight: Resetting load_button_clicked highlight")
        self.load_button_clicked = False
        self.update_gauges()
        if self._clear_highlight_after_id:
            self._clear_highlight_after_id = None

    def getPowerState(self, data_history):
        #logging.info(f"PowerGauge:getPowerState: {data_history}")
        #load_status = data_history['load_status'][-1]


        try:
            pvps_v = self.get_val('pv_voltage', data_history)
            pvps_a = self.get_val('pv_current', data_history)
            load_v = self.get_val('load_voltage', data_history)
            load_a = self.get_val('load_current', data_history)
            batt_v = self.get_val('battery_voltage', data_history)

            return self.power.getPowerState(pvps_v=pvps_v, pvps_a=pvps_a,
                           load_v=load_v, load_a=load_a,
                           batt_v=batt_v, )
        except Exception as e:
            logging.exception(f"PowerGauge:getPowerState: Error getting power state: {e}")
            print(traceback.format_exc(), file=sys.stderr)
            return PowerState.UNKNOWN

    def get_val(self, key, data_history):
        try:
            return data_history[key][-1]
        except Exception:
                return 0

    def get_vcw(self, key, data_history):
        vcw = [data_history[f"{key}_{field}"][-1] for field in ("voltage", "current", )]
        vcw.append(vcw[0] * vcw[1])
        return vcw

    def get_vcwn(self, key, data_history, n):
        #logging.info(f"PowerGauge:get_vcwn: {key} {data_history}")
        def avg(lst):
            return sum(lst[-n:]) / len(lst[-n:]) if lst else 0

        v = avg(data_history.get(f"{key}_voltage", []))
        c = avg(data_history.get(f"{key}_current", []))
        w = v * c

        return [v, c, w]

    def draw_block_static(self, x0, base_y, gaugeType=None):
        width = 0.25
        height = 1.3

        voltage_tick_step = 2 if gaugeType == Gaugetype.PVPS else 1
        match gaugeType:
            case Gaugetype.PVPS:
                min_v, max_v = (11.0, 32.0)
                label = "PV/PS"
            case Gaugetype.Battery:
                min_v, max_v = (11.0, 17.0)
                label = "Battery"
            case Gaugetype.Load:
                min_v, max_v = (11.0, 17.0)
                label = "Load"

        block_patch = self._track_static_artist(patches.Rectangle((x0 - 0.3, base_y), 1.1, height, fill=False, edgecolor='black'))
        self.ax.add_patch(block_patch)
        self._track_static_artist(self.ax.text(x0 + 0.25, base_y + height + 0.02, label, ha='center', va='bottom', fontsize=9, weight='bold'))

        for i in range(int(min_v), int(max_v) + 1, voltage_tick_step):
            pos = base_y + ((i - min_v) / (max_v - min_v)) * height
            match gaugeType:
                case Gaugetype.PVPS | Gaugetype.Battery:
                    self._track_static_artist(self.ax.hlines(pos, x0 - 0.35, x0 - 0.32, colors='gray', linewidth=1))
                    self._track_static_artist(self.ax.text(x0 - 0.37, pos, f'{i}V', ha='right', va='center', fontsize=7))
                case Gaugetype.Load:
                    x_off = 1.2
                    self._track_static_artist(self.ax.hlines(pos, x0 - 0.39+x_off, x0 - 0.35+x_off, colors='gray', linewidth=1))
                    self._track_static_artist(self.ax.text(x0 - 0.36+x_off, pos, f'{i}V', ha='left', va='center', fontsize=7))

        if gaugeType == Gaugetype.Battery:
            for label_text, volt in LiFePo4.DischargeTable.items():
                pos = base_y + ((volt - min_v) / (max_v - min_v)) * height
                marker = self._track_static_artist(self.ax.hlines(pos, x0 + 0.5 + 0.35, x0 + 0.5 + 0.32, colors='gray', linewidth=1))
                text = self._track_static_artist(self.ax.text(x0 + 0.5 + 0.37, pos, label_text, ha='left', va='center', fontsize=7))
                self.tooltip.add_tip_artist(marker, 'Discharge level', name=f"battery-discharge-marker-{label_text}")
                self.tooltip.add_tip_artist(text, 'Discharge level', name=f"battery-discharge-text-{label_text}")

    # XXX
    # Sample data_history: PowerGauge:update_gauges: 
    #   {'time': [(None, datetime.datetime(2025, 5, 17, 8, 20, 30, 118788)), (None, datetime.datetime(2025,   5, 17, 8, 20, 32, 482157))], 
    # 'battery_voltage': [14.4, 0], 
    # 'load_voltage': [14.4, 0], 'pv_voltage': [15.0, 0], 'battery_current': [3.04, 0],   
    # 'load_current': [2.53, 0], 'pv_current': [2.86, 0], 'load_power': [36.431999999999995, 0], 'pv_power': [42.9, 0], 
    # 'battery_percentage': [100,   0], 'load_status': [0, 'on']}

    def draw_block(self, x0, base_y, label, v=None, colors=None, gaugeType=None, tooltip=None):
        width = 0.25
        height = 1.3
        #base_y = 0.5

        voltage_tick_step = 2 if gaugeType == Gaugetype.PVPS else 1
        match gaugeType:
            case Gaugetype.PVPS:    
                min_v, max_v, max_w = (11.0, 32.0, 100.0)
            case Gaugetype.Battery | Gaugetype.Load:
                min_v, max_v, max_w = (11.0, 17.0, 100.0)

        #logging.info(f"PowerGauge:drawblock {label}: v:{v} power:{power}")

        power_w = 0


        def znone(v):
            return v if v is not None else 0.0

        bar1_v = bar2_w = bar3_w = 0.0
        if gaugeType == Gaugetype.Load:
            voltage = self.power.load.load_v
            power_w = self.power.load.load_w
            load_a = self.power.load.load_a
            text = self._track_dynamic_artist(self.ax.text(x0 + 0.25, base_y + height - 0.1, f"{label} {power_w:0.1f}W", ha='center', va='bottom', fontsize=8, weight='bold', 
                         color='red' if self.power.load.from_batt_w else 'green',)
                         )
            self.tooltip.add_tip_artist(text, f"Total Load power being used: {power_w:0.1f}W\nGreen if no battery power, Red if battery power used.", )
            #self.tooltip.add_tip_artist(block_patch, 'BBBB',)
            if load_a:
                percentage = LiFePo4.estPercent(self.power.batt.batt_v,)

                battery_capacity = self.active.get('battery_capacity', 8)
                batteries = self.active.get('batteries', 1)
                runtime= LiFePo4.estRuntime(percentage, battery_capacity=battery_capacity, batteries=batteries, load_a=load_a,)
                text = self._track_dynamic_artist(self.ax.text(x0 + 0.25, base_y + height - 0.18, f"{runtime:.1f} hours", ha='center', va='bottom', fontsize=8, weight='bold'))
                self.tooltip.add_tip_artist(text, f"Estimated runtime based on {battery_capacity * batteries}Ah and {load_a}A load",)
            bar1_v = znone(self.power.load.load_v)
            bar2_w = znone(self.power.load.from_batt_w)
            bar3_w = znone(self.power.load.from_pvps_w)

        # Background shading for battery based on voltage level
        if gaugeType == Gaugetype.Battery:
            voltage = self.power.batt.batt_v
            power_w = self.power.batt.batt_w
            text = self._track_dynamic_artist(self.ax.text(x0 + 0.25, base_y + height - 0.1, f"{label} {power_w:0.1f}W", ha='center', va='bottom', fontsize=8, weight='bold',
                         color='red' if self.power.batt.to_load_w else 'green',
                         ))
            self.tooltip.add_tip_artist(text, f"Total Battery power: {power_w:0.1f}W\nGreen if charging, Red if discharging.", )
            if voltage >= 13.3:
                bg_color = '#ccffcc'  # light green
            elif voltage >= 13.0:
                bg_color = '#cce5ff'  # light blue
            elif voltage >= 12.8:
                bg_color = '#ffffcc'  # light yellow
            elif voltage >= 12.5:
                bg_color = '#ffcccc'  # light red
            else:
                bg_color = '#cc0000'  # dark red

            voltage_height = height * min((voltage - min_v) / (max_v - min_v), 1.0)
            if voltage_height > 0:
                patch = self._track_dynamic_artist(patches.Rectangle((x0 - 0.3, base_y), 1.1, voltage_height, facecolor=bg_color, edgecolor='none', zorder=0))
                self.tooltip.add_tip_artist(patch, tooltip,)
                self.ax.add_patch(patch)

            #self.tooltip.add_tip_artist(block_patch, 'AAAA',)
            percentage = LiFePo4.estPercent(self.power.batt.batt_v,)
            #if load_a:
            #    runtime= LiFePo4.estRuntime(percentage, load_a=load_a,)
            battery_capacity = self.active.get('battery_capacity', 8)
            batteries = self.active.get('batteries', 1)

            text = self._track_dynamic_artist(self.ax.text(x0 + 0.25, base_y + height - 0.18, f"{battery_capacity *batteries}Ah {percentage:1.0f}%", 
                         ha='center', va='bottom', fontsize=8, weight='bold'))
            self.tooltip.add_tip_artist(text, 
                    f"Battery capacity: {battery_capacity * batteries}Ah based on {batteries} {battery_capacity}Ah " +
                    f"batter{'ies' if batteries > 1 else 'y'} {percentage:1.0f}% charged",)

            bar1_v = znone(self.power.batt.batt_v)
            bar2_w = znone(self.power.batt.from_pvps_w)
            bar3_w = znone(self.power.batt.to_load_w)
        
        if gaugeType == Gaugetype.PVPS:
            voltage = self.power.pvps.pvps_v
            power_w = self.power.pvps.pvps_w
            text = self._track_dynamic_artist(self.ax.text(x0 + 0.25, base_y + height - 0.1, f"{label} {power_w:0.1f}W", ha='center', va='bottom', fontsize=8, weight='bold',
                         color = 'red' if not self.power.pvps.to_batt_w else 'green' ,
                         ))
            self.tooltip.add_tip_artist(text, f"Total PVPS power being supplied: {power_w:0.1f}W", )
            bar1_v = znone(self.power.pvps.pvps_v)
            bar2_w = znone(self.power.pvps.to_load_w)
            bar3_w = znone(self.power.pvps.to_batt_w)
            #self.tooltip.add_tip_artist(block_patch, 'CCCC',)
            pass

        #self.ax.text(x0 + 0.25, base_y + height - 0.1, f"{label} {power_w:0.1f}W", ha='center', va='bottom', fontsize=8, weight='bold')

        def bar(x, val, maxval, label, color):
            if val <= 0:
                return
            h = height * min(val / maxval, 1.0)
            patch = self._track_dynamic_artist(patches.Rectangle((x - 0.15, base_y), width, h, color=color, alpha=0.6))
            self.ax.add_patch(patch)
            self._track_dynamic_artist(self.ax.text(x + width / 2 - 0.15, base_y + h + 0.05, f'{label}', ha='center', va='bottom', fontsize=8))

        bar(x0, bar1_v - min_v, max_v - min_v, f'{bar1_v:.1f}V', colors[0])
        bar(x0 + 0.3, bar2_w, max_w, f'{bar2_w:.1f}W', colors[1])
        bar(x0 + 0.6, bar3_w, max_w, f'{bar3_w:.1f}W', colors[2])

    def flow(self, top_left, bottom_right, color='green', oneArrow=False, power=None, info=None, debug=False ):
        """
        Draw a 3-segment flow line with 90° bends through points a → b → c → d.
        An arrowhead is placed at point d.
        
        a, b, c, d: tuples of (x, y) coordinates
        """
        if power is None:
            logging.debug("PowerGauge:flow skipped: power=None info=%s", info)
            return
        label = f"{power:.1f}W (Est.) {info if debug else ''}" 
        xl, yt = top_left
        xr, yb = bottom_right
        a = (xl, yt)
        b = (xl, yb)            # move down to the start point
        bc1 = (xl + ((xr-xl) / 5), yb)
        bc2 = (xl + ((xr-xl) / 5)*4, yb)
        c = (xr, yb)            # move right to the end point
        d = (xr, yt)            # move up to the end point

        #logging.info(f"PowerGauge:flow: {a} -> {b} -> {c} -> {d}")
        if TRACE_POWERGAUGE:
            logging.info(f"PowerGauge:flow: {label}")
        
        codes = [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.LINETO]
        if oneArrow:
            verts = [a, b, c, d]
        else:
            verts1 = [a, b, bc1]
            verts2 = [bc1, bc2]
            verts3 = [bc2, c, d]
            verts = [verts1, verts2, verts3]
            #logging.info(f"PowerGauge:flow: {verts1} -> {verts2}")

        for verts in verts:
            path = Path(verts, codes[:len(verts)])
            arrow = self._track_dynamic_artist(FancyArrowPatch(path=path, arrowstyle='->', linewidth=2, color=color, mutation_scale=10, zorder=10))
            self.ax.add_patch(arrow)

            #path1 = Path(verts1, codes[:len(verts1)])
            #path2 = Path(verts2, codes[:len(verts2)])
            #arrow1 = FancyArrowPatch(path=path1, arrowstyle='->', linewidth=2, color=color, mutation_scale=10, zorder=10)
            #self.ax.add_patch(arrow1)
            #arrow2 = FancyArrowPatch(path=path2, arrowstyle='->', linewidth=2, color=color, mutation_scale=10, zorder=10)
            #self.ax.add_patch(arrow2)

        text = self._track_dynamic_artist(self.ax.text((xl + xr) / 2, yb + 0.02, label, ha='center', fontsize=9))
        self.tooltip.add_tip_artist(text, f"Estimated power flow")


    def update_gauges(self, data_history=None):
        #if data and len(data) > 3:
        #logging.info(f"PowerGauge:update_gauges: {data['time']}")
        #logging.info(f"PowerGauge:update_gauges: {data['device_nickname']}")
        if self._closed:
            return
        if data_history is None:
            data_history = self._last_data_history
        if not data_history:
            #logging.info("PowerGauge:update_gauges: No data_history")
            return
        self._last_data_history = data_history
        has_samples = any(len(data_history.get(key, [])) > 0 for key in ('pv_voltage', 'battery_voltage', 'load_voltage'))
        # The staged DrawAnimated path is still overpainting multiple live
        # telemetry text/artists. Keep live telemetry on the simpler full
        # redraw path for now; placeholder/status rendering can continue to
        # use the staged path separately.
        desired_animated_render = False
        if desired_animated_render != self._use_animated_render:
            self._use_animated_render = desired_animated_render
            self._invalidate_static()
        if self._ui_static_signature != self._current_ui_static_signature():
            self._invalidate_static()
        if TRACE_POWERGAUGE:
            logging.info("PowerGauge:update_gauges device=%s samples pv=%d batt=%d load=%d static_dirty=%s",
                         self.device_name,
                         len(data_history.get('pv_voltage', [])),
                         len(data_history.get('battery_voltage', [])),
                         len(data_history.get('load_voltage', [])),
                         self._static_dirty)

        self.lastTime = time.time()
        date_str = datetime.now().strftime("%H:%M:%S")
        self._cancel_pending_draw()
        if self._use_animated_render:
            try:
                self.drawanim.reset('update-gauges')
            except Exception:
                pass
        self._render_artists_animated = self._use_animated_render
        self._clear_dynamic_artists()
        self.tooltip.clear_tips()
        if self._static_dirty:
            self._render_static_scene(animated=self._use_animated_render)

        #nickname = 'N/A'
        #if 'device_nickname' in data:
        #    nickname = data['device_nickname'][1]

        #logging.info(f"PowerGauge:update_gauges: {self.info}")
        #logging.info(f"PowerGauge:update_gauges: {self.info.values()}")
        if TRACE_POWERGAUGE:
            xreport(self.device_name, 'PowerGauge', f"Update gauges {self.info}", green=True, )
        #xreport(self.device_name, 'PowerGauge', f"Update gauges {self.info.values()}", green=True, )

        #if self.nickname:
        #    self.ax.text(-0.15, 4.092, self.nickname, ha='left', va='bottom', fontsize=10, weight='bold')

        self.tooltip.clear_tips()

        fault_display = self.get_fault_display(data_history)
        fault_color = 'green' if fault_display == 'OK' else 'red'
        if TRACE_POWERGAUGE:
            logging.info(
                "FAULTTRACE powergauge.update_gauges device=%s render_codes=%r render_color=%s",
                self.device_name,
                fault_display,
                fault_color,
            )
        fault_text = self._track_dynamic_artist(self.ax.text(3.0, 2.0, fault_display, ha='center', va='bottom', fontsize=13, weight='bold', color=fault_color))
        self.tooltip.add_tip_artist(fault_text, FAULT_TOOLTIP_TABLE, fixedFont=True, name="fault-status")

        info_values = [
            v for k, v in self.info.items()
            if v and k not in ('device_nickname', 'status_text', 'status_level') and v != 'N/A' and v != ''
        ]
        self._replace_dynamic_text_artist(
            '_info_line_artist',
            -0.15, 0.092,
            f"{', '.join(info_values)}",
            ha='left', va='bottom', fontsize=10, weight='bold'
        )

        powerState = self.getPowerState(data_history)
        status_text = str(self.info.get('status_text') or '').strip()
        status_level = str(self.info.get('status_level') or 'info').lower()
        if status_text:
            status_color = {
                'ok': 'darkgreen',
                'error': 'darkred',
                'warn': '#8a5a00',
                'warning': '#8a5a00',
                'info': '#204a87',
            }.get(status_level, 'black')
            self._replace_dynamic_text_artist(
                '_state_line_artist',
                -0.15, -0.05,
                status_text,
                ha='left', va='bottom', fontsize=10, weight='bold', color=status_color
            )
        else:
            text = self._replace_dynamic_text_artist(
                '_state_line_artist',
                -0.15, -0.05,
                f"Inferred Power State: {powerState.name}",
                ha='left', va='bottom', fontsize=10, weight='bold'
            )
            powerinfo = [(p.name, PowerStateInfo[p]) for p in PowerState]
            table = tabulate.tabulate(powerinfo, headers=["PowerState", "Description"], tablefmt="grid")
            self.tooltip.add_tip_artist(text, table, fixedFont=True)

        # Last time string
        self.lastTimeText = self._track_dynamic_artist(self.ax.text(3.70, 2.078, f"{date_str}", ha='left', va='bottom', fontsize=10, weight='bold'))
        self.tooltip.add_tip_artist(self.lastTimeText, "Last update time")

        battery_capacity = self.active.get('battery_capacity', 8)
        batteries = self.active.get('batteries', 1)
        battery_button_str = f"{battery_capacity}Ah x{batteries}"
        self.batteries_button = self._track_dynamic_artist(
            self.ax.text(5.50, 0.128, battery_button_str, ha='center', va='bottom', fontsize=10, weight='bold')
        )


        # Draw the three gauge blocks
        max_v, max_a, max_w = 20, 100, 100
        #pvps_v, pvps_a, pvps_w = self.get_vcwn('pv', data_history, 1)
        #batt_v, batt_a, batt_w = self.get_vcwn('battery', data_history, 1)
        #load_v, load_a, load_w = self.get_vcwn('load', data_history, 1)

        # N.b. the annotated nn.nV / nn.nW is the measured V from the destination and computed W from the V and A
        block0_x = 0.5
        block1_x = 2.5
        block2_x = 4.5
        bar0_x = 0
        bar1_x = 0.26
        bar2_x = 0.54
        # Adjusted Y levels for better spacing
        zero_y = 0.55
        top_y = 0.45
        mid_y = 0.30
        extra_y = 0.02
        extra_x = 0.02
        x_shift = 1.0  # Shift left start of line

        AAAA = BBBB = CCCC = DDDD = EEEE = FFFF = ''
        if True:
            AAAA = 'AAAA'
            BBBB = 'BBBB'
            CCCC = 'CCCC'
            DDDD = 'DDDD'
            EEEE = 'EEEE'
            FFFF = 'FFFF'

        batt_color = 'blue'
        pvps_colors = load_color = ['lightgrey', 'lightgrey', 'lightgrey']
        batt_colors = ['lightgrey', 'lightgrey', 'lightgrey']
        load_colors = ['lightgrey', 'lightgrey', 'lightgrey']
        #pvps_numbers = [0, 0, 0]
        #batt_numbers = [0, 0, 0]
        #load_numbers = [0, 0, 0]
        try:
            match powerState:
                case PowerState.noPV_noBattery | PowerState.noPV_noCharging_noLoad:
                    batt_color = 'green'
                    batt_colors = ['green', 'white', 'white']
                    pass
                case PowerState.noPV_Discharging_Load:
                    batt_colors = ['grey', 'white', 'red']
                    load_colors = ['lightgrey', 'red', 'white']
                    if self.power.batt.batt_v >= 0 and self.power.batt.to_load_w is not None:
                        self.flow((block1_x+bar2_x, zero_y), (block2_x+bar1_x, top_y), color='red', power=self.power.batt.to_load_w, info='BBBB', ) # BBBB
                    pass
                case PowerState.PV_Charging_noLoad:
                    pvps_colors = load_color = ['grey', 'white', 'green']
                    batt_colors = ['grey', 'green', 'white']
                    if self.power.pvps.pvps_v > 1 and self.power.pvps.to_batt_w is not None:
                        self.flow((block0_x+bar2_x, zero_y), (block1_x+bar1_x, top_y), color='green', power=self.power.pvps.to_batt_w, info='AAAA', ) # AAAA
                    pass
                case PowerState.PV_Split_Load:
                    pvps_colors = load_color = ['grey', 'green', 'white']
                    batt_colors = ['grey', 'green', 'red']
                    load_colors = ['lightgrey', 'red', 'green']
                    if self.power.batt.batt_v > 0 and self.power.batt.to_load_w is not None:
                        self.flow((block1_x+bar2_x, zero_y), (block2_x+bar1_x, top_y), color='red', power=self.power.batt.to_load_w, info='BBBB', ) # BBBB

                    if self.power.pvps.pvps_v > 1 and self.power.load.load_v > 1 and self.power.load.from_pvps_w is not None:
                        self.flow((block0_x+bar1_x, zero_y), (block2_x+bar2_x, mid_y), color='green', power=self.power.load.from_pvps_w, info='DDDD', ) # DDDD
                    pass
                case PowerState.PV_Charging_Load:
                    pvps_colors = load_color = ['grey', 'green', 'green']
                    batt_colors = ['grey', 'green', 'red']
                    load_colors = ['lightgrey', 'white', 'green']
                    if self.power.pvps.pvps_v > 1 and self.power.pvps.to_batt_w is not None:
                        #self.flow((block0_x+bar2_x, zero_y), (block1_x+bar1_x, top_y), color='green', label=f'{batt_numbers[2]:.1f}W (Est.){EEEE}', ) # AAAA
                        self.flow((block0_x+bar2_x, zero_y), (block1_x+bar1_x, top_y), color='green', power=self.power.pvps.to_batt_w, info='EEEE', ) # AAAA

                    if self.power.pvps.pvps_v > 1 and self.power.load.load_v > 1 and self.power.load.from_pvps_w is not None:
                        #self.flow((block0_x+bar1_x, zero_y), (block2_x+bar2_x, mid_y), color='green', label=f'{load_numbers[2]:.1f}W (Est.){FFFF}', ) # DDDD
                        self.flow((block0_x+bar1_x, zero_y), (block2_x+bar2_x, mid_y), color='green', power=self.power.load.from_pvps_w, info='DDDD', ) # DDDD
                    pass
                case PowerState.UNKNOWN:
                    #pvps_color =batt_color = load_color = 'white'
                    logging.error(f"PowerGauge:update_gauges: UNKNOWN powerState={powerState}")
                    pass

        except Exception as e:
            logging.exception(f"PowerGauge:update_gauges: Error flows: {e}")
            print(traceback.format_exc(), file=sys.stderr )

        #logging.info(f"PowerGauge:update_gauges: pvps[{pvps_v:.1f} {pvps_a:.1f} {pvps_w:.1f}] batt[{batt_v:.1f} {batt_a:.1f} {batt_w:.1f}] load[{load_v:.1f} {load_a:.1f} {load_w:.1f}]")

        try:
            self.draw_block(block0_x, zero_y, "PV/PS",   colors=pvps_colors, gaugeType=Gaugetype.PVPS,
                            tooltip=f"Photovoltaic or Power Supply Voltage and Current\n",)
            self.draw_block(block1_x, zero_y, "Battery", colors=batt_colors, gaugeType=Gaugetype.Battery,
                            tooltip=f"Battery Voltage and Current\n")
            self.draw_block(block2_x, zero_y, "Load",    colors=load_colors, gaugeType=Gaugetype.Load,
                            tooltip=f"Load Voltage and Current\n",)
        except Exception as e:
            logging.exception(f"PowerGauge:update_gauges: Error drawing blocks: {e}")
            print(traceback.format_exc(), file=sys.stderr )




        #  pv on
        # if pv_v pv_w > load_w:
        #   batt_w = pv_w - load_w

        


            #flow( color='green',
            #             a=(block0_x+bar2_x, top_y 0.0),     d=(None, None), 
            #             b=(None, top_y+0.5),                c=(block1_x+bar1_x, None), 
            #        )
        #def flow(xl, yt, xr, yb, color='green'):
        self.ax.set_xlim(0, 6)
        self.ax.set_ylim(0, 2.2)
        if not self._closed:
            if self._use_animated_render:
                self._schedule_draw()
            else:
                self.canvas.draw()

        return



if __name__ == "__main__":

    for p in PowerState:
        info = PowerStateHelp.get(p, ())
        joined = " | ".join(info[:-1])
        print(f"PowerState: {p.name} {joined} {info[-1]}")

    #powerState = PowerState.noPV_noBattery
    #print(f"PowerState: {powerState}")
    #print(f"PowerState: {powerState.name}")
