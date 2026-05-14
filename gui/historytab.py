import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates


class HistoryTab:
    def __init__(self, device_name=None, tab_control=None, text="History"):
        self.device_name = device_name
        self.tab_control = tab_control
        self.text = text

        self.tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab, text=text)

        self.figure = Figure(figsize=(7, 2.0))
        self.ax = self.figure.add_subplot(111)
        self.ax_right = self.ax.twinx()
        self.figure.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.25)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.tab)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._render_empty()

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

    def update_history(self, data_history):
        times = self._extract_times(data_history)
        if not times:
            self._render_empty()
            return

        pv = list(data_history.get('pv_voltage', []))
        batt = list(data_history.get('battery_voltage', []))
        load_w = list(data_history.get('load_power', []))

        n = min(len(times), len(pv), len(batt), len(load_w))
        if n <= 0:
            self._render_empty()
            return

        times = times[-n:]
        pv = pv[-n:]
        batt = batt[-n:]
        load_w = load_w[-n:]

        self.ax.clear()
        self.ax_right.clear()
        self.ax.set_title("Voltage History")
        self.ax.set_ylabel("Volts")
        self.ax_right.set_ylabel("Load Watts")
        self.ax_right.yaxis.set_label_position("right")
        self.ax_right.yaxis.tick_right()
        self.ax.plot(times, pv, color="green", linewidth=1.5, label="PV/PS")
        self.ax.plot(times, batt, color="tab:blue", linewidth=1.5, label="Battery")
        self.ax_right.plot(times, load_w, color="tab:red", linewidth=1.5, label="Load")
        self.ax.grid(True, alpha=0.25)
        lines = self.ax.get_lines() + self.ax_right.get_lines()
        labels = [line.get_label() for line in lines]
        self.ax.legend(lines, labels, loc="upper left")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.figure.autofmt_xdate(rotation=20, ha="right")
        self.canvas.draw()
