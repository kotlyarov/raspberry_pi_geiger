#!/usr/bin/env python3
"""Small Tkinter Geiger counter GUI for Raspberry Pi GPIO pulses."""

import argparse
import os
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk


GPIO_PIN = 4
DEFAULT_INTERVAL_SECONDS = 10
PULL_UP = True
ACTIVE_STATE = False
BOUNCE_TIME = None


SIMULATION_ENV = "GEIGER_SIMULATE"


class GeigerCounterApp:
    def __init__(self, root, force_simulation=False):
        self.root = root
        self.force_simulation = force_simulation
        self.simulation_mode = force_simulation
        self.gpio_device = None

        self._count = 0
        self._counting = False
        self._count_lock = threading.Lock()
        self._start_time = None
        self._selected_interval = DEFAULT_INTERVAL_SECONDS
        self._finish_after_id = None
        self._refresh_after_id = None
        self._simulation_after_id = None

        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL_SECONDS))
        self.count_var = tk.StringVar(value="0")
        self.cpm_var = tk.StringVar(value="--")
        self.cps_var = tk.StringVar(value="--")
        self.mode_var = tk.StringVar(value="Mode: starting")
        self.status_var = tk.StringVar(value="Starting")

        self._build_gui()
        self._configure_pulse_source()

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_gui(self):
        self.root.title("Geiger Counter")
        self.root.resizable(False, False)

        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")

        interval_label = ttk.Label(main, text="Interval (s)")
        interval_label.grid(row=0, column=0, sticky="w")

        self.interval_entry = ttk.Entry(
            main,
            textvariable=self.interval_var,
            width=8,
            justify="right",
        )
        self.interval_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))

        self.start_button = ttk.Button(main, text="Start", command=self.start_counting)
        self.start_button.grid(row=0, column=2, sticky="ew")

        separator = ttk.Separator(main)
        separator.grid(row=1, column=0, columnspan=3, sticky="ew", pady=10)

        self._add_value_row(main, 2, "Raw pulses", self.count_var)
        self._add_value_row(main, 3, "CPM", self.cpm_var)
        self._add_value_row(main, 4, "CPS", self.cps_var)

        mode_label = ttk.Label(main, textvariable=self.mode_var)
        mode_label.grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))

        status_label = ttk.Label(main, textvariable=self.status_var, wraplength=260)
        status_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))

        main.columnconfigure(1, weight=1)
        self.interval_entry.focus_set()

    def _add_value_row(self, parent, row, label_text, variable):
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky="w", pady=2)

        value = ttk.Label(parent, textvariable=variable, anchor="e", font=("TkDefaultFont", 16, "bold"))
        value.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)

    def _configure_pulse_source(self):
        if self.force_simulation:
            self._use_simulation("simulation requested")
            return

        try:
            from gpiozero import DigitalInputDevice

            self.gpio_device = DigitalInputDevice(
                GPIO_PIN,
                pull_up=PULL_UP,
                active_state=ACTIVE_STATE,
                bounce_time=BOUNCE_TIME,
            )
            self.gpio_device.when_activated = self._handle_pulse
        except Exception as exc:
            self._use_simulation(f"GPIO unavailable: {exc}")
            return

        edge = "active-low" if ACTIVE_STATE is False else "active-high"
        self.mode_var.set(f"Mode: GPIO BCM {GPIO_PIN} ({edge})")
        self.status_var.set("Ready")

    def _use_simulation(self, reason):
        self.simulation_mode = True
        self.mode_var.set("Mode: simulation")
        self.status_var.set(f"Ready ({reason})")

    def start_counting(self):
        try:
            interval = float(self.interval_var.get().strip())
        except ValueError:
            self._show_interval_error()
            return

        if interval <= 0:
            self._show_interval_error()
            return

        self._selected_interval = interval
        with self._count_lock:
            self._count = 0

        self.count_var.set("0")
        self.cpm_var.set("--")
        self.cps_var.set("--")
        self._counting = True
        self._start_time = time.monotonic()

        self.start_button.state(["disabled"])
        self.interval_entry.state(["disabled"])

        self.status_var.set(f"Counting for {self._format_seconds(interval)} seconds")
        self._finish_after_id = self.root.after(int(interval * 1000), self.finish_counting)
        self._refresh_display()

        if self.simulation_mode:
            self._schedule_simulation_pulse()

    def _show_interval_error(self):
        messagebox.showerror("Invalid interval", "Enter a counting interval greater than 0 seconds.")
        self.interval_entry.focus_set()
        self.interval_entry.select_range(0, tk.END)

    def _handle_pulse(self):
        if not self._counting:
            return

        with self._count_lock:
            self._count += 1

    def _schedule_simulation_pulse(self):
        if not self._counting or not self.simulation_mode:
            return

        delay_ms = random.randint(120, 900)
        self._simulation_after_id = self.root.after(delay_ms, self._simulation_pulse)

    def _simulation_pulse(self):
        if not self._counting:
            return

        self._handle_pulse()
        self._schedule_simulation_pulse()

    def _refresh_display(self):
        if not self._counting:
            return

        elapsed = max(time.monotonic() - self._start_time, 0.001)
        count = self._current_count()
        self.count_var.set(str(count))
        self.cpm_var.set(f"{count * 60.0 / elapsed:.1f}")
        self.cps_var.set(f"{count / elapsed:.3f}")
        self._refresh_after_id = self.root.after(250, self._refresh_display)

    def finish_counting(self):
        if not self._counting:
            return

        self._counting = False
        self._cancel_after("_refresh_after_id")
        self._cancel_after("_simulation_after_id")

        count = self._current_count()
        interval = self._selected_interval
        self.count_var.set(str(count))
        self.cpm_var.set(f"{count * 60.0 / interval:.1f}")
        self.cps_var.set(f"{count / interval:.3f}")
        self.status_var.set("Done. Ready")

        self.interval_entry.state(["!disabled"])
        self.start_button.state(["!disabled"])
        self.start_button.focus_set()

    def _current_count(self):
        with self._count_lock:
            return self._count

    def _cancel_after(self, attr_name):
        after_id = getattr(self, attr_name)
        if after_id is None:
            return

        try:
            self.root.after_cancel(after_id)
        except tk.TclError:
            pass
        setattr(self, attr_name, None)

    def close(self):
        self._counting = False
        self._cancel_after("_finish_after_id")
        self._cancel_after("_refresh_after_id")
        self._cancel_after("_simulation_after_id")

        if self.gpio_device is not None:
            try:
                self.gpio_device.close()
            except Exception:
                pass

        self.root.destroy()

    @staticmethod
    def _format_seconds(seconds):
        if seconds.is_integer():
            return str(int(seconds))
        return f"{seconds:g}"


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Lightweight Tkinter Geiger counter GUI.")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="run without GPIO and generate simulated pulses",
    )
    return parser.parse_args(argv)


def env_requests_simulation():
    return os.environ.get(SIMULATION_ENV, "").lower() in {"1", "true", "yes", "on"}


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    force_simulation = args.simulate or env_requests_simulation()

    root = tk.Tk()
    GeigerCounterApp(root, force_simulation=force_simulation)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
