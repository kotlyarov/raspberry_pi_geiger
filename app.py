#!/usr/bin/env python3
"""Command-line Geiger pulse counter for Raspberry Pi GPIO."""

import argparse
import hmac
import json
import os
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


GPIO_PIN = 17
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_PULL = "up"
DEFAULT_ACTIVE_STATE = "low"
DEFAULT_BOUNCE_MS = 25
DEFAULT_POLL_INTERVAL_MS = 1.0
DEFAULT_WEB_HOST = "0.0.0.0"
DEFAULT_WEB_PORT = 80
PASSWORD_LENGTH = 10

SIMULATION_ENV = "GEIGER_SIMULATE"
PASSWORD_FILE_ENV = "GEIGER_PASSWORD_FILE"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PASSWORD_FILE = os.path.join(APP_DIR, "password.txt")


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


def parse_port(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc

    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")

    return port


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
    parser.add_argument(
        "--serve",
        action="store_true",
        help="run the lightweight HTTP JSON API instead of one terminal count",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_WEB_HOST,
        help=f"HTTP API bind address; default is {DEFAULT_WEB_HOST}",
    )
    parser.add_argument(
        "--port",
        type=parse_port,
        default=DEFAULT_WEB_PORT,
        help=f"HTTP API port; default is {DEFAULT_WEB_PORT}",
    )
    parser.add_argument(
        "--password-file",
        "--pwd-file",
        dest="password_file",
        default=os.environ.get(PASSWORD_FILE_ENV, DEFAULT_PASSWORD_FILE),
        help=f"file containing the {PASSWORD_LENGTH} character HTTP password",
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


def result_from_count(count, args):
    seconds = args.seconds
    cps = count / seconds
    cpm = cps * 60.0
    return {
        "impulses": count,
        "seconds": int(seconds) if float(seconds).is_integer() else seconds,
        "cps": round(cps, 3),
        "cpm": round(cpm, 1),
        "pin": args.pin,
        "pull": args.pull,
        "active_state": args.active_state,
        "bounce_ms": args.bounce_ms,
        "poll_interval_ms": args.poll_interval_ms,
        "simulate": bool(args.simulate or env_requests_simulation()),
    }


def format_result_line(result):
    return " ".join(
        (
            f"impulses={result['impulses']}",
            f"seconds={format_seconds(result['seconds'])}",
            f"cps={result['cps']:.3f}",
            f"cpm={result['cpm']:.1f}",
        )
    )


def count_and_summarize(args):
    return result_from_count(count_for_interval(args), args)


def read_password(path):
    try:
        with open(path, "r", encoding="utf-8") as password_file:
            password = password_file.read().strip()
    except OSError as exc:
        raise RuntimeError(f"cannot read password file {path}: {exc}") from exc

    if len(password) != PASSWORD_LENGTH:
        raise RuntimeError(
            f"password file {path} must contain exactly {PASSWORD_LENGTH} characters"
        )

    return password


def parse_bool_query(value, name):
    if value == "":
        return True

    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"{name} must be true or false")


def single_query_value(params, *names):
    for name in names:
        if name not in params:
            continue

        values = params[name]
        if len(values) != 1:
            raise ValueError(f"{name} may only be supplied once")
        return values[0]

    return None


def parse_query_with_parser(params, parser, *names):
    value = single_query_value(params, *names)
    if value is None:
        return None

    try:
        return parser(value)
    except argparse.ArgumentTypeError as exc:
        raise ValueError(str(exc)) from exc


def geiger_args_from_query(params, base_args):
    args = argparse.Namespace(
        seconds=base_args.seconds,
        pin=base_args.pin,
        pull=base_args.pull,
        active_state=base_args.active_state,
        bounce_ms=base_args.bounce_ms,
        poll_interval_ms=base_args.poll_interval_ms,
        simulate=base_args.simulate,
        progress=False,
        no_progress=True,
    )

    seconds = parse_query_with_parser(params, parse_seconds, "s", "seconds")
    if seconds is not None:
        args.seconds = seconds

    pin = single_query_value(params, "pin")
    if pin is not None:
        try:
            args.pin = int(pin)
        except ValueError as exc:
            raise ValueError("pin must be an integer") from exc

    pull = single_query_value(params, "pull")
    if pull is not None:
        if pull not in {"up", "down", "off"}:
            raise ValueError("pull must be one of: up, down, off")
        args.pull = pull

    active_state = single_query_value(
        params, "active", "active-state", "active_state"
    )
    if active_state is not None:
        if active_state not in {"high", "low"}:
            raise ValueError("active must be high or low")
        args.active_state = active_state

    active_high = single_query_value(params, "active-high", "active_high")
    active_low = single_query_value(params, "active-low", "active_low")
    if active_high is not None and parse_bool_query(active_high, "active-high"):
        args.active_state = "high"
    if active_low is not None and parse_bool_query(active_low, "active-low"):
        args.active_state = "low"

    bounce_ms = parse_query_with_parser(
        params, parse_bounce_ms, "bounce-ms", "bounce_ms"
    )
    if bounce_ms is not None:
        args.bounce_ms = bounce_ms

    poll_interval_ms = parse_query_with_parser(
        params,
        parse_positive_float("poll-interval-ms"),
        "poll-interval-ms",
        "poll_interval_ms",
    )
    if poll_interval_ms is not None:
        args.poll_interval_ms = poll_interval_ms

    simulate = single_query_value(params, "simulate")
    if simulate is not None:
        args.simulate = parse_bool_query(simulate, "simulate")

    return args


class GeigerRequestHandler(BaseHTTPRequestHandler):
    server_version = "GeigerHTTP/1.0"

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_common_headers(0)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/geiger":
            self._send_json(404, {"error": "not_found"})
            return

        try:
            params = parse_qs(parsed.query, keep_blank_values=True)
            request_password = single_query_value(params, "pwd")
        except ValueError as exc:
            self._send_json(400, {"error": "bad_request", "message": str(exc)})
            return

        if request_password is None or not hmac.compare_digest(
            request_password.encode("utf-8"), self.server.password_bytes
        ):
            self._send_json(401, {"error": "unauthorized"})
            return

        try:
            request_args = geiger_args_from_query(params, self.server.base_args)
        except ValueError as exc:
            self._send_json(400, {"error": "bad_request", "message": str(exc)})
            return

        if not self.server.count_lock.acquire(blocking=False):
            self._send_json(409, {"error": "busy"})
            return

        try:
            result = count_and_summarize(request_args)
        except RuntimeError as exc:
            self._send_json(
                500,
                {
                    "error": "runtime_error",
                    "message": str(exc),
                },
            )
            return
        finally:
            self.server.count_lock.release()

        self._send_json(200, result)

    def _send_json(self, status, data):
        body = json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"
        self.send_response(status)
        self._send_common_headers(len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self, content_length):
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        print(f"geiger-api: {self.address_string()} - {fmt % args}", file=sys.stderr)


def run_web_service(args):
    password = read_password(args.password_file)

    server = ThreadingHTTPServer((args.host, args.port), GeigerRequestHandler)
    server.password_bytes = password.encode("utf-8")
    server.base_args = args
    server.count_lock = threading.Lock()

    print(
        f"geiger: HTTP API listening on http://{args.host}:{args.port}/geiger",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return 0


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.serve:
        try:
            return run_web_service(args)
        except (OSError, RuntimeError) as exc:
            print(f"geiger: {exc}", file=sys.stderr)
            return 2

    try:
        result = count_and_summarize(args)
    except RuntimeError as exc:
        print(f"geiger: {exc}", file=sys.stderr)
        print("geiger: for off-device testing, run with --simulate", file=sys.stderr)
        return 2

    print(format_result_line(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
