"""
전역 좌표 피커 (독립 프로세스).

확정: 좌클릭 또는 F8 (현재 커서 OS 좌표). Esc = 취소.
uvicorn/FastAPI 워커 스레드 안에서 pynput 훅이 불안정할 수 있어
별도 프로세스로 분리합니다. 결과는 stdout에 JSON 한 줄로 출력합니다.
"""
import json
import sys
import time


def main():
    try:
        from ctypes import windll, wintypes
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = wintypes.HANDLE(-4)
        windll.user32.SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE)
    except Exception:
        try:
            from ctypes import windll
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    from pynput import mouse, keyboard
    import pyautogui

    # UI 버튼 클릭이 같이 잡히지 않도록
    time.sleep(0.45)

    result = {"x": None, "y": None}
    done = {"flag": False}

    def finish(x, y):
        if done["flag"]:
            return False
        done["flag"] = True
        result["x"] = int(x)
        result["y"] = int(y)
        return False

    def on_click(x, y, button, pressed):
        if pressed and button == mouse.Button.left:
            return finish(x, y)

    def on_press(key):
        try:
            if key == keyboard.Key.esc:
                done["flag"] = True
                return False
            if key == keyboard.Key.f8:
                pos = pyautogui.position()
                return finish(pos.x, pos.y)
        except Exception:
            pass

    print("READY", flush=True)

    mouse_listener = mouse.Listener(on_click=on_click)
    key_listener = keyboard.Listener(on_press=on_press)
    mouse_listener.start()
    key_listener.start()

    while not done["flag"] and (mouse_listener.running or key_listener.running):
        time.sleep(0.05)

    try:
        mouse_listener.stop()
    except Exception:
        pass
    try:
        key_listener.stop()
    except Exception:
        pass

    if result["x"] is None:
        print(json.dumps({"cancelled": True}), flush=True)
        sys.exit(1)

    print(json.dumps({"x": result["x"], "y": result["y"]}), flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
