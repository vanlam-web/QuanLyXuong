import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT_PATH = os.path.join(PROJECT_ROOT, "scripts", "Update-WorkstationClientIfIdle.ps1")
INSTALLER_PATH = os.path.join(PROJECT_ROOT, "scripts", "Install-WorkstationAutoUpdateTask.ps1")
LAUNCHER_PATH = os.path.join(PROJECT_ROOT, "scripts", "Start-WorkstationClient.ps1")


class WorkstationAutoUpdateScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dist_dir = os.path.join(self.temp_dir.name, "dist")
        self.local_dir = os.path.join(self.temp_dir.name, "client")
        os.makedirs(self.dist_dir, exist_ok=True)
        self.write_dist("new client")

    def write_dist(self, content):
        exe_path = os.path.join(self.dist_dir, "QuanLyXuong.exe")
        with open(exe_path, "wb") as f:
            f.write(content.encode("utf-8"))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest().upper()
        manifest = {"files": [{"name": "QuanLyXuong.exe", "sha256": digest}]}
        with open(os.path.join(self.dist_dir, "BUILD_MANIFEST.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)

    def write_auto_update_dist(self, content):
        auto_dir = os.path.join(self.temp_dir.name, "dist-auto-update")
        os.makedirs(auto_dir, exist_ok=True)
        exe_path = os.path.join(auto_dir, "QuanLyXuong.exe")
        with open(exe_path, "wb") as f:
            f.write(content.encode("utf-8"))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest().upper()
        manifest = {"files": [{"name": "QuanLyXuong.exe", "sha256": digest}]}
        with open(os.path.join(auto_dir, "BUILD_MANIFEST.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        return auto_dir

    def overwrite_dist_exe_only(self, content):
        exe_path = os.path.join(self.dist_dir, "QuanLyXuong.exe")
        with open(exe_path, "wb") as f:
            f.write(content.encode("utf-8"))

    def write_status(self, payload):
        status_path = os.path.join(self.temp_dir.name, "status.json")
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return status_path

    def write_state(self, payload):
        state_path = os.path.join(self.temp_dir.name, "state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return state_path

    def old_stamp(self, seconds):
        return (datetime.now() - timedelta(seconds=seconds)).replace(microsecond=0).isoformat()

    def run_script(self, status_payload, machine="InBat", extra_args=None, idle_seconds=0, state_payload=None):
        status_path = self.write_status(status_payload)
        state_path = self.write_state(state_payload) if state_payload is not None else None
        args = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                SCRIPT_PATH,
                "-Machine",
                machine,
                "-NasDistPath",
                self.dist_dir,
                "-LocalDir",
                self.local_dir,
                "-StatusJsonPath",
                status_path,
                "-NoStart",
        ]
        if idle_seconds is not None:
            args.extend(["-IdleSeconds", str(idle_seconds)])
        if state_path:
            args.extend(["-StatePath", state_path])
        if extra_args:
            args.extend(extra_args)
        return subprocess.run(
            args,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_active_print_machine_skips_copy_in_safe_mode(self):
        result = self.run_script({"RUNNING": [{"machine": "InBat", "name": "job.prt"}]})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BUSY InBat RUNNING", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_print_machine_waits_for_rip_queue_to_empty(self):
        result = self.run_script({"RUNNING": [], "RIP": [{"machine": "InDecal", "name": "ready.prn"}]}, machine="InDecal")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BUSY InDecal RIP", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_cnc_waits_for_export_queue_to_empty(self):
        result = self.run_script({"RUNNING": [], "EXPORTED": [{"machine": "CNC", "name": "ready.tap"}]}, machine="CNC")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BUSY CNC EXPORTED", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_allow_while_active_updates_immediately(self):
        result = self.run_script(
            {"RUNNING": [{"machine": "InBat", "name": "job.prt"}]},
            extra_args=["-AllowWhileActive"],
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UPDATED", result.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_idle_machine_copies_and_verifies_new_client(self):
        result = self.run_script({"RUNNING": []})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UPDATED", result.stdout)
        with open(os.path.join(self.local_dir, "QuanLyXuong.exe"), "rb") as f:
            self.assertEqual(f.read(), b"new client")
        self.assertTrue(os.path.exists(os.path.join(self.local_dir, "BUILD_MANIFEST.json")))

    def test_idle_machine_updates_legacy_local_client_path(self):
        result = self.run_script({"RUNNING": []})

        self.assertEqual(result.returncode, 0, result.stderr)
        legacy_exe = os.path.join(os.path.dirname(self.local_dir), "QuanLyXuong_Local.exe")
        with open(legacy_exe, "rb") as f:
            self.assertEqual(f.read(), b"new client")

    def test_update_script_stops_legacy_processes_by_name_not_path(self):
        with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
            script = f.read()

        self.assertIn("Get-Process QuanLyXuong,QuanLyXuong_Local", script)
        self.assertNotIn("GetFullPath($_.Path) -eq $localFullPath", script)

    def test_mismatched_dist_exe_uses_sibling_auto_update_dist(self):
        self.write_auto_update_dist("new client")
        self.overwrite_dist_exe_only("old locked client")

        result = self.run_script({"RUNNING": []})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SOURCE_SWITCH", result.stdout)
        self.assertIn("UPDATED", result.stdout)
        with open(os.path.join(self.local_dir, "QuanLyXuong.exe"), "rb") as f:
            self.assertEqual(f.read(), b"new client")

    def test_default_idle_window_waits_before_copy(self):
        result = self.run_script({"RUNNING": []}, idle_seconds=None)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WAIT_IDLE InBat - idle timer started", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_paused_machine_waits_for_extra_quiet_window_after_idle(self):
        result = self.run_script(
            {"RUNNING": [{"machine": "CNC", "name": "paused.tap", "status": "PAUSE", "updated": "2026-07-14 10:00:00"}]},
            machine="CNC",
            idle_seconds=300,
            state_payload={"idleSince": self.old_stamp(600), "lastBusyAt": ""},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WAIT_PAUSE_QUIET CNC - pause quiet timer started", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_paused_machine_updates_after_idle_and_unchanged_pause_log(self):
        paused_key = "paused.tap|2026-07-14 10:00:00|PAUSE|"
        result = self.run_script(
            {"RUNNING": [{"machine": "CNC", "name": "paused.tap", "status": "PAUSE", "updated": "2026-07-14 10:00:00"}]},
            machine="CNC",
            idle_seconds=300,
            state_payload={
                "idleSince": self.old_stamp(900),
                "lastBusyAt": "",
                "pausedQuietSince": self.old_stamp(600),
                "lastPausedLogKey": paused_key,
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UPDATED", result.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_paused_machine_resets_quiet_window_when_pause_log_changes(self):
        result = self.run_script(
            {"RUNNING": [{"machine": "CNC", "name": "paused.tap", "status": "PAUSE", "updated": "2026-07-14 10:05:00"}]},
            machine="CNC",
            idle_seconds=300,
            state_payload={
                "idleSince": self.old_stamp(900),
                "lastBusyAt": "",
                "pausedQuietSince": self.old_stamp(600),
                "lastPausedLogKey": "paused.tap|2026-07-14 10:00:00|PAUSE|",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WAIT_PAUSE_QUIET CNC - pause log changed", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.local_dir, "QuanLyXuong.exe")))

    def test_installer_can_print_scheduled_task_command(self):
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                INSTALLER_PATH,
                "-Machine",
                "InBat",
                "-NasDistPath",
                self.dist_dir,
                "-ScriptPath",
                SCRIPT_PATH,
                "-PrintCommandOnly",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("QLX Auto Update InBat", result.stdout)
        self.assertIn("Update-WorkstationClientIfIdle.ps1", result.stdout)
        self.assertIn("-Machine InBat", result.stdout)
        self.assertIn("-NasDistPath", result.stdout)

    def test_installer_gates_battery_setting_parameters_for_old_powershell(self):
        with open(INSTALLER_PATH, "r", encoding="utf-8") as f:
            script = f.read()

        self.assertIn('$settingsParams = (Get-Command New-ScheduledTaskSettingsSet).Parameters', script)
        self.assertIn('$settings = New-ScheduledTaskSettingsSet @settingsArgs', script)
        self.assertNotIn('New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DisallowStartIfOnBatteries:$false', script)

    def test_launcher_uses_sibling_auto_update_dist_when_dist_exe_mismatches_manifest(self):
        self.write_auto_update_dist("new client")
        self.overwrite_dist_exe_only("old locked client")

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                LAUNCHER_PATH,
                "-NasDistPath",
                self.dist_dir,
                "-LocalDir",
                self.local_dir,
                "-NoStart",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SOURCE_SWITCH dist -> dist-auto-update", result.stdout)
        with open(os.path.join(self.local_dir, "QuanLyXuong.exe"), "rb") as f:
            self.assertEqual(f.read(), b"new client")

    def test_launcher_updates_legacy_local_client_path(self):
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                LAUNCHER_PATH,
                "-NasDistPath",
                self.dist_dir,
                "-LocalDir",
                self.local_dir,
                "-NoStart",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        legacy_exe = os.path.join(os.path.dirname(self.local_dir), "QuanLyXuong_Local.exe")
        with open(legacy_exe, "rb") as f:
            self.assertEqual(f.read(), b"new client")


if __name__ == "__main__":
    unittest.main()
