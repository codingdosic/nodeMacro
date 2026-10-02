import ctypes
import math
import os
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
    "shell_traywnd",
    "shell_secondarytraywnd",
    "progman",
    "workerw",
    "dv2controlhost",
}
SHELL_PROCESSES = {
    "searchapp.exe",
    "searchhost.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
}
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
MOVE_SAMPLE_INTERVAL = 0.05
MOVE_SAMPLE_DISTANCE = 12
HOVER_THRESHOLD = 0.25


def _is_transient_window(class_name, ex_style, process_name=""):
    class_key = str(class_name or "").casefold()
    process_key = str(process_name or "").casefold()
    return (
        class_key in TRANSIENT_WINDOW_CLASSES
        or bool(int(ex_style or 0) & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE))
        or process_key in SHELL_PROCESSES
    )


def _process_name(hwnd):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return pid.value, ""
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            return pid.value, os.path.basename(path.value)
        return pid.value, ""
    finally:
        kernel32.CloseHandle(handle)


def _window_info(hwnd):
    if sys.platform != "win32" or not hwnd:
        return None
    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
    class_name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_name, len(class_name))
    pid, process_name = _process_name(hwnd)
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    if _is_transient_window(class_name.value, user32.GetWindowLongPtrW(hwnd, -20), process_name):
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
        "hwnd": int(hwnd),
        "pid": int(pid),
        "process": process_name,
        "class_name": class_name.value,
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
    if getattr(key, "vk", None) == 0x15:  # VK_HANGUL / VK_KANA
        return "hangul"
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
    left_hwnd = (left or {}).get("hwnd")
    right_hwnd = (right or {}).get("hwnd")
    if left_hwnd and right_hwnd:
        return left_hwnd == right_hwnd
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
        same_window = _same_window(window, current_window)
        moved_or_resized = same_window and (window or {}).get("rect") != (current_window or {}).get("rect")
        if title and (not same_window or moved_or_resized):
            config = {"title": title, "timeout": 10, "poll_interval": 0.2, "activate": True}
            for key in ("process", "class_name"):
                if (window or {}).get(key):
                    config[key] = window[key]
            steps.append({
                "type": "window",
                "config": config,
            })
            current_window = window

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
        elif event["kind"] == "move":
            group = [event]
            while index + 1 < len(events) and events[index + 1]["kind"] == "move":
                index += 1
                group.append(events[index])
            sequence = []
            previous_move_time = None
            for item in group:
                duration_ms = round(MOVE_SAMPLE_INTERVAL * 1000)
                if previous_move_time is not None:
                    gap = item["time"] - previous_move_time
                    if gap >= HOVER_THRESHOLD:
                        wait_ms = max(1, round((gap - MOVE_SAMPLE_INTERVAL) * 1000))
                        sequence.append({"op": "wait", "ms": wait_ms})
                    else:
                        duration_ms = max(1, round(gap * 1000))
                sequence.append({
                    "op": "move", "x": int(item["x"]), "y": int(item["y"]),
                    "duration_ms": duration_ms,
                })
                previous_move_time = item["time"]
            steps.append({
                "type": "mouse_sequence",
                "config": {"coordinate_space": "screen", "steps": sequence},
            })
            previous_end = group[-1]["time"]
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
        self._modifier_downs = {}
        self._used_modifiers = set()
        self._last_move_at = 0.0
        self._last_move_pos = None
        self._pending_move = None

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
            self._modifier_downs.clear()
            self._used_modifiers.clear()
            self._last_move_at = 0.0
            self._last_move_pos = None
            self._pending_move = None
            self._cancel.clear()
        self._notify("countdown", seconds=delay)
        threading.Thread(target=self._begin_after_delay, args=(delay,), daemon=True).start()
        return True

    def _begin_after_delay(self, delay):
        deadline = time.monotonic() + max(0, delay)
        shown = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            seconds_left = max(1, math.ceil(remaining))
            if seconds_left != shown:
                self._notify("countdown", seconds=seconds_left)
                shown = seconds_left
            if self._cancel.wait(min(0.1, remaining)):
                return
        with self._lock:
            if not self.running:
                return
            self.active = True
            self.started_at = time.monotonic()
        self._mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
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
            self._flush_pending_move()
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
        self._flush_pending_move()
        amount = dy or dx
        self._append({
            "kind": "scroll", "time": time.monotonic(), "amount": int(amount),
            "axis": "vertical" if dy else "horizontal",
            "x": int(x), "y": int(y), "window": _window_at(x, y),
        })

    def _on_move(self, x, y):
        if self._downs:
            return
        now = time.monotonic()
        event = {"kind": "move", "time": now, "x": int(x), "y": int(y)}
        if self._pending_move and now - self._pending_move["time"] >= HOVER_THRESHOLD:
            self._flush_pending_move()
        previous = self._last_move_pos
        distance = math.hypot(x - previous[0], y - previous[1]) if previous else MOVE_SAMPLE_DISTANCE
        if now - self._last_move_at < MOVE_SAMPLE_INTERVAL and distance < MOVE_SAMPLE_DISTANCE:
            self._pending_move = event
            return
        self._append(event)
        self._last_move_at = now
        self._last_move_pos = (int(x), int(y))
        self._pending_move = None

    def _flush_pending_move(self):
        event = self._pending_move
        self._pending_move = None
        if not event:
            return
        point = (event["x"], event["y"])
        if point != self._last_move_pos:
            self._append(event)
            self._last_move_at = event["time"]
            self._last_move_pos = point

    def _on_press(self, key):
        self._flush_pending_move()
        name = _key_name(key)
        if name == get_setting("record_stop_key"):
            threading.Thread(target=self.stop, daemon=True).start()
            return False
        if not name:
            return
        if name in MODIFIERS:
            self._modifiers.add(name)
            self._modifier_downs[name] = (time.monotonic(), _foreground_window())
            self._used_modifiers.discard(name)
            return
        if name in self._pressed:
            return
        self._pressed.add(name)
        self._used_modifiers.update(self._modifiers)
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
        if name in MODIFIERS and name not in self._used_modifiers:
            started, window = self._modifier_downs.get(name, (time.monotonic(), _foreground_window()))
            self._append({"kind": "hotkey", "time": started, "keys": [name], "window": window})
        self._modifier_downs.pop(name, None)
        self._used_modifiers.discard(name)
        self._modifiers.discard(name)

    def stop(self, drop_last_click=False):
        self._flush_pending_move()
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
