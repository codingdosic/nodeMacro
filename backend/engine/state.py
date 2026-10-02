import threading

from pynput import mouse, keyboard
import pyautogui

# 전역 콜백 저장소
_pick_callback = None
_mouse_listener = None
_key_listener = None

# 매크로 실행 중 노드 간 데이터 공유를 위한 상태 저장소
macro_state = {}
stop_event = threading.Event()

# 상태 알림용 콜백 (FastAPI에서 이 콜백을 WebSocket 브로드캐스트로 덮어쓸 예정)
status_callback = None
execution_callback = None

def update_status(message, key=None, **params):
    """현재 실행 상태를 알림"""
    if message:
        print(f"[STATUS] {message}")
    if status_callback:
        status_callback(message, key, params)

def update_execution(node_id, phase, message=None):
    """노드 실행 상태를 UI에 알림."""
    if execution_callback:
        execution_callback(node_id, phase, message)

def start_coordinate_picker(callback):
    """레거시 헬퍼. 웹 에디터는 coordinate_picker_cli를 사용합니다."""
    global _pick_callback, _mouse_listener, _key_listener
    _pick_callback = callback

    print("좌표 선택 모드 활성화: 클릭 또는 F8 확정 / Esc 취소 (레거시 경로)")

    stop_listeners()

    _mouse_listener = mouse.Listener(on_click=_on_global_click)
    _mouse_listener.start()
    _key_listener = keyboard.Listener(on_press=_on_key_press)
    _key_listener.start()

def start_key_picker(callback):
    """다음 키보드 입력을 가로채서 콜백으로 전달합니다."""
    global _pick_callback, _key_listener
    _pick_callback = callback

    stop_listeners()

    def on_press(key):
        key_name = ""
        try:
            if hasattr(key, 'char') and key.char:
                key_name = key.char
            else:
                key_name = str(key).replace("Key.", "")
                mapping = {
                    "cmd": "win",
                    "ctrl_l": "ctrl",
                    "ctrl_r": "ctrl",
                    "alt_l": "alt",
                    "alt_gr": "alt",
                    "shift_l": "shift",
                    "shift_r": "shift"
                }
                key_name = mapping.get(key_name, key_name)
        except:
            key_name = "unknown"

        _finish_picking(key_name)
        return False

    _key_listener = keyboard.Listener(on_press=on_press)
    _key_listener.start()

def stop_listeners():
    global _mouse_listener, _key_listener
    if _mouse_listener:
        _mouse_listener.stop()
        _mouse_listener = None
    if _key_listener:
        _key_listener.stop()
        _key_listener = None

def _on_global_click(x, y, button, pressed):
    if pressed and button == mouse.Button.left:
        _finish_picking(int(x), int(y))
        return False

def _on_key_press(key):
    try:
        if key == keyboard.Key.esc:
            _pick_callback_clear()
            return False
        if key == keyboard.Key.f8:
            x, y = pyautogui.position()
            _finish_picking(x, y)
            return False
    except Exception:
        pass


def _pick_callback_clear():
    global _pick_callback
    _pick_callback = None
    stop_listeners()

def _finish_picking(*args):
    global _pick_callback
    if _pick_callback:
        _pick_callback(*args)
        _pick_callback = None
    stop_listeners()
