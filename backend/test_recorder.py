import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.engine.recorder import Recorder, _is_transient_window, events_to_steps


class RecorderTests(unittest.TestCase):
    def test_transient_popups_are_not_treated_as_windows(self):
        self.assertTrue(_is_transient_window("#32768", 0))
        self.assertTrue(_is_transient_window("Anything", 0x08000000))
        self.assertTrue(_is_transient_window("Windows.UI.Core.CoreWindow", 0, "StartMenuExperienceHost.exe"))
        self.assertFalse(_is_transient_window("Chrome_WidgetWin_1", 0))

    def test_title_change_does_not_create_another_window_node(self):
        before = {"hwnd": 10, "title": "Untitled - Notepad", "process": "Notepad.exe", "class_name": "Notepad", "rect": [0, 0, 800, 600]}
        after = {**before, "title": "notes.txt - Notepad"}
        steps = events_to_steps([
            {"kind": "text", "time": 1.0, "text": "a", "window": before},
            {"kind": "text", "time": 1.1, "text": "b", "window": after},
        ])
        windows = [step for step in steps if step["type"] == "window"]
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["config"]["process"], "Notepad.exe")

    def test_moved_window_refreshes_relative_coordinate_origin(self):
        before = {"hwnd": 10, "title": "Chrome", "rect": [0, 0, 1000, 800]}
        after = {**before, "rect": [1920, 0, 2920, 800]}
        steps = events_to_steps([
            {"kind": "click", "time": 1.0, "duration": 0, "button": "left", "x": 10, "y": 10, "window": before},
            {"kind": "click", "time": 2.0, "duration": 0, "button": "left", "x": 1930, "y": 10, "window": after},
        ])
        self.assertEqual(sum(step["type"] == "window" for step in steps), 2)
        self.assertEqual([step for step in steps if step["type"] == "click"][-1]["config"]["x"], 10)

    def test_events_become_compact_timed_steps(self):
        window = {"title": "Notepad", "rect": [100, 200, 900, 800]}
        steps = events_to_steps([
            {"kind": "click", "time": 1.0, "duration": 0.1, "button": "left", "x": 150, "y": 250, "window": window},
            {"kind": "click", "time": 1.2, "duration": 0.1, "button": "left", "x": 151, "y": 251, "window": window},
            {"kind": "text", "time": 2.0, "text": "h", "window": window},
            {"kind": "text", "time": 2.1, "text": "i", "window": window},
        ])
        self.assertEqual([step["type"] for step in steps], ["start", "window", "click", "mouse_click", "wait", "keyboard"])
        self.assertEqual(steps[2]["config"], {"x": 50, "y": 50, "relative_to_window": True})
        self.assertEqual(steps[3]["config"]["button"], "double")
        self.assertEqual(steps[3]["config"]["interval"], 0.2)
        self.assertEqual(steps[-1]["config"]["string"], "hi")

    def test_scroll_keeps_steps_and_axis(self):
        steps = events_to_steps([
            {"kind": "scroll", "time": 1.0, "amount": -3, "axis": "vertical", "x": 10, "y": 20},
            {"kind": "scroll", "time": 1.2, "amount": -5, "axis": "vertical", "x": 10, "y": 20},
        ])
        scroll = next(step for step in steps if step["type"] == "mouse_scroll")
        self.assertEqual(scroll["config"], {"axis": "vertical", "amount": -8})

    def test_moves_and_hover_become_one_embedded_sequence(self):
        steps = events_to_steps([
            {"kind": "move", "time": 1.0, "x": 10, "y": 20},
            {"kind": "move", "time": 1.05, "x": 30, "y": 40},
            {"kind": "move", "time": 1.65, "x": 50, "y": 60},
        ])
        sequence = next(step for step in steps if step["type"] == "mouse_sequence")
        self.assertEqual(sum(item["op"] == "move" for item in sequence["config"]["steps"]), 3)
        self.assertTrue(any(item["op"] == "wait" for item in sequence["config"]["steps"]))

    @patch("backend.engine.recorder._foreground_window", return_value=None)
    def test_modifier_pressed_alone_is_recorded(self, _foreground):
        recorder = Recorder()
        recorder.active = True
        key = SimpleNamespace(name="cmd", char=None)
        recorder._on_press(key)
        recorder._on_release(key)
        self.assertEqual(recorder.events[0]["keys"], ["win"])

    @patch("backend.engine.recorder._foreground_window", return_value=None)
    def test_hangul_key_is_recorded(self, _foreground):
        recorder = Recorder()
        recorder.active = True
        recorder._on_press(SimpleNamespace(name=None, char=None, vk=0x15))
        self.assertEqual(recorder.events[0]["keys"], ["hangul"])

    @patch("backend.engine.recorder.time.monotonic", side_effect=[1.0, 1.01, 1.5])
    def test_hover_endpoint_is_flushed_before_moving_again(self, _clock):
        recorder = Recorder()
        recorder.active = True
        recorder._on_move(0, 0)
        recorder._on_move(5, 0)
        recorder._on_move(20, 0)
        self.assertEqual([(event["x"], event["y"]) for event in recorder.events], [(0, 0), (5, 0), (20, 0)])


if __name__ == "__main__":
    unittest.main()
