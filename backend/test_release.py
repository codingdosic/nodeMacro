import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_temp = tempfile.TemporaryDirectory()
os.environ["D5MACRO_DATA_DIR"] = str(Path(_temp.name) / "data")
os.environ["D5MACRO_SCRIPTS_DIR"] = str(Path(_temp.name) / "scripts")

from fastapi.testclient import TestClient

from backend.config import SCRIPT_FORMAT, SCRIPT_SCHEMA_VERSION, SESSION_TOKEN, SCRIPTS_DIR
from backend.main import app


class ReleaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:8000")

    def authorized(self):
        self.client.cookies.set("d5_session", SESSION_TOKEN)
        return {"Origin": "http://127.0.0.1:8000"}

    def test_api_requires_local_session(self):
        self.assertEqual(self.client.get("/api/nodes/types").status_code, 401)
        response = self.client.get("/api/nodes/types", headers=self.authorized())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(
            self.client.get("/api/nodes/types", headers={"Origin": "https://example.com"}).status_code,
            403,
        )

    def test_saved_script_has_versioned_format(self):
        response = self.client.post(
            "/api/scripts/save",
            headers=self.authorized(),
            json={"name": "release-test", "macro_data": {"nodes": [], "edges": []}},
        )
        self.assertEqual(response.status_code, 200)
        saved = json.loads((SCRIPTS_DIR / "release-test" / "release-test.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["format"], SCRIPT_FORMAT)
        self.assertEqual(saved["schema_version"], SCRIPT_SCHEMA_VERSION)

    @patch("backend.main.os.startfile")
    def test_open_scripts_folder_uses_fixed_directory(self, startfile):
        response = self.client.post("/api/scripts/open-folder", headers=self.authorized())
        self.assertEqual(response.status_code, 200)
        startfile.assert_called_once_with(str(SCRIPTS_DIR))


if __name__ == "__main__":
    unittest.main()
