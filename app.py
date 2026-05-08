#!/usr/bin/env python3
"""Command-line Geiger pulse counter for Raspberry Pi GPIO."""

import argparse
import os
import random
import sys
import threading
import time


GPIO_PIN = 17
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_PULL = "up"
DEFAULT_ACTIVE_STATE = "low"
DEFAULT_BOUNCE_MS = 25
DEFAULT_POLL_INTERVAL_MS = 1.0

SIMULATION_ENV = "GEIGER_SIMULATE"


class PulseCounter:
    def __init__(self, dead_time_ms):
        self._count = 0
        self._last_pulse_time = None
        self._dead_time_seconds = max(dead_time_ms / 1000.0, 0.0)
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self._count = 0
            self._last_pulse_time = None

    def pulse(self, *_args):
        now = time.monotonic()
        with self._lock:
            if (
                self._last_pulse_time is not None
                and now - self._last_pulse_time < self._dead_time_seconds
            ):
                return
            self._count += 1
            self._last_pulse_time = now

    def value(self):
        with self._lock:
            return self._count


class GpioPulseSource:
    def __init__(self, pin, pull, active_state, bounce_ms, poll_interval_ms, callback):
        try:
            import RPi.GPIO as GPIO
        except ImportError as exc:
            raise RuntimeError(
                "RPi.GPIO is not installed. Run install.sh or install "
                "python3-rpi.gpio with apt."
            ) from exc

        self._GPIO = GPIO
        self._pin = pin
        self._poll_stop_event = None
        self._poll_thread = None

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.IN, pull_up_down=self._pull_mode(GPIO, pull))

        kwargs = {"callback": lambda _channel: callback()}
        if bounce_ms is not None and bounce_ms > 0:
            kwargs["bouncetime"] = bounce_ms

        try:
            GPIO.add_event_detect(pin, self._edge_mode(GPIO, active_state), **kwargs)
        except RuntimeError as exc:
            print(
                "geiger: edge detection unavailable "
                f"({exc}); using GPIO polling every {poll_interval_ms:g} ms",
                file=sys.stderr,
            )
            self._start_polling(active_state, bounce_ms, poll_interval_ms, callback)

    def close(self):
        if self._poll_stop_event is not None:
            self._poll_stop_event.set()
            self._poll_thread.join(timeout=1.0)

        try:
            self._GPIO.remove_event_detect(self._pin)
        except Exception:
            pass

        try:
            self._GPIO.cleanup(self._pin)
        except Exception:
            pass

    @staticmethod
    def _pull_mode(GPIO, pull):
        if pull == "up":
            return GPIO.PUD_UP
        if pull == "down":
            return GPIO.PUD_DOWN
        return GPIO.PUD_OFF

    @staticmethod
    def _edge_mode(GPIO, active_state):
        if active_state == "high":
            return GPIO.RISING
        return GPIO.FALLING

    def _start_polling(self, active_state, bounce_ms, poll_interval_ms, callback):
        poll_interval = max(poll_interval_ms / 1000.0, 0.0001)
        bounce_seconds = None if not bounce_ms else bounce_ms / 1000.0
        self._poll_stop_event = threading.Event()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            args=(active_state, bounce_seconds, poll_interval, callback),
            daemon=True,
        )
        self._poll_thread.start()

    def _poll_loop(self, active_state, bounce_seconds, poll_interval, callback):
        was_active = self._is_active(active_state)
        last_pulse_time = 0.0

        while not self._poll_stop_event.wait(poll_interval):
            active = self._is_active(active_state)
            if active and not was_active:
                now = time.monotonic()
                if bounce_seconds is None or now - last_pulse_time >= bounce_seconds:
                    callback()
                    last_pulse_time = now
            was_active = active

    def _is_active(self, active_state):
        value = self._GPIO.input(self._pin)
        if active_state == "high":
            return value == self._GPIO.HIGH
        return value == self._GPIO.LOW


class SimulatedPulseSource:
    def __init__(self, callback):
        self._callback = callback
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self):
        self._stop_event.set()
        self._thread.join(timeout=1.0)

    def _run(self):
        while not self._stop_event.is_set():
            if self._stop_event.wait(random.uniform(0.12, 0.9)):
                return
            self._callback()


class ProgressDisplay:
    def __init__(self, enabled, stream):
        self._enabled = enabled
        self._stream = stream
        self._dots = 0
        self._last_line_length = 0
        self._last_update = 0.0

    def update(self, remaining, count, *, force=False):
        if not self._enabled:
            return

        now = time.monotonic()
        if not force and now - self._last_update < 0.2:
            return

        self._last_update = now
        self._dots = (self._dots % 4) + 1
        dot_text = "." * self._dots
        line = f"Counting {remaining:5.1f}s left | impulses {count} {dot_text:<4}"
        self._write_line(line)

    def finish(self, count):
        if not self._enabled:
            return

        self._write_line(f"Counting done           | impulses {count}")
        self._stream.write("\n")
        self._stream.flush()

    def _write_line(self, line):
        padding = " " * max(0, self._last_line_length - len(line))
        self._stream.write(f"\r{line}{padding}")
        self._stream.flush()
        self._last_line_length = len(line)


def parse_seconds(value):
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seconds must be a number") from exc

    seconds = abs(seconds)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be greater than zero")

    return seconds


def parse_bounce_ms(value):
    try:
        bounce_ms = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bounce-ms must be an integer") from exc

    if bounce_ms < 0:
        raise argparse.ArgumentTypeError("bounce-ms must be zero or greater")

    return bounce_ms


def parse_positive_float(name):
    def parser(value):
        try:
            number = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be a number") from exc

        if number <= 0:
            raise argparse.ArgumentTypeError(f"{name} must be greater than zero")

        return number

    return parser


def env_requests_simulation():
    return os.environ.get(SIMULATION_ENV, "").lower() in {"1", "true", "yes", "on"}


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="geiger.sh",
        description=(
            "Count Geiger interface impulses on a Raspberry Pi GPIO pin. "
            "The shorthand '-10' is accepted and means count for 10 seconds."
        )
    )
    parser.add_argument(
        "seconds",
        nargs="?",
        type=parse_seconds,
        default=DEFAULT_INTERVAL_SECONDS,
        help="counting interval in seconds, for example -10 or 60",
    )
    parser.add_argument("--pin", type=int, default=GPIO_PIN, help="BCM GPIO pin")
    parser.add_argument(
        "--pull",
        choices=("up", "down", "off"),
        default=DEFAULT_PULL,
        help="GPIO internal pull resistor",
    )
    parser.add_argument(
        "--active-high",
        action="store_const",
        dest="active_state",
        const="high",
        default=DEFAULT_ACTIVE_STATE,
        help="count rising edges instead of falling edges",
    )
    parser.add_argument(
        "--active-low",
        action="store_const",
        dest="active_state",
        const="low",
        help="count falling edges; this is the default",
    )
    parser.add_argument(
        "--bounce-ms",
        type=parse_bounce_ms,
        default=DEFAULT_BOUNCE_MS,
        help=(
            "software dead-time/debounce in milliseconds; default is "
            f"{DEFAULT_BOUNCE_MS} ms, set 0 to disable"
        ),
    )
    parser.add_argument(
        "--poll-interval-ms",
        type=parse_positive_float("poll-interval-ms"),
        default=DEFAULT_POLL_INTERVAL_MS,
        help=(
            "GPIO polling interval used only if edge detection is unavailable; "
            "default is 1 ms"
        ),
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="generate fake pulses for testing without GPIO hardware",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="force the counting progress animation",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="disable the counting progress animation",
    )
    return parser.parse_args(argv)


def should_show_progress(args):
    if args.no_progress:
        return False
    if args.progress:
        return True
    return sys.stderr.isatty()


def format_seconds(seconds):
    if float(seconds).is_integer():
        return str(int(seconds))
    return f"{seconds:g}"


def make_pulse_source(args, counter):
    if args.simulate or env_requests_simulation():
        return SimulatedPulseSource(counter.pulse)

    return GpioPulseSource(
        pin=args.pin,
        pull=args.pull,
        active_state=args.active_state,
        bounce_ms=args.bounce_ms,
        poll_interval_ms=args.poll_interval_ms,
        callback=counter.pulse,
    )


def count_for_interval(args):
    counter = PulseCounter(args.bounce_ms or 0)
    source = make_pulse_source(args, counter)
    progress = ProgressDisplay(should_show_progress(args), sys.stderr)

    try:
        counter.reset()
        start = time.monotonic()
        end = start + args.seconds
        progress.update(args.seconds, 0, force=True)

        while True:
            now = time.monotonic()
            remaining = end - now
            if remaining <= 0:
                break

            time.sleep(min(0.05, remaining))
            progress.update(max(end - time.monotonic(), 0.0), counter.value())

        count = counter.value()
        progress.finish(count)
        return count
    finally:
        source.close()


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        count = count_for_interval(args)
    except RuntimeError as exc:
        print(f"geiger: {exc}", file=sys.stderr)
        print("geiger: for off-device testing, run with --simulate", file=sys.stderr)
        return 2

    seconds = args.seconds
    cps = count / seconds
    cpm = cps * 60.0
    print(
        " ".join(
            (
                f"impulses={count}",
                f"seconds={format_seconds(seconds)}",
                f"cps={cps:.3f}",
                f"cpm={cpm:.1f}",
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
