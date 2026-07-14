import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from machine_file_meta import resolve_machine_file_path


class MachineFileMetaTests(unittest.TestCase):
    def test_resolves_indecal_bare_queue_file_to_dated_new_folder(self):
        existing = {r"\\InDecal\D\2026-07-13\New Folder\8~loi_121x23.prn".lower()}

        resolved = resolve_machine_file_path(
            "InDecal",
            "8~loi_121x23.prn",
            "8~loi_121x23.prn",
            "2026-07-13 10:31:38",
            exists_func=lambda path: path.lower() in existing,
        )

        self.assertEqual(resolved, r"\\InDecal\D\2026-07-13\New Folder\8~loi_121x23.prn")

    def test_resolves_inbat_d_drive_path_to_share(self):
        existing = {r"\\InBat\D\2026-07-13\New Folder\ut_160x230.prt".lower()}

        resolved = resolve_machine_file_path(
            "InBat",
            r"D:\2026-07-13\New Folder\ut_160x230.prt",
            "ut_160x230.prt",
            "2026-07-13 11:19:56",
            exists_func=lambda path: path.lower() in existing,
        )

        self.assertEqual(resolved, r"\\InBat\D\2026-07-13\New Folder\ut_160x230.prt")

    def test_resolves_cnc_file_from_day_root_into_new_folder(self):
        existing = {r"\\CNC\CNC\CNC\2026-07-13\New Folder\f8_120x67.tap".lower()}

        resolved = resolve_machine_file_path(
            "CNC",
            r"D:\CNC\2026-07-13\f8_120x67.tap",
            "f8_120x67.tap",
            "2026-07-13 11:30:49",
            exists_func=lambda path: path.lower() in existing,
        )

        self.assertEqual(resolved, r"\\CNC\CNC\CNC\2026-07-13\New Folder\f8_120x67.tap")


if __name__ == "__main__":
    unittest.main()
