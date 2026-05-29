import tkinter as tk
from tkinter import ttk
import logging
from functools import partial

class LabelEditEx(ttk.LabelFrame):
    def __init__(self, parent, grid=None, labelframe=True, background="white",
                 outerFlag=False, editable=False, option=None,
                 description="", addr=None, value="", callback=None, **kwargs):

        self.option = option
        self.labelframe = labelframe
        self.outerFlag = outerFlag
        self.editable = editable
        self._initialized = False
        self.addr = addr
        self.description = description
        self.callback = callback
        self.entry = None
        self.value_widget = None
        self._editing = False

        self._pending_description = description
        self._pending_addr = addr
        self._pending_value = value
        self._pending_editable = editable

        label_title = description if option == 2 else f"{addr:04x}" if addr is not None else ""
        super().__init__(parent, text=label_title, **kwargs)

        self.frame = ttk.Frame(self)
        self.frame.pack(fill="both", expand=True, padx=4, pady=4)

        if grid:
            grid.setdefault("padx", 5)
            grid.setdefault("pady", 5)
            self.grid(**grid)

    def on_focus_in(self, event=None):
        #logging.info(f"LabelEditEx {self.addr} focus_in")
        self._editing = True

    def on_focus_out(self, event=None):
        #logging.info(f"LabelEditEx {self.addr} focus_out")
        self._editing = False
        if self.callback and hasattr(self, "entry"):
            try:
                value = self.entry.get()
                self.callback(self.addr, self.description, value)
            except Exception as e:
                logging.error(f"Error in on_focus_out callback: {e}")
                logging.error(traceback.format_exc())

    def key_release(self, event=None):
        #logging.info(f"LabelEditEx {self.addr} focus_out")
        #self._editing = False
        pass

    def set_text(self, description=None, value=None, editable=False):
        if not self._initialized:
            #logging.info(f"Initializing LabelEditEx {self.addr} {description} {value} {editable} {self.option}")
            self.option = self.option or 2
            self._initialized = True

            self.description = description or self._pending_description
            value = value if value is not None else self._pending_value
            editable = editable or self._pending_editable

            addrhex = f"{self.addr:04x}" if self.addr is not None else ""

            if self.option == 1:
                if editable:
                    self.entry = tk.Entry(self.frame, font=("TkDefaultFont", 10), justify="center")
                    self.entry.insert(0, str(value))
                    self.entry.pack(fill="x", padx=4, pady=2)
                    self.value_widget = self.entry
                else:
                    self.value_widget = ttk.Label(self.frame, text=str(value), anchor="center")
                    self.value_widget.pack(fill="x", padx=4, pady=2)

                ttk.Label(self, text=self.description, font=("TkDefaultFont", 8), anchor="e").pack(anchor="e", padx=4, pady=(2, 0))

            else:
                self.config(text=description)
                self.frame.columnconfigure(1, weight=1)
                ttk.Label(self.frame, text=addrhex, font=("TkDefaultFont", 8), anchor="e") \
                    .grid(row=0, column=0, sticky="e", padx=(4, 2))

                if editable:
                    self.entry = tk.Entry(self.frame, font=("TkDefaultFont", 10), justify="center")
                    self.entry.insert(0, str(value))
                    self.entry.grid(row=0, column=1, sticky="ew", padx=(2, 4))
                    self.value_widget = self.entry
                else:
                    self.value_widget = ttk.Label(self.frame, text=str(value), anchor="center")
                    self.value_widget.grid(row=0, column=1, sticky="ew", padx=(2, 4))
            if self.entry:
                #logging.info(f"Binding entry to callback {self.callback}")
                self.entry.bind("<KeyRelease>", self.key_release)
                self.entry.bind("<FocusIn>", self.on_focus_in)
                self.entry.bind("<FocusOut>", self.on_focus_out)
            return

        #if self.option == 2 and description:
        #    self.config(text=description)
        #elif self.option == 1 and addr is not None:
        #    self.config(text=f"{addr:04x}")

        if self._editing:
            #logging.info(f"LabelEditEx {self.addr} is being edited, not updating text")
            return

        if self.option == 1 and description:
            for child in self.winfo_children():
                if isinstance(child, ttk.Label) and child.cget("anchor") == "e":
                    child.config(text=description)

        if self.option == 2 and self.addr is not None:
            for child in self.frame.winfo_children():
                if isinstance(child, ttk.Label) and child.grid_info().get("column") == 0:
                    child.config(text=f"{self.addr:04x}")

        if hasattr(self, "entry") and isinstance(self.entry, tk.Entry):
            self.entry.delete(0, tk.END)
            self.entry.insert(0, str(value))
        else:
            for child in self.frame.winfo_children():
                if isinstance(child, ttk.Label) and child.grid_info().get("column") == 1:
                    child.config(text=str(value))

    def get_value(self):
        if self.editable and hasattr(self, "entry") and self.entry:
            return self.entry.get()
        return None

    def set_value_style(self, changed=False):
        color = "#b24a00" if changed else "black"
        widget = self.value_widget
        if widget is None:
            return
        try:
            if isinstance(widget, tk.Entry):
                widget.configure(fg=color)
            else:
                widget.configure(foreground=color)
        except Exception:
            pass
