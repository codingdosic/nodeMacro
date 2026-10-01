import dearpygui.dearpygui as dpg
from pynput import mouse, keyboard
import pyautogui

# 전역 콜백 저장소
_pick_callback = None
_mouse_listener = None
_key_listener = None

# 매크로 실행 중 노드 간 데이터 공유를 위한 상태 저장소
macro_state = {}

def update_status(message):
    """화면 우상단 오버레이에 메시지 표시"""
    if dpg.does_item_exist("status_overlay_text"):
        dpg.set_value("status_overlay_text", message)
    # console 출력도 병행
    if message:
        print(f"[STATUS] {message}")

def start_coordinate_picker(callback):
    """전역 리스너를 시작하여 화면 클릭이나 'Z' 키 입력 시 좌표를 가져옵니다."""
    global _pick_callback, _mouse_listener, _key_listener
    _pick_callback = callback
    
    print("좌표 선택 모드 활성화: 화면을 클릭하거나 'Z' 키를 누르세요.")
    
    # 기존 리스너 중지
    stop_listeners()
    
    # 마우스 클릭 리스너
    _mouse_listener = mouse.Listener(on_click=_on_global_click)
    _mouse_listener.start()
    
    # 키보드 리스너 (Z 키)
    _key_listener = keyboard.Listener(on_press=_on_key_press)
    _key_listener.start()

def start_key_picker(callback):
    """다음 키보드 입력을 가로채서 콜백으로 전달합니다."""
    global _pick_callback, _key_listener
    _pick_callback = callback
    
    stop_listeners()
    
    def on_press(key):
        # pynput 키 객체를 문자열로 변환 (pyautogui 호환용)
        key_name = ""
        try:
            if hasattr(key, 'char') and key.char:
                key_name = key.char
            else:
                # 특수 키 이름 추출 (Key.enter -> 'enter')
                key_name = str(key).replace("Key.", "")
                
                # PyAutoGUI 호환성을 위한 매핑
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
        return False # 리스너 중지

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
        # 'z' 또는 'Z' 키 확인
        if hasattr(key, 'char') and key.char.lower() == 'z':
            # 현재 마우스 커서 위치 획득
            x, y = pyautogui.position()
            _finish_picking(x, y)
            return False
    except AttributeError:
        pass

def _finish_picking(*args):
    global _pick_callback
    if _pick_callback:
        # 좌표(x, y)나 키 이름(key_name) 등 전달받은 인자 그대로 콜백 실행
        _pick_callback(*args)
        _pick_callback = None
    stop_listeners()
