import os


def env_str(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def env_int(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default

def env_bool(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


DB_DIR = env_str("QLX_DB_DIR", r"C:\QuanLyXuong\Data")
BASE_DATA_CRM = env_str("QLX_BASE_DATA_CRM", r"C:\QuanLyXuong\Data_Auto_CRM")
OPENCLAW_PATH = env_str("QLX_OPENCLAW_PATH", r"C:\Users\Admin\AppData\Roaming\npm\openclaw.cmd")

SERVER_HOST = env_str("QLX_SERVER_HOST", "0.0.0.0")
SERVER_PORT = env_int("QLX_SERVER_PORT", 8000)
DASHBOARD_HOST = env_str("QLX_DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = env_int("QLX_DASHBOARD_PORT", 5000)
AUTO_CRM_HOST = env_str("QLX_AUTO_CRM_HOST", "127.0.0.1")
AUTO_CRM_PORT = env_int("QLX_AUTO_CRM_PORT", 8001)

API_SERVER_URL = env_str("QLX_API_SERVER_URL", "http://192.168.1.104:8000/api/log_event")
AUTO_CRM_WAKE_URL = env_str("QLX_AUTO_CRM_WAKE_URL", "http://127.0.0.1:8001/wake_up")
SERVER_BROADCAST_URL = env_str("QLX_SERVER_BROADCAST_URL", "http://127.0.0.1:8000/api/broadcast")

NAS_CLIENT_EXE_PATH = env_str("QLX_NAS_CLIENT_EXE_PATH", r"\\192.168.1.188\AI\Tools\dist\QuanLyXuong.exe")
NAS_SERVER_EXE_PATH = env_str("QLX_NAS_SERVER_EXE_PATH", r"\\192.168.1.188\AI\Tools\dist\server.exe")
NAS_DASHBOARD_EXE_PATH = env_str("QLX_NAS_DASHBOARD_EXE_PATH", r"\\192.168.1.188\AI\Tools\dist\Dashboard.exe")
NAS_CRM_EXE_PATH = env_str("QLX_NAS_CRM_EXE_PATH", r"\\192.168.1.188\AI\Tools\dist\Auto_CRM.exe")

KIOT_URL = env_str("QLX_KIOT_URL", "https://quangcaoinvanlam.kiotviet.vn/")

RUNTIME_MODE = env_str("QLX_RUNTIME_MODE", "v2")
ENABLE_AUTO_CRM = env_bool("QLX_ENABLE_AUTO_CRM", False)
ENABLE_SERVER_ZALO = env_bool("QLX_ENABLE_SERVER_ZALO", False)
MACHINE_ALIASES = env_str("QLX_MACHINE_ALIASES", "")
