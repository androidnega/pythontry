#!/usr/bin/env python3
"""Desktop calculator (tkinter). Web hosting: use Flask app in app.py + passenger_wsgi.py."""

import tkinter as tk
from tkinter import font as tkfont

from calculator_core import CalculatorState


class CalculatorApp:
    # Display = bright text on deep panel; digit keys = softer label color (not same as display).
    COLORS = {
        "bg": "#070b12",
        "display_bg": "#020617",
        "display_fg": "#f8fafc",
        "btn_num": "#1e293b",
        "btn_num_hover": "#334155",
        "btn_num_fg": "#94a3b8",
        "btn_op": "#2563eb",
        "btn_op_hover": "#3b82f6",
        "btn_op_fg": "#ffffff",
        "btn_eq": "#059669",
        "btn_eq_hover": "#10b981",
        "btn_eq_fg": "#ecfdf5",
        "btn_clear": "#be123c",
        "btn_clear_hover": "#e11d48",
        "btn_clear_fg": "#fff1f2",
        "btn_back": "#475569",
        "btn_back_hover": "#64748b",
        "btn_back_fg": "#e2e8f0",
    }

    def __init__(self) -> None:
        self._model = CalculatorState()
        self.root = tk.Tk()
        self.root.title("Calculator")
        self.root.resizable(False, False)
        self.root.configure(bg=self.COLORS["bg"])

        self._display_font = tkfont.Font(family="SF Pro Display", size=28, weight="normal")
        try:
            _ = self._display_font.actual("family")
        except tk.TclError:
            self._display_font = tkfont.Font(family="Helvetica Neue", size=26, weight="normal")

        self._btn_font = tkfont.Font(family="SF Pro Text", size=18, weight="normal")
        try:
            _ = self._btn_font.actual("family")
        except tk.TclError:
            self._btn_font = tkfont.Font(family="Helvetica Neue", size=17, weight="bold")

        self.display_var = tk.StringVar(value=self._model.display)
        self._build_ui()

    def _press(self, text: str, kind: str) -> None:
        self._model.dispatch(text, kind)
        self.display_var.set(self._model.display)

    def _build_ui(self) -> None:
        c = self.COLORS
        pad = 12

        outer = tk.Frame(self.root, bg=c["bg"], padx=pad, pady=pad)
        outer.pack(fill=tk.BOTH, expand=True)

        display = tk.Label(
            outer,
            textvariable=self.display_var,
            font=self._display_font,
            bg=c["display_bg"],
            fg=c["display_fg"],
            anchor="e",
            padx=16,
            pady=20,
            width=12,
        )
        display.pack(fill=tk.X, pady=(0, pad))

        grid = tk.Frame(outer, bg=c["bg"])
        grid.pack()

        layout = [
            ("C", 0, 0, "clear", 2), ("⌫", 0, 2, "back", 2),
            ("7", 1, 0, "num", 1), ("8", 1, 1, "num", 1), ("9", 1, 2, "num", 1), ("÷", 1, 3, "op", 1),
            ("4", 2, 0, "num", 1), ("5", 2, 1, "num", 1), ("6", 2, 2, "num", 1), ("×", 2, 3, "op", 1),
            ("1", 3, 0, "num", 1), ("2", 3, 1, "num", 1), ("3", 3, 2, "num", 1), ("−", 3, 3, "op", 1),
            ("0", 4, 0, "num", 1), (".", 4, 1, "num", 1), ("=", 4, 2, "eq", 1), ("+", 4, 3, "op", 1),
        ]

        btn_w, btn_h, gap = 72, 56, 8
        for spec in layout:
            text, row, col, kind, colspan = spec
            bg, hover = self._style_for(kind)
            fg = self._fg_for(kind)
            btn = tk.Button(
                grid,
                text=text,
                font=self._btn_font,
                bg=bg,
                fg=fg,
                activebackground=hover,
                activeforeground=fg,
                relief=tk.FLAT,
                border=0,
                width=1,
                height=1,
                cursor="hand2",
                command=lambda t=text, k=kind: self._press(t, k),
            )
            btn.grid(
                row=row,
                column=col,
                columnspan=colspan,
                padx=gap // 2,
                pady=gap // 2,
                sticky="nsew",
                ipadx=8,
                ipady=8,
            )
            self._bind_hover(btn, bg, hover)

        for col in range(4):
            grid.grid_columnconfigure(col, minsize=btn_w + gap)
        for r in range(5):
            grid.grid_rowconfigure(r, minsize=btn_h + gap)

    def _style_for(self, kind: str) -> tuple[str, str]:
        c = self.COLORS
        if kind == "clear":
            return c["btn_clear"], c["btn_clear_hover"]
        if kind == "back":
            return c["btn_back"], c["btn_back_hover"]
        if kind == "op":
            return c["btn_op"], c["btn_op_hover"]
        if kind == "eq":
            return c["btn_eq"], c["btn_eq_hover"]
        return c["btn_num"], c["btn_num_hover"]

    def _fg_for(self, kind: str) -> str:
        c = self.COLORS
        if kind == "clear":
            return c["btn_clear_fg"]
        if kind == "back":
            return c["btn_back_fg"]
        if kind == "op":
            return c["btn_op_fg"]
        if kind == "eq":
            return c["btn_eq_fg"]
        return c["btn_num_fg"]

    def _bind_hover(self, btn: tk.Button, normal: str, hover: str) -> None:
        def enter(_: object) -> None:
            if btn["state"] != tk.DISABLED:
                btn.configure(bg=hover)

        def leave(_: object) -> None:
            btn.configure(bg=normal)

        btn.bind("<Enter>", enter)
        btn.bind("<Leave>", leave)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    CalculatorApp().run()


if __name__ == "__main__":
    main()
