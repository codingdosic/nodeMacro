import unittest

from backend.engine.recorder import _is_transient_window, events_to_steps


class RecorderTests(unittest.TestCase):
    def test_transient_popups_are_not_treated_as_windows(self):
        self.assertTrue(_is_transient_window("#32768", 0))
        self.assertTrue(_is_transient_window("Anything", 0x08000000))
        self.assertFalse(_is_transient_window("Chrome_WidgetWin_1", 0))

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


if __name__ == "__main__":
    unittest.main()
