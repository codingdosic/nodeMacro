import ctypes
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from backend.engine import state
from backend.engine.executor import Executor
from backend.nodes.action_nodes import (
    CoordNode, ImageNode, KeyboardNode, LaunchNode, MouseClickNode, MouseDragNode,
    MouseScrollNode, MouseSequenceNode, WaitNode, WindowNode, _Input, _send_mouse_move,
)


class RegressionTests(unittest.TestCase):
    def tearDown(self):
        state.stop_event.clear()

    def test_missing_image_clears_previous_target(self):
        macro_state = {"target_pos": (10, 20)}
        ImageNode("image", {}).execute(macro_state)
        self.assertNotIn("target_pos", macro_state)

    def test_image_search_uses_virtual_screen_coordinates(self):
        node = ImageNode(
            "image",
            {"image_path": "needle.png", "wait_time": 0, "search_region": [-1800, 100, 500, 400]},
        )
        screen = Image.new("RGB", (3840, 1080))
        with patch("backend.engine.capture._virtual_screen_rect", return_value=(-1920, 0, 3840, 1080)), \
             patch("backend.engine.capture._grab_all_screens", return_value=screen), \
             patch("backend.nodes.action_nodes.pyautogui.locate", return_value=(20, 30, 10, 10)):
            self.assertEqual(node._find_image(), (-1775, 135))

    def test_stop_interrupts_wait(self):
        state.stop_event.set()
        self.assertEqual(WaitNode("wait", {"ms": 60_000}).execute({}), "output_pin")

    def test_wait_reports_topbar_countdown(self):
        with patch.object(state, "update_status") as update_status:
            WaitNode("wait", {"ms": 10}).execute({})
        update_status.assert_called_with(
            "다음 동작까지 1초",
            "status_next_action",
            seconds=1,
        )

    @patch("backend.nodes.action_nodes.pyautogui.click")
    def test_middle_click(self, click):
        MouseClickNode("mouse", {"button": "middle"}).execute({"target_pos": (10, 20)})
        click.assert_called_once_with(10, 20, button="middle")

    @patch("backend.nodes.action_nodes.pyautogui.scroll")
    def test_windows_scroll_uses_wheel_delta(self, scroll):
        with patch("backend.nodes.action_nodes.os.name", "nt"):
            MouseScrollNode("scroll", {"amount": -8}).execute({})
        scroll.assert_called_once_with(-960)

    @patch("backend.nodes.action_nodes._send_mouse_move")
    def test_mouse_sequence_replays_embedded_moves(self, move_to):
        MouseSequenceNode("path", {"steps": [
            {"op": "move", "x": 10, "y": 20, "duration_ms": 50},
            {"op": "wait", "ms": 0},
            {"op": "move", "x": 30, "y": 40, "duration_ms": 100},
        ]}).execute({})
        self.assertEqual(move_to.call_count, 2)
        move_to.assert_any_call(10.0, 20.0)

    @patch("backend.nodes.action_nodes._send_mouse_move")
    def test_mouse_sequence_accepts_one_millisecond_move(self, move_to):
        MouseSequenceNode("path", {"steps": [
            {"op": "move", "x": 10, "y": 20, "duration_ms": 1},
        ]}).execute({})
        move_to.assert_called_once_with(10.0, 20.0)

    def test_send_input_uses_virtual_desktop_coordinates(self):
        captured = {}

        def send_input(_count, pointer, _size):
            event = ctypes.cast(pointer, ctypes.POINTER(_Input)).contents
            captured["move"] = (event.mi.dx, event.mi.dy, event.mi.dwFlags)
            return 1

        metrics = {76: -1920, 77: 0, 78: 3840, 79: 1080}
        user32 = SimpleNamespace(
            GetSystemMetrics=lambda key: metrics[key],
            SendInput=send_input,
        )
        with patch("backend.nodes.action_nodes.ctypes.windll.user32", user32):
            _send_mouse_move(-1920, 0)
        self.assertEqual(captured["move"], (0, 0, 0x0001 | 0x4000 | 0x8000))

    @patch.object(state.stop_event, "wait", return_value=False)
    @patch("backend.nodes.action_nodes._send_mouse_move")
    def test_mouse_sequence_refreshes_recorded_hover(self, move_to, _wait):
        MouseSequenceNode("path", {"steps": [
            {"op": "move", "x": 10, "y": 20, "duration_ms": 50},
            {"op": "wait", "ms": 500},
        ]}).execute({})
        self.assertEqual(
            [call.args for call in move_to.call_args_list],
            [(10.0, 20.0), (11.0, 20.0), (10.0, 20.0)],
        )

    @patch("backend.nodes.action_nodes.pyautogui.hotkey")
    def test_hangul_key_is_replayed(self, hotkey):
        KeyboardNode("key", {"mode": "hotkey", "keys": ["hangul"]}).execute({})
        hotkey.assert_called_once_with("hangul")

    @patch("backend.nodes.action_nodes.pyautogui.dragTo")
    @patch("backend.nodes.action_nodes.pyautogui.position", return_value=(0, 0))
    def test_drag_preserves_button(self, _position, drag_to):
        MouseDragNode("drag", {"button": "right", "duration": 0.4}).execute({"target_pos": (10, 20)})
        drag_to.assert_called_once_with(10, 20, duration=0.4, button="right")

    @patch("backend.nodes.action_nodes._find_window", return_value=("Chrome", (1920, 0, 2920, 800)))
    @patch("backend.nodes.action_nodes.pyautogui.dragTo")
    @patch("backend.nodes.action_nodes.pyautogui.position", return_value=(10, 10))
    def test_drag_refreshes_window_relative_origin(self, _position, _drag_to, _find_window):
        macro_state = {
            "target_pos": (2000, 20),
            "window_title": "Chrome",
            "window_rect": (0, 0, 1000, 800),
            "window_process": "chrome.exe",
            "window_class": "Chrome_WidgetWin_1",
        }
        MouseDragNode("drag", {"duration": 0}).execute(macro_state)
        self.assertEqual(macro_state["window_rect"], (1920, 0, 2920, 800))

    @patch("backend.nodes.action_nodes._find_window")
    def test_window_relative_coordinate(self, find_window):
        find_window.return_value = ("Calculator", (200, 300, 1000, 900))
        macro_state = {}
        WindowNode("window", {"title": "Calc"}).execute(macro_state)
        CoordNode(
            "coord",
            {"x": 10, "y": 20, "relative_to_window": True},
        ).execute(macro_state)
        self.assertEqual(macro_state["target_pos"], (210, 320))

    @patch("backend.nodes.action_nodes.os.startfile")
    def test_launch_expands_environment_variable(self, startfile):
        with patch.dict(os.environ, {"D5_TEST_APP": r"C:\Tools\demo.exe"}):
            LaunchNode("launch", {"path": r"%D5_TEST_APP%", "wait_after": 0}).execute({})
        startfile.assert_called_once_with(r"C:\Tools\demo.exe")

    @patch("backend.nodes.action_nodes._find_window")
    def test_window_waits_until_found(self, find_window):
        find_window.side_effect = [None, ("Calculator", (1, 2, 3, 4))]
        macro_state = {}
        WindowNode("window", {"title": "Calc", "timeout": 1, "poll_interval": 0.05}).execute(macro_state)
        self.assertEqual(macro_state["window_rect"], (1, 2, 3, 4))
        self.assertEqual(find_window.call_count, 2)

    @patch("backend.nodes.action_nodes._find_window", return_value=None)
    def test_window_timeout_is_an_error(self, _find_window):
        with self.assertRaisesRegex(RuntimeError, "창을 찾을 수 없습니다"):
            WindowNode("window", {"title": "Missing", "timeout": 0}).execute({})

    @patch("backend.nodes.action_nodes._find_window")
    def test_window_wait_honors_stop(self, find_window):
        state.stop_event.set()
        self.assertEqual(WindowNode("window", {"title": "Anything"}).execute({}), "output_pin")
        find_window.assert_not_called()

    def test_executor_recovers_after_node_error(self):
        class BrokenNode:
            node_id = "broken"
            node_type = "start"
            label = "broken"

            def reset(self):
                pass

            def execute(self, macro_state):
                raise RuntimeError("boom")

        executor = Executor.__new__(Executor)
        executor.running = True
        executor._stop_requested = False
        node = BrokenNode()
        with patch.object(state, "update_execution") as update_execution:
            executor._run_loop(node, {node.node_id: node}, [])
        self.assertFalse(executor.running)
        update_execution.assert_any_call(None, "finished")

    def test_start_requires_start_node(self):
        executor = Executor.__new__(Executor)
        executor.running = False
        with patch.object(state, "update_status"):
            self.assertFalse(executor.start({}, []))

    def test_executor_can_start_from_selected_node(self):
        class Node:
            node_type = "wait"

            def __init__(self, node_id):
                self.node_id = node_id

        executor = Executor.__new__(Executor)
        executor.running = False
        nodes = {"chosen": Node("chosen")}
        with patch("backend.engine.executor.threading.Thread") as thread:
            self.assertTrue(executor.start(nodes, [], "chosen"))
        self.assertIs(thread.call_args.kwargs["args"][0], nodes["chosen"])


if __name__ == "__main__":
    unittest.main()
