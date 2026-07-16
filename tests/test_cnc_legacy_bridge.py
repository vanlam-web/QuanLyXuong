import os
import sys
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import cnc_legacy_bridge
from cnc_legacy_bridge import build_ping_payload, legacy_path, parse_history_lines, read_dyn_progress_event, read_ncstudio_health
from cnc_log_parser import parse_cnc_log_events


class CncLegacyBridgeTests(unittest.TestCase):
    def test_ncstudio_health_detects_running_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            ncstudio = os.path.join(tmp, "NCSTUDIO.LOG")
            with open(ncstudio, "w", encoding="gb18030") as handle:
                handle.write("M\t2026-07-13 13:50:32\tInitiate a machining task: 'D:\\CNC\\2026-07-13\\XXD.tap', from beginning to end\n")
            mtime = datetime(2026, 7, 13, 13, 50, 32).timestamp()
            os.utime(ncstudio, (mtime, mtime))

            health = read_ncstudio_health(ncstudio, now_dt=datetime(2026, 7, 13, 13, 50, 45), stale_seconds=60)

        self.assertEqual(health["cnc_ncstudio_state"], "RUNNING")
        self.assertEqual(health["cnc_ncstudio_current_job"], r"D:\CNC\2026-07-13\XXD.tap")
        self.assertEqual(health["cnc_ncstudio_last_event_time"], "2026-07-13 13:50:32")

    def test_ncstudio_health_detects_stale_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            ncstudio = os.path.join(tmp, "NCSTUDIO.LOG")
            with open(ncstudio, "w", encoding="gb18030") as handle:
                handle.write("M\t2026-07-13 13:50:32\tInitiate a machining task: 'D:\\CNC\\2026-07-13\\XXD.tap', from beginning to end\n")
            mtime = datetime(2026, 7, 13, 13, 50, 32).timestamp()
            os.utime(ncstudio, (mtime, mtime))

            health = read_ncstudio_health(ncstudio, now_dt=datetime(2026, 7, 13, 14, 5, 0), stale_seconds=60)

        self.assertEqual(health["cnc_ncstudio_state"], "STALE")
        self.assertEqual(health["cnc_ncstudio_log_mtime"], "2026-07-13 13:50:32")

    def test_build_ping_payload_includes_ncstudio_health(self):
        payload = build_ping_payload(
            r"\\CNC\CNC\CLIENT_CNC\file_history.csv",
            {
                "cnc_ncstudio_state": "EXITED",
                "cnc_ncstudio_log_mtime": "2026-07-13 14:20:00",
            },
        )

        self.assertEqual(payload["machine"], "cnc")
        self.assertEqual(payload["version"], cnc_legacy_bridge.BRIDGE_VERSION)
        self.assertEqual(payload["cnc_bridge_source_path"], r"\\CNC\CNC\CLIENT_CNC\file_history.csv")
        self.assertEqual(payload["cnc_ncstudio_state"], "EXITED")

    def test_parse_history_lines_keeps_comma_in_legacy_csv_names(self):
        rows = parse_history_lines(
            "2026-07-09 14:27:24,CUTTING,ttt_to_mui1,5,ttt_to_mui1,5\n"
            "2026-07-10 10:16:45,EXPORT,namlee_mui1,5_120x83,namlee_mui1,5_120x83\n"
        )

        self.assertEqual(rows[0]["file_name"], "ttt_to_mui1,5")
        self.assertEqual(rows[0]["event_type"], "CUTTING")
        self.assertEqual(rows[1]["file_name"], "namlee_mui1,5_120x83")
        self.assertEqual(rows[1]["path"], r"D:\CNC\2026-07-10\namlee_mui1,5_120x83.tap")

    def test_legacy_path_adds_tap_extension_when_history_has_base_name_only(self):
        self.assertEqual(
            legacy_path("abc_120x80", "2026-07-10 07:36:05"),
            r"D:\CNC\2026-07-10\abc_120x80.tap",
        )

    def test_legacy_path_keeps_existing_extension(self):
        self.assertEqual(
            legacy_path("abc.nc", "2026-07-10 07:36:05"),
            r"D:\CNC\2026-07-10\abc.nc",
        )

    def test_run_once_reads_new_ncstudio_log_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = os.path.join(tmp, "file_history.csv")
            ncstudio = os.path.join(tmp, "NCSTUDIO.LOG")
            open(history, "w", encoding="utf-8").close()
            with open(ncstudio, "w", encoding="gb18030") as handle:
                handle.write("M\t2026-07-13 13:50:32\tInitiate a machining task: 'D:\\CNC\\2026-07-13\\XXD.tap', from beginning to end\n")
                handle.write("M\t2026-07-13 14:20:00\t文件'D:\\CNC\\2026-07-13\\XXD.tap'正常完毕\n")
            args = SimpleNamespace(
                history=history,
                ncstudio_log=ncstudio,
                api="http://example.invalid",
                import_existing=True,
                import_existing_ncstudio=True,
                dry_run=False,
            )
            posted = []
            original_ping = cnc_legacy_bridge.post_ping
            original_post = cnc_legacy_bridge.post_event
            try:
                cnc_legacy_bridge.post_ping = lambda api, source, health=None: None
                cnc_legacy_bridge.post_event = lambda api, event: posted.append(event)
                cnc_legacy_bridge.run_once(args, {})
            finally:
                cnc_legacy_bridge.post_ping = original_ping
                cnc_legacy_bridge.post_event = original_post

            self.assertEqual([event["event_type"] for event in posted], ["CUTTING", "DONE"])
            self.assertEqual(posted[1]["file_name"], "XXD")

    def test_run_once_posts_dyn_progress_for_current_cut_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = os.path.join(tmp, "file_history.csv")
            ncstudio = os.path.join(tmp, "NCSTUDIO.LOG")
            dyn = os.path.join(tmp, "NCSTUDIO.DYN")
            tap = os.path.join(tmp, "nsss_120x120.tap")
            open(history, "w", encoding="utf-8").close()
            open(ncstudio, "w", encoding="gb18030").close()
            with open(dyn, "wb") as handle:
                handle.write(b"\x00#m\x03\x00L40\x00")
            with open(tap, "w", encoding="utf-8") as handle:
                handle.write("\n".join(["G1X1Y1"] * 100))
            args = SimpleNamespace(
                history=history,
                ncstudio_log=ncstudio,
                ncstudio_dyn=dyn,
                api="http://example.invalid",
                import_existing=True,
                import_existing_ncstudio=True,
                dry_run=False,
            )
            posted = []
            original_ping = cnc_legacy_bridge.post_ping
            original_post = cnc_legacy_bridge.post_event
            try:
                cnc_legacy_bridge.post_ping = lambda api, source, health=None: None
                cnc_legacy_bridge.post_event = lambda api, event: posted.append(event)
                with patch("cnc_legacy_bridge.find_existing_tap", return_value=tap):
                    cnc_legacy_bridge.run_once(args, {"current_cut_path": r"D:\CNC\2026-07-14\nsss_120x120.tap"})
            finally:
                cnc_legacy_bridge.post_ping = original_ping
                cnc_legacy_bridge.post_event = original_post

            self.assertEqual(posted[0]["event_type"], "CUTTING")
            self.assertEqual(posted[0]["machine_meta"]["current_line"], 40)
            self.assertEqual(posted[0]["machine_meta"]["line_count"], 100)
            self.assertAlmostEqual(posted[0]["machine_meta"]["progress_percent"], 40.0)

    def test_run_once_does_not_resurrect_cutting_from_dyn_after_log_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = os.path.join(tmp, "file_history.csv")
            ncstudio = os.path.join(tmp, "NCSTUDIO.LOG")
            dyn = os.path.join(tmp, "NCSTUDIO.DYN")
            tap = os.path.join(tmp, "nsss_120x120.tap")
            open(history, "w", encoding="utf-8").close()
            with open(ncstudio, "w", encoding="gb18030") as handle:
                handle.write("M\t2026-07-14 11:09:00\tInitiate a machining task: 'D:\\CNC\\2026-07-14\\nsss_120x120.tap', from beginning to end\n")
                handle.write("M\t2026-07-14 11:09:04\t文件'D:\\CNC\\2026-07-14\\nsss_120x120.tap'中断终止\n")
            with open(dyn, "wb") as handle:
                handle.write(b"\x00#m\x03\x00L40\x00")
            with open(tap, "w", encoding="utf-8") as handle:
                handle.write("\n".join(["G1X1Y1"] * 100))
            args = SimpleNamespace(
                history=history,
                ncstudio_log=ncstudio,
                ncstudio_dyn=dyn,
                dyn_stale_seconds=60,
                api="http://example.invalid",
                import_existing=True,
                import_existing_ncstudio=True,
                dry_run=False,
            )
            posted = []
            original_ping = cnc_legacy_bridge.post_ping
            original_post = cnc_legacy_bridge.post_event
            try:
                cnc_legacy_bridge.post_ping = lambda api, source, health=None: None
                cnc_legacy_bridge.post_event = lambda api, event: posted.append(event)
                with patch("cnc_legacy_bridge.find_existing_tap", return_value=tap):
                    cnc_legacy_bridge.run_once(args, {"current_cut_path": r"D:\CNC\2026-07-14\nsss_120x120.tap"})
            finally:
                cnc_legacy_bridge.post_ping = original_ping
                cnc_legacy_bridge.post_event = original_post

            self.assertEqual([event["event_type"] for event in posted], ["CUTTING", "PAUSE"])
            self.assertEqual(posted[1]["file_name"], "nsss_120x120")


    def test_dyn_progress_does_not_infer_pause_when_same_line_becomes_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            dyn = os.path.join(tmp, "NCSTUDIO.DYN")
            tap = os.path.join(tmp, "VCTT_F5_120X50.tap")
            with open(dyn, "wb") as handle:
                handle.write(b"\x00#m\x03\x00L22442\x00")
            with open(tap, "w", encoding="utf-8") as handle:
                handle.write("\n".join(["G1X1Y1"] * 24729))
            dyn_mtime = cnc_legacy_bridge.time.time()
            os.utime(dyn, (dyn_mtime, dyn_mtime))
            state = {"current_cut_path": r"D:\CNC\2026-07-14\VCTT_F5_120X50.tap"}

            with patch("cnc_legacy_bridge.find_existing_tap", return_value=tap):
                with patch("cnc_legacy_bridge.time.time", return_value=dyn_mtime + 1):
                    first = read_dyn_progress_event(dyn, state, stale_seconds=60)
                with patch("cnc_legacy_bridge.time.time", return_value=dyn_mtime + 120):
                    second = read_dyn_progress_event(dyn, state, stale_seconds=60)

            self.assertEqual(first["event_type"], "CUTTING")
            self.assertIsNone(second)

    def test_dyn_progress_prefers_tap_path_distance_over_line_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            dyn = os.path.join(tmp, "NCSTUDIO.DYN")
            tap = os.path.join(tmp, "long_second_cut.tap")
            with open(dyn, "wb") as handle:
                handle.write(b"\x00#m\x03\x00L4\x00")
            with open(tap, "w", encoding="utf-8") as handle:
                handle.write("\n".join([
                    "G0Z5",
                    "G0X0Y0",
                    "G1Z0",
                    "G1X100Y0",
                    "G1X1000Y0",
                ]))
            dyn_mtime = cnc_legacy_bridge.time.time()
            os.utime(dyn, (dyn_mtime, dyn_mtime))
            state = {"current_cut_path": r"D:\CNC\2026-07-15\long_second_cut.tap"}

            with patch("cnc_legacy_bridge.find_existing_tap", return_value=tap):
                with patch("cnc_legacy_bridge.time.time", return_value=dyn_mtime + 1):
                    event = read_dyn_progress_event(dyn, state, stale_seconds=60)

            meta = event["machine_meta"]
            self.assertEqual(meta["progress_source"], "cnc_tap_path")
            self.assertEqual(meta["current_line"], 4)
            self.assertEqual(meta["line_count"], 5)
            self.assertEqual(meta["current_path_length"], 100.0)
            self.assertEqual(meta["total_path_length"], 1000.0)
            self.assertAlmostEqual(meta["progress_percent"], 10.0)

    def test_parse_cnc_log_pause_clears_current_cut_path(self):
        state = {}
        events = parse_cnc_log_events([
            "M\t2026-07-14 17:12:02\tInitiate a machining task: 'D:\\CNC\\2026-07-14\\VCTT_F5_120X50.tap', from beginning to end",
            "M\t2026-07-14 17:35:29\t文件'D:\\CNC\\2026-07-14\\VCTT_F5_120X50.tap'中断终止",
        ], state=state)

        self.assertEqual([event["event_type"] for event in events], ["CUTTING", "PAUSE"])
        self.assertEqual(state.get("current_cut_path"), "")

if __name__ == "__main__":
    unittest.main()
