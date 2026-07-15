import os
import sys
import tempfile
import time
import unittest
import os
import sqlite3
from datetime import date

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import QuanLyXuong
from qlx_outbox import EventOutbox


class QuanLyXuongScanTests(unittest.TestCase):
    def setUp(self):
        self.original_root = QuanLyXuong.ROOT
        self.original_machine = QuanLyXuong.MACHINE_NAME
        self.original_state_file = QuanLyXuong.STATE_FILE
        self.original_base_storage = QuanLyXuong.BASE_STORAGE
        self.original_processed_set = QuanLyXuong.processed_set
        self.original_recent_moved = QuanLyXuong.recent_moved
        self.original_processed_prt = QuanLyXuong.processed_prt
        self.original_processed_prn = QuanLyXuong.processed_prn
        self.original_prn_tracking = QuanLyXuong.prn_tracking
        self.original_process_event = QuanLyXuong.process_event
        self.original_outbox = QuanLyXuong.OUTBOX
        self.original_log_system = QuanLyXuong.log_system
        self.original_requests_post = QuanLyXuong.requests.post
        self.temp_dir = tempfile.TemporaryDirectory()
        self.day = date.today().strftime("%Y-%m-%d")
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.restore_globals)

    def restore_globals(self):
        QuanLyXuong.ROOT = self.original_root
        QuanLyXuong.MACHINE_NAME = self.original_machine
        QuanLyXuong.STATE_FILE = self.original_state_file
        QuanLyXuong.BASE_STORAGE = self.original_base_storage
        QuanLyXuong.processed_set = self.original_processed_set
        QuanLyXuong.recent_moved = self.original_recent_moved
        QuanLyXuong.processed_prt = self.original_processed_prt
        QuanLyXuong.processed_prn = self.original_processed_prn
        QuanLyXuong.prn_tracking = self.original_prn_tracking
        QuanLyXuong.process_event = self.original_process_event
        QuanLyXuong.OUTBOX = self.original_outbox
        QuanLyXuong.log_system = self.original_log_system
        QuanLyXuong.requests.post = self.original_requests_post

    def make_file(self, *parts):
        file_path = os.path.join(self.temp_dir.name, *parts)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as handle:
            handle.write(b"test")
        return file_path.lower()

    def test_inbat_scan_collects_exports_and_rip_files(self):
        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "inbat"
        day = self.day
        export_path = self.make_file(day, "job.tif")
        rip_path = self.make_file(day, "New Folder", "job.prn")
        ignored_path = self.make_file(day, "New Folder", "note.txt")

        scan = QuanLyXuong.scan_day(day)

        self.assertIn(export_path, scan)
        self.assertIn(rip_path, scan)
        self.assertNotIn(ignored_path, scan)

    def test_indecal_scan_collects_nested_rip_files(self):
        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "indecal"
        day = self.day
        export_path = self.make_file(day, "nested", "decal.jpg")
        rip_path = self.make_file(day, "nested", "New Folder", "decal~meta.prn")

        scan = QuanLyXuong.scan_day(day)

        self.assertIn(export_path, scan)
        self.assertIn(rip_path, scan)

    def test_indecal_print_log_resolves_ready_rip_from_tem_folder(self):
        class FakeOutbox:
            def __init__(self):
                self.payloads = []

            def enqueue(self, payload):
                self.payloads.append(payload)
                return "evt-ready-rip"

        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "indecal"
        QuanLyXuong.MACHINE_DISPLAY = "InDecal"
        fake = FakeOutbox()
        QuanLyXuong.OUTBOX = fake
        QuanLyXuong.log_system = lambda *args, **kwargs: None
        ready_rip = self.make_file("Tem", "Bevang1.prn")

        QuanLyXuong.process_event("Bevang1.prn", "PRINTING")

        self.assertEqual(fake.payloads[0]["path"].lower(), ready_rip)

    def test_cnc_scan_collects_root_and_new_folder_cut_files(self):
        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "cnc"
        day = self.day
        root_cut_path = self.make_file(day, "part.tap")
        done_cut_path = self.make_file(day, "New Folder", "part.nc")
        ignored_path = self.make_file(day, "image.jpg")

        scan = QuanLyXuong.scan_day(day)

        self.assertIn(root_cut_path, scan)
        self.assertIn(done_cut_path, scan)
        self.assertNotIn(ignored_path, scan)

    def test_scan_once_emits_export_and_delete_events(self):
        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "inbat"
        QuanLyXuong.STATE_FILE = os.path.join(self.temp_dir.name, "state.json")
        QuanLyXuong.processed_set = set()
        QuanLyXuong.recent_moved = {}
        QuanLyXuong.processed_prt = {}
        QuanLyXuong.processed_prn = set()
        captured = []
        QuanLyXuong.process_event = lambda path, event_type, **kwargs: captured.append((event_type, path))

        day = self.day
        export_path = self.make_file(day, "job.tif")
        cur_date, last_curr = QuanLyXuong.run_universal_scan_once(day, set())
        os.remove(export_path)
        cur_date, last_curr = QuanLyXuong.run_universal_scan_once(cur_date, last_curr)

        self.assertEqual(captured[0], ("EXPORT", export_path))
        self.assertEqual(captured[1], ("DELETE", export_path))

    def test_sweep_old_files_emits_explicit_rollover_before_new_day_row(self):
        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "cnc"
        QuanLyXuong.processed_set = set()
        QuanLyXuong.recent_moved = {}
        captured = []

        def capture_event(path, event_type, **kwargs):
            captured.append((event_type, path, kwargs))

        QuanLyXuong.process_event = capture_event
        old_path = self.make_file("2026-07-14", "loi_f8_120x29.tap")

        QuanLyXuong.sweep_old_files_to_today()

        today = date.today().strftime("%Y-%m-%d")
        new_path = os.path.join(self.temp_dir.name, today, "loi_f8_120x29_Ngay14.tap").lower()
        self.assertTrue(os.path.exists(new_path))
        self.assertEqual([event[0] for event in captured], ["ROLLOVER", "WRONG_DAY"])
        self.assertEqual(captured[0][1].lower(), old_path)
        self.assertEqual(captured[0][2]["machine_meta_extra"]["rollover_target_path"].lower(), new_path)
        self.assertEqual(captured[1][1].lower(), new_path)

    def test_indecal_scan_once_emits_rip_only_after_meta_rename(self):
        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "indecal"
        QuanLyXuong.STATE_FILE = os.path.join(self.temp_dir.name, "state.json")
        QuanLyXuong.processed_set = set()
        QuanLyXuong.recent_moved = {}
        QuanLyXuong.processed_prt = {}
        QuanLyXuong.processed_prn = set()
        captured = []
        QuanLyXuong.process_event = lambda path, event_type, **kwargs: captured.append((event_type, path))

        day = self.day
        plain_prn = self.make_file(day, "New Folder", "job.prn")
        cur_date, last_curr = QuanLyXuong.run_universal_scan_once(day, set())
        renamed_prn = os.path.join(os.path.dirname(plain_prn), "job~meta.prn").lower()
        QuanLyXuong.recent_moved[plain_prn] = time.time()
        os.replace(plain_prn, renamed_prn)
        cur_date, last_curr = QuanLyXuong.run_universal_scan_once(cur_date, last_curr)

        self.assertEqual(captured, [("RIP", renamed_prn)])
        self.assertNotIn(plain_prn, QuanLyXuong.processed_set)
        self.assertIn(renamed_prn, QuanLyXuong.processed_set)

    def test_scan_once_writes_event_to_real_outbox(self):
        QuanLyXuong.ROOT = self.temp_dir.name
        QuanLyXuong.MACHINE_NAME = "inbat"
        QuanLyXuong.STATE_FILE = os.path.join(self.temp_dir.name, "state.json")
        QuanLyXuong.processed_set = set()
        QuanLyXuong.recent_moved = {}
        QuanLyXuong.processed_prt = {}
        QuanLyXuong.processed_prn = set()
        QuanLyXuong.OUTBOX = EventOutbox(os.path.join(self.temp_dir.name, "agent_outbox_inbat.db"))
        QuanLyXuong.log_system = lambda *args, **kwargs: None

        day = self.day
        export_path = self.make_file(day, "job.tif")
        QuanLyXuong.run_universal_scan_once(day, set())

        events = QuanLyXuong.OUTBOX.next_pending()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["machine"], "inbat")
        self.assertEqual(events[0].payload["path"], export_path)
        self.assertEqual(events[0].payload["event_type"], "EXPORT")
        self.assertIn("idempotency_key", events[0].payload)


    def test_thumbnail_source_for_rip_file_can_use_parent_export_folder(self):
        export_path = self.make_file(self.day, "ut_260x230.tif")
        rip_path = self.make_file(self.day, "New Folder", "ut_260x230.prt")

        self.assertEqual(QuanLyXuong.find_thumbnail_source(rip_path), export_path)

    def test_thumbnail_source_for_indecal_numbered_rip_uses_name_after_queue_prefix(self):
        export_path = self.make_file(self.day, "hhhh_decal_62x62.tif")
        rip_path = self.make_file(self.day, "New Folder", "13~hhhh_decal_62x62.prn")

        self.assertEqual(QuanLyXuong.find_thumbnail_source(rip_path), export_path)

    def test_thumbnail_source_for_rip_prefers_original_image_before_generated_bmp(self):
        export_path = self.make_file(self.day, "balong_80x10.tif")
        rip_path = self.make_file(self.day, "New Folder", "9~balong_80x10.prn")
        self.make_file(self.day, "New Folder", "9~balong_80x10.prn.bmp")

        self.assertEqual(QuanLyXuong.find_thumbnail_source(rip_path), export_path)

    def test_thumbnail_source_for_rip_uses_generated_bmp_when_original_missing(self):
        rip_path = self.make_file(self.day, "New Folder", "9~balong_80x10.prn")
        bmp_path = self.make_file(self.day, "New Folder", "9~balong_80x10.prn.bmp")

        self.assertEqual(QuanLyXuong.find_thumbnail_source(rip_path), bmp_path)

    def test_collect_machine_file_meta_reads_tiff_dimensions(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")
        tif_path = os.path.join(self.temp_dir.name, self.day, "job_10x5.tif")
        os.makedirs(os.path.dirname(tif_path), exist_ok=True)
        Image.new("RGB", (1000, 500), "white").save(tif_path, dpi=(100, 100))

        meta = QuanLyXuong.collect_machine_file_meta(tif_path)

        self.assertEqual(meta["image_width_px"], 1000)
        self.assertEqual(meta["image_height_px"], 500)
        self.assertAlmostEqual(meta["dpi_x"], 100.0, places=1)
        self.assertAlmostEqual(meta["width_cm"], 25.4, places=1)

    def test_collect_machine_file_meta_uses_tiff_dimensions_when_preview_is_prn_bmp(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")
        day_dir = os.path.join(self.temp_dir.name, self.day)
        rip_dir = os.path.join(day_dir, "New Folder")
        os.makedirs(rip_dir, exist_ok=True)
        tif_path = os.path.join(day_dir, "job_10x5.tif")
        prn_path = os.path.join(rip_dir, "9~job_10x5.prn")
        bmp_path = prn_path + ".bmp"
        Image.new("RGB", (1000, 500), "white").save(tif_path, dpi=(100, 100))
        Image.new("RGB", (100, 50), "white").save(bmp_path, dpi=(1000, 1000))
        with open(prn_path, "wb") as handle:
            handle.write(b"rip")

        meta = QuanLyXuong.collect_machine_file_meta(prn_path, bmp_path)

        self.assertEqual(meta["metadata_source"], tif_path)
        self.assertEqual(meta["preview_source"], bmp_path)
        self.assertAlmostEqual(meta["width_cm"], 25.4, places=1)
        self.assertEqual(meta["source_kind"], "image")

    def test_indecal_log_parser_detects_chinese_done_and_progress(self):
        state = {}
        lines = [
            "启动任务：10~tho_119x191.prn",
            "pInitParam->nTotalPrintPass=342",
            "nCurPassIndex=341: nFireStart=40674",
            "打印完成.....................................",
        ]

        events = QuanLyXuong.parse_indecal_log_events(lines, state)

        self.assertEqual(events[0]["event_type"], "PRINTING")
        self.assertEqual(events[0]["file_name"], "10~tho_119x191.prn")
        self.assertEqual(events[0]["forced_base_id"], "tho_119x191")
        done_event = [event for event in events if event["event_type"] == "DONE"][0]
        self.assertEqual(done_event["file_name"], "10~tho_119x191.prn")
        self.assertAlmostEqual(done_event["machine_meta"]["progress_percent"], 99.7, places=1)

    def test_indecal_log_parser_emits_progress_printing_events(self):
        state = {}
        lines = [
            "启动任务：12~hl_120x240.prn",
            "pInitParam->nTotalPrintPass=429",
            "[SM][1][2026/07/13 14:44:09][000000] nCurPassIndex=43: nFireStart=40826",
        ]

        events = QuanLyXuong.parse_indecal_log_events(lines, state)

        self.assertEqual([event["event_type"] for event in events], ["PRINTING", "PRINTING"])
        self.assertEqual(events[1]["file_name"], "12~hl_120x240.prn")
        self.assertEqual(events[1]["machine_meta"]["current_pass"], 43)
        self.assertEqual(events[1]["machine_meta"]["total_pass"], 429)
        self.assertEqual(events[1]["machine_meta"]["log_event_time"], "2026-07-13 14:44:09")
        self.assertNotIn("log_done_time", events[1]["machine_meta"])
        self.assertAlmostEqual(events[1]["machine_meta"]["progress_percent"], 10.0, places=1)

    def test_indecal_log_parser_keeps_max_pass_when_machine_resets_counter(self):
        state = {}
        lines = [
            "启动任务：10~tho_119x191.prn",
            "pInitParam->nTotalPrintPass=342",
            "nCurPassIndex=341: nFireStart=40674",
            "nCurPassIndex=0: nFireStart=0 nFireLen=0",
            "[SM][1][2026/07/13 13:57:17][000000] 打印完成.....................................",
        ]

        events = QuanLyXuong.parse_indecal_log_events(lines, state)

        self.assertEqual(events[-1]["event_type"], "DONE")
        self.assertAlmostEqual(events[-1]["machine_meta"]["progress_percent"], 99.7, places=1)
        self.assertEqual(events[-1]["machine_meta"]["log_done_time"], "2026-07-13 13:57:17")

    def test_indecal_rename_missing_source_is_ok_when_target_exists(self):
        new_folder = os.path.join(self.temp_dir.name, self.day, "New Folder")
        os.makedirs(new_folder, exist_ok=True)
        target = os.path.join(new_folder, "11~ghep_105x220.prn")
        with open(target, "wb") as handle:
            handle.write(b"rip")

        inferred = QuanLyXuong.infer_existing_renamed_prn(
            os.path.join(new_folder, "11.prn"),
            os.path.join(self.temp_dir.name, self.day, "ghep_105x220._tf"),
        )

        self.assertEqual(inferred, target)

    def test_indecal_audit_writes_local_db_and_posts_to_server(self):
        QuanLyXuong.MACHINE_NAME = "indecal"
        QuanLyXuong.BASE_STORAGE = self.temp_dir.name
        sent = []
        QuanLyXuong.requests.post = lambda url, json, timeout: sent.append((url, json, timeout))

        payload = QuanLyXuong.indecal_audit(
            "RENAME_FAIL_NO_META",
            prn_path=r"D:\2026-07-13\New Folder\12.prn",
            file_size=1234,
            error="no meta",
        )

        self.assertEqual(payload["action"], "RENAME_FAIL_NO_META")
        self.assertEqual(sent[0][0], QuanLyXuong.indecal_rename_audit_url())
        self.assertEqual(sent[0][1]["prn_path"], r"D:\2026-07-13\New Folder\12.prn")
        self.assertEqual(sent[0][2], 2)
        audit_db = os.path.join(self.temp_dir.name, "Data", "indecal_rename_audit.db")
        conn = sqlite3.connect(audit_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = [dict(row) for row in conn.execute("SELECT machine, action, prn_path, file_size, error FROM rename_audit")]
        finally:
            conn.close()
        self.assertEqual(rows, [{
            "machine": "InDecal",
            "action": "RENAME_FAIL_NO_META",
            "prn_path": r"D:\2026-07-13\New Folder\12.prn",
            "file_size": 1234,
            "error": "no meta",
        }])

    def test_indecal_plain_prn_without_meta_waits_instead_of_sending_rip(self):
        QuanLyXuong.MACHINE_NAME = "indecal"
        QuanLyXuong.processed_set = set()
        QuanLyXuong.processed_prn = set()
        QuanLyXuong.prn_tracking = {}
        captured = []
        audits = []
        QuanLyXuong.process_event = lambda path, event_type, **kwargs: captured.append((event_type, path))
        original_audit = QuanLyXuong.indecal_audit
        QuanLyXuong.indecal_audit = lambda action, **kwargs: audits.append((action, kwargs))
        self.addCleanup(lambda: setattr(QuanLyXuong, "indecal_audit", original_audit))
        new_folder = os.path.join(self.temp_dir.name, self.day, "New Folder")
        os.makedirs(new_folder, exist_ok=True)
        plain_prn = self.make_file(self.day, "New Folder", "12.prn")
        QuanLyXuong.prn_tracking[plain_prn] = {
            "size": os.path.getsize(plain_prn),
            "last_changed": time.time() - 10,
            "retry": 0,
        }

        result = QuanLyXuong.handle_indecal_prn_rename_candidate(
            plain_prn,
            self.day,
            os.path.dirname(new_folder),
            new_folder,
            "12.prn",
            now_ts=time.time(),
        )

        self.assertEqual(result, "WAIT_META")
        self.assertEqual(captured, [])
        self.assertIn(plain_prn, QuanLyXuong.prn_tracking)
        self.assertNotIn(plain_prn, QuanLyXuong.processed_prn)
        self.assertNotIn(plain_prn, QuanLyXuong.processed_set)
        self.assertEqual(audits[-1][0], "RENAME_WAIT_META")

    def test_indecal_rename_cleans_only_selected_meta_file(self):
        QuanLyXuong.MACHINE_NAME = "indecal"
        QuanLyXuong.processed_set = set()
        QuanLyXuong.processed_prn = set()
        QuanLyXuong.recent_moved = {}
        QuanLyXuong.prn_tracking = {}
        captured = []
        QuanLyXuong.process_event = lambda path, event_type, **kwargs: captured.append((event_type, path))
        original_audit = QuanLyXuong.indecal_audit
        QuanLyXuong.indecal_audit = lambda action, **kwargs: None
        self.addCleanup(lambda: setattr(QuanLyXuong, "indecal_audit", original_audit))
        day_folder = os.path.join(self.temp_dir.name, self.day)
        new_folder = os.path.join(day_folder, "New Folder")
        os.makedirs(new_folder, exist_ok=True)
        plain_prn = self.make_file(self.day, "New Folder", "12.prn")
        selected_meta = self.make_file(self.day, "job._tf")
        other_meta = self.make_file(self.day, "other._tf")
        self.make_file(self.day, "job.tif")
        os.utime(selected_meta, (time.time() - 1, time.time() - 1))
        os.utime(other_meta, (time.time() - 30, time.time() - 30))
        QuanLyXuong.prn_tracking[plain_prn] = {
            "size": os.path.getsize(plain_prn),
            "last_changed": time.time() - 10,
            "retry": 0,
        }

        result = QuanLyXuong.handle_indecal_prn_rename_candidate(
            plain_prn,
            self.day,
            day_folder,
            new_folder,
            "12.prn",
            now_ts=time.time(),
        )

        expected_prn = os.path.join(new_folder, "12~job.prn").lower()
        self.assertEqual(result, "RENAMED")
        self.assertEqual([(event, path.lower()) for event, path in captured], [("RIP", expected_prn)])
        self.assertFalse(os.path.exists(selected_meta))
        self.assertTrue(os.path.exists(other_meta))

    def test_client_instance_lock_blocks_second_instance(self):
        first = QuanLyXuong.acquire_client_instance_lock("indecal", self.temp_dir.name)
        self.addCleanup(lambda: QuanLyXuong.release_client_instance_lock(first))

        second = QuanLyXuong.acquire_client_instance_lock("indecal", self.temp_dir.name)

        self.assertIsNotNone(first)
        self.assertIsNone(second)

if __name__ == "__main__":
    unittest.main()


