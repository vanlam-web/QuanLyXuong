import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HEALTH_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "Test-QuanLyXuongHealth.ps1")


class RuntimeHealthScriptTests(unittest.TestCase):
    def test_healthcheck_contains_duplicate_process_gate(self):
        with open(HEALTH_SCRIPT, "r", encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("Test-ProcessCountAtMostOne", script)
        self.assertIn("Duplicate process server_Local", script)
        self.assertIn("Duplicate process Dashboard_Local", script)
        self.assertIn("Duplicate process cnc_legacy_bridge", script)
        self.assertIn("Process server duplicate guard", script)
        self.assertIn("Process Dashboard duplicate guard", script)
        self.assertIn("Process CNC bridge duplicate guard", script)


if __name__ == "__main__":
    unittest.main()
