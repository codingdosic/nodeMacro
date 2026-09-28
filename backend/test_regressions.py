import unittest
from unittest.mock import patch

from PIL import Image

from backend.engine import state
from backend.engine.executor import Executor
from backend.nodes.action_nodes import CoordNode, ImageNode, WaitNode, WindowNode


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
        executor._run_loop(node, {node.node_id: node}, [])
        self.assertFalse(executor.running)

    def test_start_requires_start_node(self):
        executor = Executor.__new__(Executor)
        executor.running = False
        with patch.object(state, "update_status"):
            self.assertFalse(executor.start({}, []))


if __name__ == "__main__":
    unittest.main()
