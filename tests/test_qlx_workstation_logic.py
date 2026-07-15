import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from qlx_workstation_logic import (
    LogTailState,
    MachineConfig,
    classify_created_path,
    get_expected_meta,
    is_export_file,
    is_meta_file,
    make_event_identity,
    normalize_inbat_feed_progress,
    parse_machine_aliases,
    parse_cnc_log_lines,
    parse_inbat_printfile_progress,
    parse_inbat_printmon_snapshot,
    parse_indecal_log_lines,
    plan_scan_events,
    read_new_log_lines,
    resolve_machine_config,
)


class WorkstationLogicTests(unittest.TestCase):
    def test_resolve_machine_config_maps_known_hostnames(self):
        self.assertEqual(resolve_machine_config("INBAT").machine_name, "inbat")
        self.assertEqual(resolve_machine_config("indecal").machine_display, "InDecal")
        self.assertEqual(resolve_machine_config("cnc").root, r"D:\CNC")
        self.assertIsNone(resolve_machine_config("office-pc"))

    def test_resolve_machine_config_supports_aliases(self):
        aliases = "inbat=INBAT-PC, PRINT-01; indecal=DECAL-PC; cnc=CNC-BACKUP"

        self.assertEqual(parse_machine_aliases(aliases)["print-01"], "inbat")
        self.assertEqual(resolve_machine_config("DECAL-PC", aliases).machine_name, "indecal")
        self.assertEqual(resolve_machine_config("cnc-backup", aliases).root, r"D:\CNC")

    def test_export_and_meta_file_rules_match_printer_expectations(self):
        self.assertTrue(is_export_file(r"D:\2026-07-09\job.tif"))
        self.assertTrue(is_export_file(r"D:\2026-07-09\job.jpg"))
        self.assertFalse(is_export_file(r"D:\2026-07-09\job.prn"))
        self.assertFalse(is_export_file(r"D:\2026-07-09\job.prt"))
        self.assertFalse(is_export_file(r"D:\2026-07-09\job.prn.tmp"))
        self.assertTrue(is_meta_file("._tf"))
        self.assertEqual(get_expected_meta(".tif"), "._tf")
        self.assertEqual(get_expected_meta(".jpg"), "._jg")

    def test_classify_created_path_per_machine(self):
        self.assertEqual(classify_created_path("inbat", r"D:\2026-07-09\kh.tif"), "EXPORT")
        self.assertIsNone(classify_created_path("inbat", r"D:\2026-07-09\New Folder\kh.prn"))
        self.assertEqual(classify_created_path("indecal", r"D:\2026-07-09\New Folder\kh~meta.prn"), "RIP")
        self.assertIsNone(classify_created_path("indecal", r"D:\2026-07-09\New Folder\kh.prn"))
        self.assertEqual(classify_created_path("cnc", r"D:\CNC\2026-07-09\kh.tap"), "EXPORT")
        self.assertIsNone(classify_created_path("cnc", r"D:\CNC\2026-07-09\New Folder\kh.tap"))

    def test_plan_scan_events_avoids_moved_duplicates_and_detects_delete(self):
        previous = {r"d:\2026-07-09\old.tif"}
        processed = {r"d:\2026-07-09\old.tif"}
        current = {r"d:\2026-07-09\new.tif"}
        recent_moved = {r"d:\2026-07-09\new.tif"}

        plan = plan_scan_events("inbat", current, previous, processed, recent_moved)

        self.assertEqual(plan.events, [("DELETE", r"d:\2026-07-09\old.tif")])
        self.assertEqual(plan.processed_add, set())
        self.assertEqual(plan.processed_discard, {r"d:\2026-07-09\old.tif"})
        self.assertEqual(plan.recent_moved_discard, {r"d:\2026-07-09\new.tif"})

    def test_inbat_printmon_snapshot_extracts_printing_and_done(self):
        raw_printing = b"xxD:\\Jobs\\KH001.prn\x00\x01"
        raw_done = b"xxD:\\Jobs\\KH001.prn\x00\x02"

        event, state = parse_inbat_printmon_snapshot(raw_printing, None, None)
        self.assertEqual(event, ("PRINTING", r"D:\Jobs\KH001.prn"))

        event, state = parse_inbat_printmon_snapshot(raw_done, *state)
        self.assertEqual(event, ("DONE", r"D:\Jobs\KH001.prn"))

    def test_inbat_printfile_progress_reads_printmon_offsets(self):
        raw = bytearray(b"xxD:\\Jobs\\KH001.prt")
        raw.extend(b"\x00" * (272 - len(raw)))
        raw[260:264] = (1).to_bytes(4, "little")
        raw[264:268] = (18).to_bytes(4, "little")
        raw[268:272] = (545).to_bytes(4, "little")

        meta = parse_inbat_printfile_progress(bytes(raw))

        self.assertEqual(meta["progress_source"], "inbat_printfile_steps")
        self.assertEqual(meta["current_pass"], 18)
        self.assertEqual(meta["total_pass"], 545)
        self.assertAlmostEqual(meta["progress_percent"], 18 * 100.0 / 545)

    def test_inbat_printmon_snapshot_emits_progress_updates(self):
        def raw_with_pass(current_pass):
            raw = bytearray(b"xxD:\\Jobs\\KH001.prt")
            raw.extend(b"\x00" * (272 - len(raw)))
            raw[260:264] = (1).to_bytes(4, "little")
            raw[264:268] = current_pass.to_bytes(4, "little")
            raw[268:272] = (545).to_bytes(4, "little")
            return bytes(raw)

        event, state = parse_inbat_printmon_snapshot(raw_with_pass(18), None, None)
        self.assertEqual(event[0:2], ("PRINTING", r"D:\Jobs\KH001.prt"))
        self.assertEqual(event[2]["current_pass"], 18)
        self.assertAlmostEqual(event[2]["progress_percent"], 18 * 100.0 / 545)

        event, state = parse_inbat_printmon_snapshot(raw_with_pass(24), *state)
        self.assertEqual(event[0:2], ("PRINTING", r"D:\Jobs\KH001.prt"))
        self.assertEqual(event[2]["current_pass"], 24)
        self.assertAlmostEqual(event[2]["progress_percent"], 24 * 100.0 / 545)

    def test_normalize_inbat_feed_progress_uses_feed_length_not_printmon_total(self):
        meta = {
            "current_pass": 148,
            "total_pass": 410,
            "height_cm": 487.045,
            "width_cm": 260.043,
            "progress_percent": 36.1,
        }
        normalized = normalize_inbat_feed_progress(meta)
        self.assertEqual(normalized["current_pass"], 148)
        self.assertEqual(normalized["total_pass"], 203)
        self.assertEqual(normalized["printmon_total_pass"], 410)
        self.assertEqual(normalized["progress_source"], "inbat_feed_length_steps")
        self.assertAlmostEqual(normalized["progress_percent"], 148 * 100.0 / 203, places=1)

    def test_event_identity_is_stable_for_same_logical_event(self):
        first = make_event_identity(
            "inbat",
            "DONE",
            r"D:\2026-07-10\New Folder\KH001.prn",
            event_time="2026-07-10 15:27:57",
        )
        replay = make_event_identity(
            "InBat",
            "DONE",
            r"d:\2026-07-10\new folder\KH001.prn",
            event_time="2026-07-10 15:27:57",
        )
        different_status = make_event_identity(
            "inbat",
            "PRINTING",
            r"D:\2026-07-10\New Folder\KH001.prn",
            event_time="2026-07-10 15:27:57",
        )

        self.assertEqual(first, replay)
        self.assertNotEqual(first, different_status)

    def test_indecal_log_lines_track_start_done_and_cancel(self):
        events, state = parse_indecal_log_lines(["2026 启动任务：D:\\Jobs\\kh~meta.prn"], None, None)
        self.assertEqual(events, [("PRINTING", "kh~meta.prn", "meta")])

        events, state = parse_indecal_log_lines(["打印动作完成"], *state)
        self.assertEqual(events, [("DONE", "kh~meta.prn", "meta")])
        self.assertEqual(state, (None, None))

        events, state = parse_indecal_log_lines(["启动任务：D:\\Jobs\\kh2.prn", "printing is cancelled"], None, None)
        self.assertEqual(events[-1], ("DELETE", "kh2.prn", "kh2"))

    def test_cnc_log_lines_track_cutting_done_and_delete(self):
        events, state = parse_cnc_log_lines(["Initiate a machining task 'D:\\CNC\\job.tap'"], "IDLE", "")
        self.assertEqual(events, [("CUTTING", r"D:\CNC\job.tap")])

        events, state = parse_cnc_log_lines(["正常完毕"], *state)
        self.assertEqual(events, [("DONE", r"D:\CNC\job.tap")])
        self.assertEqual(state, ("IDLE", ""))

        events, state = parse_cnc_log_lines(["Initiate a machining task 'D:\\CNC\\job2.tap'", "中断终止"], "IDLE", "")
        self.assertEqual(events[-1], ("DELETE", r"D:\CNC\job2.tap"))

    def test_log_tail_keeps_partial_line_until_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "machine.log")
            with open(log_path, "wb") as handle:
                handle.write("line 1\nline".encode("gb18030"))

            state = LogTailState()
            lines, state = read_new_log_lines(log_path, state, encoding="gb18030")

            self.assertEqual(lines, ["line 1"])
            self.assertEqual(state.remainder, "line")

            with open(log_path, "ab") as handle:
                handle.write(" 2\n".encode("gb18030"))

            lines, state = read_new_log_lines(log_path, state, encoding="gb18030")

            self.assertEqual(lines, ["line 2"])
            self.assertEqual(state.remainder, "")

    def test_log_tail_resets_when_file_rotates_or_truncates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "machine.log")
            with open(log_path, "wb") as handle:
                handle.write(b"old line\n")

            state = LogTailState()
            lines, state = read_new_log_lines(log_path, state)
            self.assertEqual(lines, ["old line"])

            with open(log_path, "wb") as handle:
                handle.write(b"new\n")

            lines, state = read_new_log_lines(log_path, state)

            self.assertEqual(lines, ["new"])


if __name__ == "__main__":
    unittest.main()


