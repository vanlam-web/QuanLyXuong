import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _constant(source, name):
    match = re.search(rf'^{name}\s*=\s*"([^"]+)"', source, re.MULTILINE)
    assert match, f"{name} not found"
    return match.group(1)


class ReleaseVersionTests(unittest.TestCase):
    def test_workstation_client_release_version_is_2_1_1(self):
        source = _read("app/QuanLyXuong.py")
        self.assertEqual(_constant(source, "CLIENT_VERSION"), "V2.1.1_INDECAL_READY_RIP")

    def test_cnc_bridge_release_version_is_2_1_test(self):
        source = _read("app/cnc_legacy_bridge.py")
        self.assertEqual(_constant(source, "BRIDGE_VERSION"), "V2.1.0_TEST_CNC_BRIDGE")


if __name__ == "__main__":
    unittest.main()
