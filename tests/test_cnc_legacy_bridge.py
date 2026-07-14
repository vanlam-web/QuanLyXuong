import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import cnc_legacy_bridge
from cnc_legacy_bridge import legacy_path, parse_history_lines


class CncLegacyBridgeTests(unittest.TestCase):
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
                cnc_legacy_bridge.post_ping = lambda api, source: None
                cnc_legacy_bridge.post_event = lambda api, event: posted.append(event)
                cnc_legacy_bridge.run_once(args, {})
            finally:
                cnc_legacy_bridge.post_ping = original_ping
                cnc_legacy_bridge.post_event = original_post

            self.assertEqual([event["event_type"] for event in posted], ["CUTTING", "DONE"])
            self.assertEqual(posted[1]["file_name"], "XXD")


if __name__ == "__main__":
    unittest.main()
