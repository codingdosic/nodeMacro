import ctypes
import math
import sys
import threading
import time
from ctypes import wintypes

from pynput import keyboard, mouse

from backend.config import get_setting


WAIT_THRESHOLD = 0.1
MAX_EVENTS = 5000
MAX_SECONDS = 600
MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")
MODIFIERS = set(MODIFIER_ORDER)
TRANSIENT_WINDOW_CLASSES = {
    "#32768",  # native menus
    "tooltips_class32",
    "sysshadow",
    "xamlexplorerhostislandwindow",
    "windows.ui.composition.desktopwindowcontentbridge",
}
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


def _is_transient_window(class_name, ex_style):
    return (
        str(class_name or "").casefold() in TRANSIENT_WINDOW_CLASSES
        or bool(int(ex_style or 0) & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE))
    )


def _window_info(hwnd):
    if sys.platform != "win32" or not hwnd:
        return None
    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
    class_name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_name, len(class_name))
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    if _is_transient_window(class_name.value, user32.GetWindowLongPtrW(hwnd, -20)):
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return None
    title = ctypes.create_unicode_buffer(length + 1)
    rect = wintypes.RECT()
    user32.GetWindowTextW(hwnd, title, len(title))
    if not title.value or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return {
        "title": title.value,
        "rect": [rect.left, rect.top, rect.right, rect.bottom],
    }


def _window_at(x, y):
    if sys.platform != "win32":
        return None
    point = wintypes.POINT(int(x), int(y))
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.restype = wintypes.HWND
    return _window_info(user32.WindowFromPoint(point))


def _foreground_window():
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    return _window_info(user32.GetForegroundWindow())


def _key_name(key):
    name = getattr(key, "name", None)
    if not name:
        return getattr(key, "char", None)
    return {
        "ctrl_l": "ctrl", "ctrl_r": "ctrl",
        "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
        "shift_l": "shift", "shift_r": "shift",
        "cmd": "win", "cmd_l": "win", "cmd_r": "win",
    }.get(name, name)


def _same_window(left, right):
    return (left or {}).get("title") == (right or {}).get("title")


def _collapse_events(events):
    collapsed = []
    for event in events:
        current = dict(event)
        previous = collapsed[-1] if collapsed else None
        if (
            current["kind"] == "scroll"
            and previous and previous["kind"] == "scroll"
            and current["time"] - previous.get("end_time", previous["time"]) <= 0.25
            and current.get("axis") == previous.get("axis")
            and _same_window(current.get("window"), previous.get("window"))
        ):
            previous["amount"] += current["amount"]
            previous["x"], previous["y"] = current["x"], current["y"]
            previous["end_time"] = current["time"]
            continue
        if (
            current["kind"] == "click" and current["button"] == "left"
            and previous and previous["kind"] == "click" and previous["button"] == "left"
            and current["time"] - previous["time"] <= 0.5
            and math.hypot(current["x"] - previous["x"], current["y"] - previous["y"]) <= 4
        ):
            previous["button"] = "double"
            previous["interval"] = current["time"] - previous["time"]
            previous["duration"] = 0
            previous["end_time"] = current["time"] + current.get("duration", 0)
            continue
        collapsed.append(current)
    return collapsed


def events_to_steps(events):
    events = _collapse_events(sorted(events, key=lambda item: item["time"]))
    steps = [{"type": "start", "config": {"delay": 0}}]
    current_window = None
    previous_end = None
    index = 0

    def add_wait(start):
        nonlocal previous_end
        if previous_end is None:
            return
        gap = start - previous_end
        if gap >= WAIT_THRESHOLD:
            steps.append({"type": "wait", "config": {"ms": max(1, round(gap * 100) * 10)}})

    def use_window(window):
        nonlocal current_window
        title = (window or {}).get("title")
        if title and title != current_window:
            steps.append({
                "type": "window",
                "config": {"title": title, "timeout": 10, "poll_interval": 0.2, "activate": True},
            })
            current_window = title

    def coordinate(x, y, window):
        rect = (window or {}).get("rect")
        relative = bool(rect and (window or {}).get("title"))
        if relative:
            x, y = int(x - rect[0]), int(y - rect[1])
        steps.append({
            "type": "click",
            "config": {"x": int(x), "y": int(y), "relative_to_window": relative},
        })

    while index < len(events):
        event = events[index]
        start = event["time"]
        add_wait(start)
        use_window(event.get("window"))

        if event["kind"] == "text":
            group = [event]
            while index + 1 < len(events):
                following = events[index + 1]
                if (
                    following["kind"] != "text"
                    or following["time"] - group[-1]["time"] > 0.75
                    or not _same_window(following.get("window"), event.get("window"))
                ):
                    break
                index += 1
                group.append(following)
            interval = 0.05
            if len(group) > 1:
                interval = round(min(0.5, max(0.01, (group[-1]["time"] - start) / (len(group) - 1))), 2)
            steps.append({
                "type": "keyboard",
                "config": {
                    "mode": "text", "keys": [],
                    "string": "".join(item["text"] for item in group),
                    "hangul_typewrite": False, "interval": interval,
                },
            })
            previous_end = group[-1]["time"]
        elif event["kind"] == "hotkey":
            steps.append({
                "type": "keyboard",
                "config": {"mode": "hotkey", "keys": event["keys"], "string": "", "hangul_typewrite": False, "interval": 0.05},
            })
            previous_end = start
        elif event["kind"] == "click":
            coordinate(event["x"], event["y"], event.get("window"))
            duration = round(event.get("duration", 0), 2) if event.get("duration", 0) >= 0.35 else 0
            config = {"button": event["button"], "duration": duration}
            if event["button"] == "double":
                config["interval"] = round(event.get("interval", 0.1), 2)
            steps.append({"type": "mouse_click", "config": config})
            previous_end = event.get("end_time", start + event.get("duration", 0))
        elif event["kind"] == "drag":
            coordinate(event["start_x"], event["start_y"], event.get("window"))
            steps.append({"type": "mouse_move", "config": {"duration": 0}})
            coordinate(event["x"], event["y"], event.get("window"))
            steps.append({"type": "mouse_drag", "config": {
                "button": event.get("button", "left"),
                "duration": round(max(0.05, event["duration"]), 2),
            }})
            previous_end = start + event["duration"]
        elif event["kind"] == "scroll":
            coordinate(event["x"], event["y"], event.get("window"))
            steps.append({"type": "mouse_move", "config": {"duration": 0}})
            steps.append({"type": "mouse_scroll", "config": {
                "axis": event.get("axis", "vertical"),
                "amount": int(event["amount"]),
            }})
            end = event.get("end_time", start)
            duration = end - start
            if duration >= WAIT_THRESHOLD:
                steps.append({"type": "wait", "config": {"ms": max(1, round(duration * 100) * 10)}})
            previous_end = end
        index += 1
    return steps


class Recorder:
    def __init__(self):
        self.running = False
        self.active = False
        self.callback = None
        self.events = []
        self.started_at = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._timer = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._downs = {}
        self._modifiers = set()
        self._pressed = set()

    def _notify(self, phase, **payload):
        if self.callback:
            self.callback({"phase": phase, **payload})

    def start(self, delay=3):
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.active = False
            self.events = []
            self.started_at = None
            self._downs.clear()
            self._modifiers.clear()
            self._pressed.clear()
            self._cancel.clear()
        self._notify("countdown", seconds=delay)
        threading.Thread(target=self._begin_after_delay, args=(delay,), daemon=True).start()
        return True

    def _begin_after_delay(self, delay):
        if self._cancel.wait(max(0, delay)):
            return
        with self._lock:
            if not self.running:
                return
            self.active = True
            self.started_at = time.monotonic()
        self._mouse_listener = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
        self._keyboard_listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mouse_listener.start()
        self._keyboard_listener.start()
        self._timer = threading.Timer(MAX_SECONDS, self.stop)
        self._timer.daemon = True
        self._timer.start()
        self._notify("started")

    def _append(self, event):
        should_stop = False
        with self._lock:
            if not self.active:
                return
            self.events.append(event)
            should_stop = len(self.events) >= MAX_EVENTS
        if should_stop:
            threading.Thread(target=self.stop, daemon=True).start()

    def _on_click(self, x, y, button, pressed):
        name = getattr(button, "name", str(button).split(".")[-1])
        now = time.monotonic()
        if pressed:
            self._downs[name] = (now, int(x), int(y), _window_at(x, y))
            return
        down = self._downs.pop(name, None)
        if not down:
            return
        started, start_x, start_y, window = down
        duration = max(0, now - started)
        if math.hypot(x - start_x, y - start_y) > 5:
            self._append({
                "kind": "drag", "time": started, "duration": duration,
                "button": name, "start_x": start_x, "start_y": start_y,
                "x": int(x), "y": int(y), "window": window,
            })
        else:
            self._append({
                "kind": "click", "time": started, "duration": duration,
                "button": name, "x": int(x), "y": int(y), "window": window,
            })

    def _on_scroll(self, x, y, dx, dy):
        amount = dy or dx
        self._append({
            "kind": "scroll", "time": time.monotonic(), "amount": int(amount),
            "axis": "vertical" if dy else "horizontal",
            "x": int(x), "y": int(y), "window": _window_at(x, y),
        })

    def _on_press(self, key):
        name = _key_name(key)
        if name == get_setting("record_stop_key"):
            threading.Thread(target=self.stop, daemon=True).start()
            return False
        if not name:
            return
        if name in MODIFIERS:
            self._modifiers.add(name)
            return
        if name in self._pressed:
            return
        self._pressed.add(name)
        now = time.monotonic()
        window = _foreground_window()
        char = getattr(key, "char", None)
        command_modifiers = self._modifiers.intersection({"ctrl", "alt", "win"})
        if char and not command_modifiers:
            self._append({"kind": "text", "time": now, "text": char, "window": window})
        elif name == "space" and not command_modifiers:
            self._append({"kind": "text", "time": now, "text": " ", "window": window})
        else:
            keys = [modifier for modifier in MODIFIER_ORDER if modifier in self._modifiers]
            keys.append(name)
            self._append({"kind": "hotkey", "time": now, "keys": keys, "window": window})

    def _on_release(self, key):
        name = _key_name(key)
        self._pressed.discard(name)
        self._modifiers.discard(name)

    def stop(self, drop_last_click=False):
        with self._lock:
            if not self.running:
                return False
            was_active = self.active
            self.running = False
            self.active = False
            events = list(self.events)
            started_at = self.started_at
        if (
            drop_last_click and events and events[-1]["kind"] == "click"
            and time.monotonic() - events[-1]["time"] < 1
        ):
            events.pop()
        self._cancel.set()
        if self._timer:
            self._timer.cancel()
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        if not was_active:
            self._notify("cancelled")
            return True
        duration = max(0, time.monotonic() - started_at) if started_at else 0
        steps = events_to_steps(events)
        self._notify("complete", steps=steps, event_count=len(events), duration=round(duration, 1))
        return True

    def close(self):
        self.callback = None
        self.stop()
