import os
import struct
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from machine_file_meta import collect_machine_file_meta, find_machine_thumbnail_source, find_thumbnail_source, resolve_machine_file_path


class MachineFileMetaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

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

    def test_resolves_indecal_ready_rip_from_tem_folder(self):
        existing = {r"\\InDecal\D\Tem\Bevang1.prn".lower()}

        resolved = resolve_machine_file_path(
            "InDecal",
            "Bevang1.prn",
            "Bevang1.prn",
            "2026-07-15 14:45:15",
            exists_func=lambda path: path.lower() in existing,
        )

        self.assertEqual(resolved, r"\\InDecal\D\Tem\Bevang1.prn")

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

    def test_resolves_inbat_e_drive_path_to_share(self):
        existing = {r"\\InBat\E\2026-07-13\New Folder\ut_160x230.prt".lower()}

        resolved = resolve_machine_file_path(
            "InBat",
            r"E:\2026-07-13\New Folder\ut_160x230.prt",
            "ut_160x230.prt",
            "2026-07-13 11:19:56",
            exists_func=lambda path: path.lower() in existing,
        )

        self.assertEqual(resolved, r"\\InBat\E\2026-07-13\New Folder\ut_160x230.prt")

    def test_finds_inbat_printmon_preview_cache(self):
        preview_path = r"\\InBat\PrintMon USB3.0 510 508GS 1020\Preview\D__2026-07-14_New Folder_yte_600x240_prt.bmp"
        found = find_machine_thumbnail_source(
            "InBat",
            r"\\InBat\D\2026-07-14\New Folder\yte_600x240.prt",
            exists_func=lambda path: path.lower() == preview_path.lower(),
        )

        self.assertEqual(found, preview_path)

    def test_prt_thumbnail_prefers_original_image_before_direct_bmp(self):
        prt_path = os.path.join(self.temp_dir.name, "TTP_800x130.prt")
        tif_path = os.path.join(self.temp_dir.name, "TTP_800x130.tif")
        bmp_path = prt_path + ".bmp"
        for path in (prt_path, tif_path, bmp_path):
            with open(path, "wb") as handle:
                handle.write(b"x")

        self.assertEqual(find_thumbnail_source(prt_path), tif_path)

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

    def test_collects_indecal_prn_dimensions_from_rip_header(self):
        prn_path = os.path.join(self.temp_dir.name, "16~kl_105x212.prn")
        with open(prn_path, "wb") as handle:
            handle.write(struct.pack("<6I", 0x74667966, 360, 1800, 3728, 150252, 14884))

        meta = collect_machine_file_meta(prn_path)

        self.assertEqual(meta["source_kind"], "rip_file_header")
        self.assertEqual(meta["metadata_source"], prn_path)
        self.assertAlmostEqual(meta["width_cm"], 105.01, places=2)
        self.assertAlmostEqual(meta["height_cm"], 212.02, places=2)
        self.assertAlmostEqual(meta["area_m2"], 2.23, places=2)

    def test_prt_header_overrides_design_image_orientation(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")
        tif_path = os.path.join(self.temp_dir.name, "yte_600x240.tif")
        prt_path = os.path.join(self.temp_dir.name, "yte_600x240.prt")
        Image.new("RGB", (6000, 2400), "white").save(tif_path, dpi=(25.4, 25.4))
        with open(prt_path, "wb") as handle:
            handle.write(struct.pack("<6I", 0x5555, 240, 540, 2836, 127564, 22682))

        meta = collect_machine_file_meta(prt_path)

        self.assertEqual(meta["source_kind"], "rip_file_header")
        self.assertEqual(meta["metadata_source"], prt_path)
        self.assertEqual(meta["design_metadata_source"], tif_path)
        self.assertAlmostEqual(meta["design_width_cm"], 600.0, places=1)
        self.assertAlmostEqual(meta["design_height_cm"], 240.0, places=1)
        self.assertAlmostEqual(meta["width_cm"], 240.05, places=2)
        self.assertAlmostEqual(meta["height_cm"], 600.02, places=2)


if __name__ == "__main__":
    unittest.main()
