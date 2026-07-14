import hashlib
from dataclasses import dataclass
from os import path
import os


PRINT_MACHINES = {"inbat", "indecal"}


@dataclass(frozen=True)
class MachineConfig:
    machine_name: str
    machine_display: str
    root: str
    base_storage: str = r"C:\QuanLyXuong"


@dataclass(frozen=True)
class ScanPlan:
    events: list[tuple[str, str]]
    processed_add: set[str]
    processed_discard: set[str]
    recent_moved_discard: set[str]


@dataclass(frozen=True)
class LogTailState:
    offset: int = 0
    remainder: str = ""


def read_new_log_lines(file_path: str, state: LogTailState | None = None, encoding: str = "utf-8"):
    current = state or LogTailState()
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return [], current

    offset = current.offset
    remainder = current.remainder
    if size < offset:
        offset = 0
        remainder = ""

    if size == offset:
        return [], LogTailState(offset=offset, remainder=remainder)

    with open(file_path, "rb") as handle:
        handle.seek(offset)
        raw = handle.read()

    offset += len(raw)
    text = raw.decode(encoding, "ignore")
    combined = remainder + text
    if not combined:
        return [], LogTailState(offset=offset, remainder="")

    if combined.endswith(("\n", "\r")):
        return combined.splitlines(), LogTailState(offset=offset, remainder="")

    lines = combined.splitlines()
    if not lines:
        return [], LogTailState(offset=offset, remainder=combined)

    return lines[:-1], LogTailState(offset=offset, remainder=lines[-1])


def parse_machine_aliases(aliases_text: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for group in aliases_text.split(";"):
        if "=" not in group:
            continue
        machine_name, raw_aliases = group.split("=", 1)
        machine_name = machine_name.strip().lower()
        if machine_name not in {"inbat", "indecal", "cnc"}:
            continue
        for alias in raw_aliases.split(","):
            normalized_alias = alias.strip().lower()
            if normalized_alias:
                aliases[normalized_alias] = machine_name
    return aliases

def resolve_machine_config(hostname: str, aliases_text: str = "") -> MachineConfig | None:
    normalized = hostname.strip().lower()
    normalized = parse_machine_aliases(aliases_text).get(normalized, normalized)
    configs = {
        "inbat": MachineConfig("inbat", "InBat", r"D:\\"),
        "indecal": MachineConfig("indecal", "InDecal", r"D:\\"),
        "cnc": MachineConfig("cnc", "CNC", r"D:\CNC"),
    }
    return configs.get(normalized)


def is_target_file_for_machine(machine_name: str, filename: str) -> bool:
    lowered = filename.lower()
    if machine_name == "cnc":
        return lowered.endswith((".tap", ".nc", ".txt"))
    return lowered.endswith((".tif", ".jpg"))


def is_export_file(filename: str) -> bool:
    lowered = filename.lower()
    ext = path.splitext(lowered)[1]
    if not ext or ext.startswith("._"):
        return False
    if lowered.endswith(".bmp") or ".prn." in lowered or ".prt." in lowered:
        return False
    return ext not in (".prn", ".prt", ".ini", ".db", ".json", ".csv", ".txt", ".tmp", ".exe", ".sys", ".log")


def is_meta_file(filename: str) -> bool:
    name = path.basename(filename).lower()
    ext = path.splitext(filename)[1].lower()
    return (name.startswith("._") and len(name) == 4) or (ext.startswith("._") and len(ext) == 4)


def get_expected_meta(ext_str: str) -> str:
    clean = ext_str.replace(".", "").lower()
    return f"._{clean[0]}{clean[-1]}" if clean else ""


def normalize_event_path(file_path: str) -> str:
    return str(file_path or "").replace("/", "\\").lower().strip()


def make_event_identity(
    machine_name: str,
    event_type: str,
    file_path: str,
    event_time: str = "",
    forced_base_id: str | None = None,
) -> str:
    parts = [
        "qlx-v2",
        str(machine_name or "").lower().strip(),
        str(event_type or "").upper().strip(),
        normalize_event_path(forced_base_id or file_path),
        str(event_time or "").strip(),
    ]
    return "evt:" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def is_new_folder_path(file_path: str) -> bool:
    parts = [part.lower() for part in file_path.replace("/", "\\").split("\\")]
    return "new folder" in parts


def classify_created_path(machine_name: str, file_path: str) -> str | None:
    lowered = file_path.lower()
    filename = path.basename(file_path)
    if machine_name == "cnc":
        if not is_new_folder_path(file_path) and is_target_file_for_machine(machine_name, filename):
            return "EXPORT"
        return None

    ext = path.splitext(lowered)[1]
    if machine_name == "indecal" and any(marker in lowered for marker in ("~error", "~skipped", "~ghost")):
        return None
    if is_export_file(file_path):
        return "EXPORT"
    if ext in (".prn", ".prt") and machine_name != "inbat":
        if machine_name == "indecal" and "~" not in path.basename(file_path):
            return None
        return "RIP"
    return None


def plan_scan_events(
    machine_name: str,
    current_paths: set[str],
    previous_paths: set[str],
    processed_paths: set[str],
    recent_moved_paths: set[str],
) -> ScanPlan:
    events: list[tuple[str, str]] = []
    processed_add: set[str] = set()
    processed_discard: set[str] = set()
    recent_moved_discard: set[str] = set()

    for file_path in sorted(current_paths - processed_paths):
        if file_path in recent_moved_paths:
            recent_moved_discard.add(file_path)
            continue
        event_type = classify_created_path(machine_name, file_path)
        if event_type:
            events.append((event_type, file_path))
        if event_type or machine_name != "indecal" or "~" in path.basename(file_path):
            processed_add.add(file_path)

    for file_path in sorted(previous_paths - current_paths):
        if file_path in recent_moved_paths:
            recent_moved_discard.add(file_path)
        else:
            events.append(("DELETE", file_path))
        processed_discard.add(file_path)

    return ScanPlan(events, processed_add, processed_discard, recent_moved_discard)


def parse_inbat_printmon_snapshot(raw: bytes, current_job: str | None, current_switch: int | None):
    lowered = raw.lower()
    ext_idx = lowered.find(b".prt")
    if ext_idx == -1:
        ext_idx = lowered.find(b".prn")
    if ext_idx == -1:
        return None, (None, None)

    start_idx = -1
    for idx in range(ext_idx, -1, -1):
        if idx > 0 and raw[idx : idx + 2] == b":\\":
            start_idx = idx - 1
            break
    if start_idx == -1:
        return None, (current_job, current_switch)

    file_path = raw[start_idx : ext_idx + 4].decode("utf-8", "ignore").strip()
    switch = next((byte for byte in raw[ext_idx + 4 :] if byte not in (0x00, 0x20, 0x09, 0x0A, 0x0D)), None)
    if switch not in (1, 2):
        return None, (current_job, current_switch)

    if current_job != file_path:
        event_type = "PRINTING" if switch == 1 else "DONE"
        return (event_type, file_path), (file_path, switch)

    if current_switch == 1 and switch == 2:
        return ("DONE", file_path), (file_path, 2)
    return None, (file_path, switch)


def parse_indecal_log_lines(lines: list[str], current_job: str | None, current_base_id: str | None):
    events: list[tuple[str, str, str]] = []
    job = current_job
    base_id = current_base_id
    start_markers = ("启动任务：", "启动任务:", "Ã†Ã´Â¶Â¯ÃˆÃŽÃŽÃ±Â£Âº")
    done_markers = ("打印动作完成", "打印结束", "打印完成")
    cancel_markers = ("PRINT_RESULT_CANCEL", "printing is cancelled", "ÃˆÂ¡ÃÃ»Â´Ã²Ã“Â¡")

    for line in lines:
        if any(marker in line for marker in start_markers):
            raw_name = line
            for marker in start_markers:
                if marker in raw_name:
                    raw_name = raw_name.split(marker)[-1].strip()
                    break
            stem = path.splitext(raw_name.split("\\")[-1])[0]
            base_id = stem.split("~")[-1] if "~" in stem else stem
            if base_id.endswith((".tif", ".jpg")):
                base_id = base_id[:-4]
            job = stem
            events.append(("PRINTING", f"{job}.prn", base_id))
        elif job and any(marker in line for marker in done_markers):
            events.append(("DONE", f"{job}.prn", base_id or job))
            job = None
            base_id = None
        elif job and any(marker in line for marker in cancel_markers):
            events.append(("DELETE", f"{job}.prn", base_id or job))
            job = None
            base_id = None

    return events, (job, base_id)


def parse_cnc_log_lines(lines: list[str], machine_state: str, current_job: str):
    events: list[tuple[str, str]] = []
    state = machine_state
    job = current_job

    for raw_line in lines:
        line = raw_line.replace("‘", "'").replace("’", "'")
        if "Initiate a simulation" in line:
            state = "SIMULATING"
        elif "Initiate a machining task" in line:
            state = "CUTTING"
            parts = line.split("'")
            if len(parts) > 1 and parts[1]:
                job = parts[1]
                events.append(("CUTTING", job))
        elif "中断终止" in line:
            if state == "CUTTING" and job:
                events.append(("DELETE", job))
                state = "IDLE"
                job = ""
        elif "正常完毕" in line:
            if state == "CUTTING" and job:
                events.append(("DONE", job))
                state = "IDLE"
                job = ""
            elif state == "SIMULATING":
                state = "IDLE"

    return events, (state, job)
