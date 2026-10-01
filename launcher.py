import argparse
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
import webbrowser

from backend.config import (
    APP_ID, APP_NAME, APP_VERSION, HOST, INSTANCE_MUTEX, LOG_DIR, PACKAGE_DIR,
    PORT, SCRIPTS_DIR, SESSION_TOKEN,
)


BASE_URL = f"http://{HOST}:{PORT}"
_instance_mutex = None


def editor_url(language=None):
    code = {"english": "en", "korean": "ko", "en": "en", "ko": "ko"}.get(language)
    return f"{BASE_URL}/?{urllib.parse.urlencode({'lang': code})}" if code else BASE_URL


def acquire_instance_mutex():
    global _instance_mutex
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateMutexW(None, False, INSTANCE_MUTEX)
    if not handle:
        raise ctypes.WinError()
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return False
    _instance_mutex = handle
    return True


def release_instance_mutex():
    global _instance_mutex
    if _instance_mutex:
        kernel32 = ctypes.windll.kernel32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(_instance_mutex)
        _instance_mutex = None


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[RotatingFileHandler(LOG_DIR / "d5macro.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")],
    )


def health():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=0.7) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def wait_until_ready(timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = health()
        if status and status.get("app") == APP_ID:
            return True
        time.sleep(0.15)
    return False


def port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((HOST, PORT)) == 0


def post_json(path, payload):
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-D5-Token": SESSION_TOKEN},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def run_script(path):
    absolute = os.path.abspath(path)
    scripts_root = os.path.abspath(SCRIPTS_DIR)
    if os.path.commonpath([absolute, scripts_root]) != scripts_root:
        raise ValueError(f"스크립트는 {scripts_root} 아래에 있어야 합니다.")
    relative = os.path.relpath(absolute, scripts_root).replace("\\", "/")
    result = post_json("/api/scripts/run", {"path": relative})
    if result.get("status") not in {"started", "success"}:
        raise RuntimeError(result.get("message", "매크로 실행에 실패했습니다."))


def start_server():
    import uvicorn
    from backend.main import app

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, daemon=True, name="d5macro-server")
    thread.start()
    return server, thread


def restart_as_admin(server):
    server.should_exit = True
    deadline = time.time() + 5
    while health() and time.time() < deadline:
        time.sleep(0.1)
    release_instance_mutex()
    if getattr(sys, "frozen", False):
        executable, params = sys.executable, ""
    else:
        executable, params = sys.executable, f'"{os.path.abspath(__file__)}"'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)


def show_tray(server):
    try:
        import pystray
        from PIL import Image
    except ImportError:
        logging.warning("pystray가 없어 콘솔 종료 전까지 서버를 유지합니다.")
        while not server.should_exit:
            time.sleep(0.5)
        return

    icon_path = PACKAGE_DIR / "branding" / "d5macro.png"
    image = Image.open(icon_path)

    def open_editor(icon=None, item=None):
        webbrowser.open(BASE_URL)

    def elevate(icon, item):
        icon.stop()
        restart_as_admin(server)

    def quit_app(icon, item):
        server.should_exit = True
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("D5 Macro 열기", open_editor, default=True),
        pystray.MenuItem("관리자 권한으로 다시 시작", elevate),
        pystray.MenuItem("종료", quit_app),
    )
    pystray.Icon(APP_ID, image, f"{APP_NAME} {APP_VERSION}", menu).run()


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--run-script")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--coordinate-picker", action="store_true")
    parser.add_argument("--language", choices=("english", "korean", "en", "ko"))
    args = parser.parse_args()

    if args.coordinate_picker:
        from backend.engine.coordinate_picker_cli import main as picker_main
        picker_main()
        return

    setup_logging()
    current = health()
    if current:
        if current.get("app") != APP_ID:
            raise RuntimeError(f"포트 {PORT}을 다른 프로그램이 사용 중입니다.")
        if args.run_script:
            run_script(args.run_script)
        elif not args.no_browser:
            webbrowser.open(editor_url(args.language))
        return


    if not acquire_instance_mutex():
        if wait_until_ready(timeout=5):
            if args.run_script:
                run_script(args.run_script)
            elif not args.no_browser:
                webbrowser.open(editor_url(args.language))
            return
        raise RuntimeError("D5 Macro가 시작 중이거나 종료 중입니다. 잠시 후 다시 실행하세요.")

    try:
        if port_in_use():
            raise RuntimeError(f"포트 {PORT}을 다른 프로그램이 사용 중입니다.")
        server, thread = start_server()
        if not wait_until_ready():
            server.should_exit = True
            raise RuntimeError("D5 Macro 서버를 시작하지 못했습니다. 로그를 확인하세요.")
        if args.run_script:
            run_script(args.run_script)
        elif not args.no_browser:
            webbrowser.open(editor_url(args.language))
        show_tray(server)
        thread.join(timeout=3)
    finally:
        release_instance_mutex()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("D5 Macro failed")
        ctypes.windll.user32.MessageBoxW(None, str(exc), APP_NAME, 0x10)
        raise SystemExit(1)
