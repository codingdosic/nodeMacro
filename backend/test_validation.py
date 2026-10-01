import unittest

from backend.nodes.action_nodes import ImageNode, LaunchNode, MouseClickNode, StartNode, WaitNode
from backend.validation import validate_macro


NODE_MAP = {
    "start": StartNode,
    "launch": LaunchNode,
    "wait": WaitNode,
    "image": ImageNode,
    "mouse_click": MouseClickNode,
}


class ValidationTests(unittest.TestCase):
    def test_valid_linear_macro_has_no_issues(self):
        nodes = {
            "start": {"type": "start", "config": {}},
            "wait": {"type": "wait", "config": {"ms": 10}},
        }
        links = [{"source": "start", "target": "wait"}]
        self.assertEqual(validate_macro(nodes, links, NODE_MAP), [])

    def test_invalid_image_and_number_are_errors(self):
        nodes = {
            "start": {"type": "start", "config": {}},
            "image": {"type": "image", "config": {"threshold": 2}},
        }
        links = [{"source": "start", "target": "image"}]
        codes = {issue["code"] for issue in validate_macro(nodes, links, NODE_MAP)}
        self.assertIn("number_max:threshold", codes)
        self.assertIn("image_required", codes)

    def test_unreachable_and_missing_position_are_warnings(self):
        nodes = {
            "start": {"type": "start", "config": {}},
            "wait": {"type": "wait", "config": {}},
            "mouse": {"type": "mouse_click", "config": {}},
        }
        links = [{"source": "start", "target": "wait"}]
        issues = validate_macro(nodes, links, NODE_MAP)
        warning_codes = {issue["code"] for issue in issues if issue["level"] == "warning"}
        self.assertIn("unreachable", warning_codes)
        self.assertIn("missing_position", warning_codes)

    def test_missing_launch_target_is_an_error(self):
        nodes = {
            "start": {"type": "start", "config": {}},
            "launch": {"type": "launch", "config": {"path": ""}},
        }
        links = [{"source": "start", "target": "launch"}]
        codes = {issue["code"] for issue in validate_macro(nodes, links, NODE_MAP)}
        self.assertIn("launch_path", codes)


if __name__ == "__main__":
    unittest.main()
