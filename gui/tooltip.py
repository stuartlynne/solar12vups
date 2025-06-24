import tkinter as tk

import logging
from lib.log import setup_logger, xreport
logger = logging.getLogger(__name__)

class ToolTipManager:
    def __init__(self, root, canvas_widget, mpl_canvas, ax):
        self.root = root                # Tk root window
        self.canvas_widget = canvas_widget  # Tk widget from FigureCanvasTkAgg
        self.mpl_canvas = mpl_canvas        # matplotlib canvas
        self.ax = ax                        # the matplotlib axes
        #self.tooltips = []                  # list of (test_func, text)
        self.tooltips = {}
        self.tooltip_window = None              # currently shown tooltip window
        self.label = None
        #self.label = tk.Label(canvas_widget, text="", bg="yellow", relief="solid", bd=1, font=("Arial", 8))
        #self.label = tk.Label(self.canvas_widget.master, text="", bg="yellow", relief="solid", bd=1, font=("Arial", 8))
        #self.label = tk.Label(self.root, text="", bg="yellow", relief="solid", bd=1, font=("Arial", 8))

        self.mpl_canvas.mpl_connect("motion_notify_event", self._on_motion)
        logging.info('ToolTipManager initialized with canvas_widget: %s, mpl_canvas: %s, ax: %s',)

    def add_tip_box(self, bounds, text, fixedFont=False, name=None):
        """
        Add tooltip using [x, y, w, h] in data coordinates
        """
        #logging.info('ToolTipmanager.add_tip_box: Adding tooltip box with bounds: %s, text: %s', bounds, text)
        def test(event):
            if event.inaxes != self.ax:
                return False
            x, y, w, h = bounds
            return x <= event.xdata <= x + w and y <= event.ydata <= y + h
        #self.tooltips.append((test, text, fixedFont))
        key = name if name else text
        self.tooltips[key] = ((test, text, fixedFont))

    def add_tip_artist(self, artist, text, fixedFont=False, name=None):
        """
        Add tooltip for a matplotlib artist (e.g., Patch, Line2D)
        """
        def test(event):
            if event.inaxes != self.ax:
                return False
            contains, _ = artist.contains(event)
            return contains
        #self.tooltips.append((test, text, fixedFont))
        key = name if name else text
        self.tooltips[key] = ((test, text, fixedFont))

    def clear_tips(self):
        #self._hide_tooltip()  # Hide any currently shown tooltip
        self.tooltips.clear()


    def _on_motion(self, event):
        for name, (test, text, fixedFont) in list(self.tooltips.items()):
            if test(event):
                if not self.tooltip_window or self.current_text != text:
                    self._show_tooltip(event, text, fixedFont=fixedFont)
                return
        self._hide_tooltip()

    def _show_tooltip(self, event, text, fixedFont=False):
        self._hide_tooltip()  # In case one is still visible
        self.current_text = text

        top = self.root.winfo_toplevel()
        self.tooltip_window = tw = tk.Toplevel(top)
        tw.wm_overrideredirect(True)

        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        tw.wm_geometry(f"+{pointer_x + 10}+{pointer_y + 10}")

        label = tk.Label(tw, text=text, background="yellow", relief="solid", borderwidth=1,
                         font=("Arial", 9) if not fixedFont else ("Courier", 9))
        label.pack()

        tw.lift()
        tw.attributes('-topmost', True)

    def _hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
            self.current_text = None

