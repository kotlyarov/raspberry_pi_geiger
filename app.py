#!/usr/bin/env python3
"""Command-line Geiger pulse counter for Raspberry Pi GPIO."""

import argparse
import os
import random
import sys
import threading
import time


GPIO_PIN = 4
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_PULL = "up"
DEFAULT_ACTIVE_STATE = "low"
DEFAULT_BOUNCE_MS = None

SIMULATION_ENV = "GEIGER_SIMULATE"


class PulseCounter:
    def __init__(self):
        self._count = 0
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self._count = 0

    def pulse(self, *_args):
        with self._lock:
            self._count += 1

    def value(self):
        with self._lock:
            return self._count


class GpioPulseSource:
    def __init__(self, pin, pull, active_state, bounce_ms, callback):
        try:
            import RPi.GPIO as GPIO
        except ImportError as exc:
            raise RuntimeError(
                "RPi.GPIO is not installed. Run install.sh or install "
                "python3-rpi.gpio with apt."
            ) from exc

        self._GPIO = GPIO
        self._pin = pin

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.IN, pull_up_down=self._pull_mode(GPIO, pull))

        kwargs = {"callback": lambda _channel: callback()}
        if bounce_ms is not None:
            kwargs["bouncetime"] = bounce_ms

        GPIO.add_event_detect(pin, self._edge_mode(GPIO, active_state), **kwargs)

    def close(self):
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
        help="optional RPi.GPIO debounce time in milliseconds",
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
        callback=counter.pulse,
    )


def count_for_interval(args):
    counter = PulseCounter()
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
