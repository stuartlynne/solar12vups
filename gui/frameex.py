import tkinter as tk
from tkinter import ttk

# FrameEx


class FrameEx(ttk.Frame):
    def __init__(self, parent, grid=None, labelframe=False, background="white", outerFlag=False, editable=False, **kwargs):
        self.labelframe = labelframe
        self.outerFlag = outerFlag
        self.style_name = None
        if False:
            self._text_label = None
        else:
            self._text_widget = None
        self.editable = editable

        # Create outer LabelFrame or Frame
        if labelframe:
            self.style_name = f"Custom.TLabelframe_{id(self)}"
            style = ttk.Style()
            style.layout(self.style_name, style.layout("TLabelframe"))
            style.configure(self.style_name, background=background, borderwidth=1, relief="groove")
            style.configure(self.style_name + ".Label", background=background, font=("TkDefaultFont", 9))
            self.outer = ttk.LabelFrame(parent, style=self.style_name, **kwargs)
        else:
            self.outer = ttk.Frame(parent, **kwargs)


        # 🔳 INNER PADDING BETWEEN BORDER AND CONTENT
        # You can adjust this for outer vs inner usage
        padx = 0 if outerFlag else 0
        pady = 0 if outerFlag else 0

        self.frame = ttk.Frame(self.outer)
        self.frame.pack(fill="both", expand=True, padx=padx, pady=pady)

        # 🔲 OUTER FRAME PLACEMENT PADDING
        if grid:
            grid.setdefault("padx", 2 if outerFlag else 0)
            grid.setdefault("pady", 0 if outerFlag else 0)
            self.outer.grid(**grid)

    def config(self, **kwargs):
        self.outer.config(**kwargs)

    def set_background(self, color):
        if self.labelframe and self.style_name:
            style = ttk.Style()
            style.configure(self.style_name, background=color)
            style.configure(self.style_name + ".Label", background=color)
        for child in self.frame.winfo_children():
            try:
                child.configure(background=color)
            except Exception:
                pass

    def set_title(self, text):
        if self.labelframe:
            self.outer.config(text=text)

    def xset_text(self, text, background=None, **kwargs):
        """Replace or set a single label inside the inner frame."""
        if self._text_label is None:
            self._text_label = tk.Label(
                self.frame,
                text=text,
                font=("TkDefaultFont", 18),
                padx=0,
                pady=0,
                **kwargs
            )
            self._text_label.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
            self.frame.columnconfigure(0, weight=1)
            self.frame.rowconfigure(0, weight=1)
        else:
            self._text_label.config(text=text, **kwargs)
        if background:
            self.set_background(color=background)

    def set_text(self, text, background=None, **kwargs):
        """Set text or value. If editable=True, use Entry."""
        if self._text_widget is None:
            if self.editable:
                self._text_widget = tk.Entry(self.frame, font=("TkDefaultFont", 9), **kwargs)
                self._text_widget.insert(0, text)
            else:
                self._text_widget = tk.Label(self.frame, text=text, font=("TkDefaultFont", 10), **kwargs)

            self._text_widget.grid(row=0, column=0, sticky="nsew", padx=2, pady=1)
            self.frame.columnconfigure(0, weight=1)
            self.frame.rowconfigure(0, weight=1)
        else:
            if self.editable:
                self._text_widget.delete(0, tk.END)
                self._text_widget.insert(0, text)
            else:
                self._text_widget.config(text=text, **kwargs)
        if background:
            self.set_background(color=background)

    def get_value(self):
        if self._text_widget is None:
            return ""
        if self.editable:
            return self._text_widget.get()
        else:
            return self._text_widget.cget("text")

    def set_value(self, value):
        if self.editable and self._text_widget:
            self._text_widget.delete(0, tk.END)
            self._text_widget.insert(0, value)


    def grid(self, *args, **kwargs):
        return self.outer.grid(*args, **kwargs)

    def pack(self, *args, **kwargs):
        return self.outer.pack(*args, **kwargs)

    def place(self, *args, **kwargs):
        return self.outer.place(*args, **kwargs)

    def columnconfigure(self, *args, **kwargs):
        return self.frame.columnconfigure(*args, **kwargs)

    def rowconfigure(self, *args, **kwargs):
        return self.frame.rowconfigure(*args, **kwargs)

    def winfo_children(self):
        return self.frame.winfo_children()

    def destroy(self):
        return self.outer.destroy()

