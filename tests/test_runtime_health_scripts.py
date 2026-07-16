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

    def test_start_runtime_uses_strict_stop_and_verify_single_instance(self):
        path = os.path.join(PROJECT_ROOT, "scripts", "Start-V2Runtime.ps1")
        with open(path, "r", encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("Stop-Process -Id $process.Id -Force -ErrorAction Stop", script)
        self.assertIn("Wait-Process -Id $process.Id -Timeout 10 -ErrorAction Stop", script)
        self.assertIn('Assert-SingleProcess "server_Local"', script)
        self.assertIn('Assert-SingleProcess "Dashboard_Local"', script)
        self.assertIn('Assert-SingleProcess "cnc_legacy_bridge"', script)


if __name__ == "__main__":
    unittest.main()
