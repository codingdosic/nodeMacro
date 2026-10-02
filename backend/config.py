import os
import secrets
import sys
import ctypes
import json
from pathlib import Path


APP_NAME = "D5 Macro"
APP_ID = "d5macro"
APP_VERSION = "1.0.5"
SCRIPT_FORMAT = "d5macro"
SCRIPT_SCHEMA_VERSION = 1
HOST = "127.0.0.1"
PORT = 8000
INSTANCE_MUTEX = "D5Macro.App.Singleton.B06F6C40-A7D4-4DC4-90E2-BB8EB01B7917"
HOTKEY_CHOICES = ("esc", "pause", *(f"f{i}" for i in range(1, 13)))
DEFAULT_SETTINGS = {"record_stop_key": "f8", "panic_stop_key": "esc"}

PACKAGE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _known_folder(csidl: int, fallback: Path):
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) == 0:
            return Path(buffer.value)
    return fallback


LOCAL_DATA_DIR = Path(os.environ.get(
    "D5MACRO_DATA_DIR",
    _known_folder(28, Path(os.environ.get("LOCALAPPDATA", Path.home()))) / "D5Macro",
))
SCRIPTS_DIR = Path(os.environ.get(
    "D5MACRO_SCRIPTS_DIR",
    _known_folder(5, Path.home() / "Documents") / "D5Macro" / "scripts",
))
CAPTURES_DIR = LOCAL_DATA_DIR / "captures"
LOG_DIR = LOCAL_DATA_DIR / "logs"
SESSION_KEY_FILE = LOCAL_DATA_DIR / "session.key"
SETTINGS_FILE = LOCAL_DATA_DIR / "settings.json"


def ensure_directories():
    for path in (LOCAL_DATA_DIR, SCRIPTS_DIR, CAPTURES_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def session_token():
    ensure_directories()
    try:
        token = SESSION_KEY_FILE.read_text(encoding="ascii").strip()
    except OSError:
        token = ""
    if len(token) < 32:
        token = secrets.token_urlsafe(32)
        SESSION_KEY_FILE.write_text(token, encoding="ascii")
    return token


def normalize_settings(values=None):
    settings = {**DEFAULT_SETTINGS, **(values or {})}
    normalized = {
        key: str(settings[key]).strip().lower()
        for key in DEFAULT_SETTINGS
    }
    if any(value not in HOTKEY_CHOICES for value in normalized.values()):
        raise ValueError("지원하지 않는 단축키입니다.")
    if normalized["record_stop_key"] == normalized["panic_stop_key"]:
        raise ValueError("녹화 종료 키와 패닉 스탑 키는 서로 달라야 합니다.")
    return normalized


def load_settings():
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return normalize_settings(saved)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)


SETTINGS = load_settings()


def get_setting(name):
    return SETTINGS.get(name, DEFAULT_SETTINGS.get(name))


def save_settings(values):
    updated = normalize_settings({**SETTINGS, **values})
    temporary = SETTINGS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SETTINGS_FILE)
    SETTINGS.clear()
    SETTINGS.update(updated)
    return dict(SETTINGS)


ensure_directories()
SESSION_TOKEN = session_token()
