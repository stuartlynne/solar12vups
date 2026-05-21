import tkinter as tk
from tkinter import ttk
from datetime import timedelta

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates
import numpy as np

from gui.powerstate import Power


class HistoryTab:
    RANGE_OPTIONS = [
        ("5m", 5),
        ("15m", 15),
        ("30m", 30),
        ("60m", 60),
        ("120m", 120),
    ]

    def __init__(self, device_name=None, tab_control=None, text="History"):
        self.device_name = device_name
        self.tab_control = tab_control
        self.text = text
        self._last_data_history = None

        self.tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab, text=text)

        controls = ttk.Frame(self.tab)
        controls.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(controls, text="Range").pack(side="left")
        self.range_var = tk.StringVar(value="60m")
        self.range_combo = ttk.Combobox(
            controls,
            textvariable=self.range_var,
            values=[label for label, _ in self.RANGE_OPTIONS],
            width=6,
            state="readonly",
        )
        self.range_combo.pack(side="left", padx=(6, 0))
        self.range_combo.bind("<<ComboboxSelected>>", self._on_range_changed)

        self.figure = Figure(figsize=(7, 2.0))
        self.ax = self.figure.add_subplot(111)
        self.ax_right = self.ax.twinx()
        self.figure.subplots_adjust(left=0.07, right=0.96, top=0.92, bottom=0.25)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.tab)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._render_empty()

    def _selected_minutes(self):
        label = self.range_var.get().strip()
        for option_label, minutes in self.RANGE_OPTIONS:
            if option_label == label:
                return minutes
        return 60

    def _on_range_changed(self, _event=None):
        if self._last_data_history is not None:
            self.update_history(self._last_data_history)

    def _extract_times(self, data_history):
        times = []
        for item in data_history.get('time', []):
            if isinstance(item, tuple) and len(item) >= 2:
                times.append(item[1])
            else:
                times.append(item)
        return times

    def _render_empty(self):
        self.ax.clear()
        self.ax_right.clear()
        self.ax.set_title("Voltage History")
        self.ax.set_ylabel("Volts")
        self.ax_right.set_ylabel("Load Watts")
        self.ax_right.yaxis.set_label_position("right")
        self.ax_right.yaxis.tick_right()
        self.ax.text(
            0.5, 0.5, "No history yet",
            transform=self.ax.transAxes,
            ha="center", va="center",
            fontsize=11, color="#666666",
        )
        self.ax.grid(True, alpha=0.25)
        self.canvas.draw()

    def _derive_load_components(self, data_history, n):
        pv_v = list(data_history.get('pv_voltage', []))[-n:]
        pv_a = list(data_history.get('pv_current', []))[-n:]
        load_v = list(data_history.get('load_voltage', []))[-n:]
        load_a = list(data_history.get('load_current', []))[-n:]
        batt_v = list(data_history.get('battery_voltage', []))[-n:]

        pv_to_load = []
        batt_to_load = []
        power = Power(name=f"{self.device_name}-history")

        for i in range(n):
            state = power.getPowerState(
                pvps_v=pv_v[i],
                pvps_a=pv_a[i],
                load_v=load_v[i],
                load_a=load_a[i],
                batt_v=batt_v[i],
                info="history",
            )
            _ = state
            pv_to_load.append(power.load.from_pvps_w or 0)
            batt_to_load.append(power.load.from_batt_w or 0)

        return pv_to_load, batt_to_load

    def _bar_width_days(self, times):
        if len(times) >= 2:
            deltas = [
                (times[i] - times[i - 1]).total_seconds()
                for i in range(1, len(times))
                if times[i] is not None and times[i - 1] is not None
            ]
            if deltas:
                return max(1.0, min(deltas) * 0.75) / 86400.0
        return 2.0 / 86400.0

    def update_history(self, data_history):
        self._last_data_history = data_history
        times = self._extract_times(data_history)
        if not times:
            self._render_empty()
            return

        pv = list(data_history.get('pv_voltage', []))
        batt = list(data_history.get('battery_voltage', []))
        load_v = list(data_history.get('load_voltage', []))
        load_a = list(data_history.get('load_current', []))

        n = min(len(times), len(pv), len(batt), len(load_v), len(load_a))
        if n <= 0:
            self._render_empty()
            return

        times = times[-n:]
        pv = pv[-n:]
        batt = batt[-n:]
        load_v = load_v[-n:]
        load_a = load_a[-n:]
        pv_a = list(data_history.get('pv_current', []))[-n:]

        cutoff = times[-1] - timedelta(minutes=self._selected_minutes())
        start_idx = 0
        for i, ts in enumerate(times):
            if ts >= cutoff:
                start_idx = i
                break
        times = times[start_idx:]
        pv = pv[start_idx:]
        batt = batt[start_idx:]
        pv_a = pv_a[start_idx:]
        load_v = load_v[start_idx:]
        load_a = load_a[start_idx:]
        n = len(times)
        if n <= 0:
            self._render_empty()
            return

        pv_to_load_w, batt_to_load_w = self._derive_load_components(
            {
                'pv_voltage': pv,
                'pv_current': pv_a,
                'load_voltage': load_v,
                'load_current': load_a,
                'battery_voltage': batt,
            },
            n,
        )

        self.ax.clear()
        self.ax_right.clear()
        self.ax.set_title(f"Voltage History ({self.range_var.get()})")
        self.ax.set_ylabel("Volts")
        self.ax_right.set_ylabel("Load Watts")
        self.ax_right.yaxis.set_label_position("right")
        self.ax_right.yaxis.tick_right()
        self.ax.plot(times, pv, color="green", linewidth=1.8, zorder=5, label="PV/PS")
        self.ax.plot(times, batt, color="red", linewidth=1.8, zorder=5, label="Battery")
        bar_width = self._bar_width_days(times)
        times_num = mdates.date2num(times)
        pv_bars = self.ax_right.bar(
            times_num,
            pv_to_load_w,
            width=bar_width,
            color="green",
            alpha=0.35,
            align="center",
            zorder=1,
            label="Load from PV/PS",
        )
        batt_bars = self.ax_right.bar(
            times_num,
            batt_to_load_w,
            width=bar_width,
            bottom=np.array(pv_to_load_w),
            color="red",
            alpha=0.35,
            align="center",
            zorder=1,
            label="Load from Battery",
        )
        self.ax.grid(True, alpha=0.25)
        legend_handles = [self.ax.get_lines()[0], self.ax.get_lines()[1], pv_bars, batt_bars]
        legend_labels = ["PV/PS Voltage", "Battery Voltage", "Load from PV/PS", "Load from Battery"]
        self.ax.legend(legend_handles, legend_labels, loc="upper left")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.figure.autofmt_xdate(rotation=20, ha="right")
        self.canvas.draw()
