import pyautogui
import time
from backend.nodes.base_node import BaseNode
from backend.engine import state


def _set_clipboard_text(text: str) -> bool:
    """Windows 유니코드 클립보드 설정. 한글 등 non-ASCII 입력용."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            payload = text.encode("utf-16-le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
            if not h_mem:
                return False
            ptr = kernel32.GlobalLock(h_mem)
            ctypes.memmove(ptr, payload, len(payload))
            kernel32.GlobalUnlock(h_mem)
            if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                kernel32.GlobalFree(h_mem)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception as exc:
        print(f"클립보드 설정 실패: {exc}")
        return False


def _type_text(text: str, interval: float = 0.05):
    """ASCII는 typewrite, 그 외(한글 포함)는 클립보드 붙여넣기."""
    if not text:
        return
    if text.isascii():
        pyautogui.typewrite(text, interval=interval)
        return
    if _set_clipboard_text(text):
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(max(0.05, float(interval or 0.05)))
    else:
        print("에러: 한글/유니코드 문자열을 입력하지 못했습니다 (클립보드 실패).")


def _find_window(title_query, activate=False):
    """제목에 title_query가 포함된 첫 번째 표시 창의 좌표를 반환."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    matches = []
    query = (title_query or "").strip().casefold()
    if not query:
        return None

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if query in buffer.value.casefold():
                matches.append((hwnd, buffer.value))
                return False
        return True

    user32.EnumWindows(collect, 0)
    if not matches:
        return None

    hwnd, title = matches[0]
    if activate:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return title, (rect.left, rect.top, rect.right, rect.bottom)


class AnchorNode(BaseNode):
    """에디터의 (0,0) 위치를 추적하기 위한 노드"""
    node_type = "anchor"
    node_label = "ORIGIN"

    def execute(self, macro_state):
        pass


class StartNode(BaseNode):
    node_type = "start"
    node_label = "시작"

    def execute(self, macro_state):
        delay = self.config.get("delay", 0)
        if delay > 0:
            print(f"매크로 시작 전 {delay}ms 대기 중...")
            state.stop_event.wait(delay / 1000.0)
        print("매크로 실행을 시작합니다.")
        return "output_pin"

    def get_schema(self):
        return {
            "delay": {"type": "number", "label": "지연(ms)", "default": 0}
        }


class WindowNode(BaseNode):
    node_type = "window"
    node_label = "창 선택"

    def execute(self, macro_state):
        result = _find_window(
            self.config.get("title", ""),
            bool(self.config.get("activate", True)),
        )
        if not result:
            raise RuntimeError(f"창을 찾을 수 없습니다: {self.config.get('title', '')}")
        title, rect = result
        macro_state["window_title"] = title
        macro_state["window_rect"] = rect
        return "output_pin"

    def get_schema(self):
        return {
            "title": {"type": "text", "label": "창 제목 포함", "default": ""},
            "activate": {"type": "checkbox", "label": "창 활성화", "default": True},
        }


class CoordNode(BaseNode):
    node_type = "click"  # 레거시 유지를 위해 click 사용
    node_label = "좌표 노드"

    def execute(self, macro_state):
        x = self.config.get("x", 0)
        y = self.config.get("y", 0)
        if self.config.get("relative_to_window", False):
            rect = macro_state.get("window_rect")
            if not rect:
                raise RuntimeError("창 기준 좌표에 필요한 '창 선택' 노드가 실행되지 않았습니다.")
            x += rect[0]
            y += rect[1]
        print(f"좌표 노드: ({x}, {y}) 저장")
        macro_state["target_pos"] = (x, y)
        return "output_pin"

    def get_schema(self):
        return {
            "x": {"type": "number", "label": "X", "default": 0},
            "y": {"type": "number", "label": "Y", "default": 0},
            "relative_to_window": {
                "type": "checkbox",
                "label": "창 기준 좌표",
                "default": False,
            },
        }


class WaitNode(BaseNode):
    node_type = "wait"
    node_label = "대기"

    def execute(self, macro_state):
        ms = self.config.get("ms", 1000)
        total_sec = ms / 1000.0
        print(f"대기 노드: {ms}ms 대기 중...")

        start_time = time.time()
        while time.time() - start_time < total_sec:
            remaining = total_sec - (time.time() - start_time)
            state.update_status(f"대기 중... {remaining:.1f}초 남음")
            if state.stop_event.wait(min(0.1, remaining)):
                break

        return "output_pin"

    def get_schema(self):
        return {
            "ms": {"type": "number", "label": "ms", "default": 1000}
        }


class BaseImageNode(BaseNode):
    """이미지 인식 노드들의 공통 부모 클래스"""

    def __init__(self, node_id, config=None):
        super().__init__(node_id, config)
        self.image_path = self.config.get("image_path")
        self.offset_x = self.config.get("offset_x", 0)
        self.offset_y = self.config.get("offset_y", 0)
        self.img_size = self.config.get("img_size", [1, 1])
        self.search_region = self.config.get("search_region")

    def _get_search_region(self):
        region = self.config.get("search_region", self.search_region)
        if region is None:
            return None
        if isinstance(region, (list, tuple)) and len(region) == 4:
            return tuple(region)
        return region

    def _find_image(self):
        """공통 이미지 검색 로직 (구 Dear PyGui BaseImageNode와 동일)"""
        from backend.engine.capture import _grab_all_screens, _virtual_screen_rect

        image_path = self.config.get("image_path", self.image_path)
        if not image_path:
            return None

        max_wait = self.config.get("wait_time", 5.0)
        interval = self.config.get("interval", 0.1)
        conf = self.config.get("threshold", 0.8)
        offset_x = self.config.get("offset_x", self.offset_x)
        offset_y = self.config.get("offset_y", self.offset_y)
        search_region = self._get_search_region()

        start_time = time.time()
        while True:
            try:
                vx, vy, vw, vh = _virtual_screen_rect()
                screen = _grab_all_screens()
                if screen.size != (vw, vh):
                    screen = screen.resize((vw, vh))

                origin_x, origin_y = vx, vy
                if search_region:
                    x, y, width, height = map(int, search_region)
                    screen = screen.crop((x - vx, y - vy, x - vx + width, y - vy + height))
                    origin_x, origin_y = x, y

                match = pyautogui.locate(image_path, screen, confidence=conf)
                if match:
                    center = pyautogui.center(match)
                    return (
                        origin_x + center.x + offset_x,
                        origin_y + center.y + offset_y,
                    )
            except Exception:
                pass

            if time.time() - start_time >= max_wait:
                break
            if interval > 0 and state.stop_event.wait(interval):
                break
        return None

    def _image_schema(self, include_offset=True):
        schema = {
            "wait_time": {"type": "number", "label": "검색(초)", "default": 5.0},
            "interval": {"type": "number", "label": "간격(s)", "default": 0.1},
            "threshold": {"type": "number", "label": "감도", "default": 0.8},
        }
        if include_offset:
            schema["offset_x"] = {"type": "number", "label": "X 오프셋(중앙)", "default": 0}
            schema["offset_y"] = {"type": "number", "label": "Y 오프셋(중앙)", "default": 0}
        return schema


class ImageNode(BaseImageNode):
    node_type = "image"
    node_label = "이미지 노드"

    def execute(self, macro_state):
        pos = self._find_image()
        if pos:
            macro_state["target_pos"] = pos
        else:
            macro_state.pop("target_pos", None)
        return "output_pin"

    def get_schema(self):
        return self._image_schema(include_offset=True)


class IfNode(BaseImageNode):
    node_type = "if"
    node_label = "조건문(이미지)"

    def execute(self, macro_state):
        pos = self._find_image()
        if pos:
            macro_state["target_pos"] = pos
            return "true_out_pin"
        macro_state.pop("target_pos", None)
        return "false_out_pin"

    def get_schema(self):
        # 조건문 노드는 클릭 지점(오프셋) 설정이 필요 없음
        return self._image_schema(include_offset=False)


class MouseClickNode(BaseNode):
    node_type = "mouse_click"
    node_label = "마우스 입력"

    def execute(self, macro_state):
        pos = macro_state.get("target_pos")
        btn_type = self.config.get("button", "좌클릭")
        duration = self.config.get("duration", 0.0)

        if pos:
            x, y = pos
            if btn_type == "좌클릭":
                if duration > 0:
                    print(f"좌클릭 꾹 누르기: {duration}s 위치: ({x}, {y})")
                    pyautogui.mouseDown(x, y, button="left")
                    try:
                        state.stop_event.wait(duration)
                    finally:
                        pyautogui.mouseUp(x, y, button="left")
                else:
                    pyautogui.click(x, y)
            elif btn_type == "우클릭":
                if duration > 0:
                    print(f"우클릭 꾹 누르기: {duration}s 위치: ({x}, {y})")
                    pyautogui.mouseDown(x, y, button="right")
                    try:
                        state.stop_event.wait(duration)
                    finally:
                        pyautogui.mouseUp(x, y, button="right")
                else:
                    pyautogui.rightClick(x, y)
            elif btn_type == "더블클릭":
                pyautogui.doubleClick(x, y)
            print(f"마우스 클릭 실행: {btn_type} 위치: ({x}, {y})")
        else:
            print("에러: 클릭할 목표 좌표가 없습니다.")
        return "output_pin"

    def get_schema(self):
        return {
            "button": {
                "type": "select",
                "label": "버튼",
                "options": ["좌클릭", "우클릭", "더블클릭"],
                "default": "좌클릭",
            },
            "duration": {
                "type": "number",
                "label": "지속 시간(s)",
                "default": 0.0,
            },
        }


class LoopNode(BaseNode):
    node_type = "loop"
    node_label = "반복문"

    def __init__(self, node_id, config=None):
        super().__init__(node_id, config)
        self.current_count = 0

    def reset(self):
        self.current_count = 0

    def execute(self, macro_state):
        max_count = self.config.get("max_count", 5)
        self.current_count += 1
        if self.current_count <= max_count:
            return "loop_out_pin"
        self.current_count = 0
        return "exit_out_pin"

    def get_schema(self):
        return {
            "max_count": {"type": "number", "label": "횟수", "default": 5}
        }


class KeyboardNode(BaseNode):
    node_type = "keyboard"
    node_label = "키보드 입력"

    @staticmethod
    def _normalize_key(key):
        # 가상 키코드 보정 (한영키 <21> -> hangul)
        if key == "<21>":
            return "hangul"
        return key

    def _get_keys(self):
        keys = self.config.get("keys", ["enter"])
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",") if k.strip()]
        return [self._normalize_key(k) for k in keys if k]

    def execute(self, macro_state):
        mode = self.config.get("mode", "단축키")
        if mode == "단축키":
            valid_keys = self._get_keys()
            if valid_keys:
                pyautogui.hotkey(*valid_keys)
        else:
            string_val = self.config.get("string", "")
            interval = self.config.get("interval", 0.05)
            hangul_typewrite = bool(self.config.get("hangul_typewrite", False))
            if hangul_typewrite:
                from backend.engine.hangul_type import type_text_as_keys
                type_text_as_keys(string_val, interval=interval)
            else:
                _type_text(string_val, interval=interval)
        return "output_pin"

    def get_schema(self):
        return {
            "mode": {
                "type": "select",
                "label": "모드",
                "options": ["단축키", "문자열"],
                "default": "단축키",
            },
            "keys": {
                "type": "text",
                "label": "Keys (Hotkey 조합)",
                "default": ["enter"],
            },
            "string": {
                "type": "text",
                "label": "Typing 문자열",
                "default": "",
                "multiline": True,
            },
            "hangul_typewrite": {
                "type": "checkbox",
                "label": "한글 타자 입력(두벌식)",
                "default": False,
            },
            "interval": {
                "type": "number",
                "label": "간격(s)",
                "default": 0.05,
            },
        }


class MouseMoveNode(BaseNode):
    node_type = "mouse_move"
    node_label = "마우스 이동"

    def execute(self, macro_state):
        pos = macro_state.get("target_pos")
        dur = self.config.get("duration", 0.2)
        if pos:
            print(f"마우스 이동: ({pos[0]}, {pos[1]})")
            pyautogui.moveTo(pos[0], pos[1], duration=dur)
        else:
            print("에러: 이동할 목표 좌표가 없습니다.")
        return "output_pin"

    def get_schema(self):
        return {
            "duration": {"type": "number", "label": "시간(s)", "default": 0.2}
        }


class MouseScrollNode(BaseNode):
    node_type = "mouse_scroll"
    node_label = "마우스 스크롤"

    def execute(self, macro_state):
        amt = self.config.get("amount", -100)
        print(f"마우스 스크롤: {amt}")
        pyautogui.scroll(amt)
        return "output_pin"

    def get_schema(self):
        return {
            "amount": {"type": "number", "label": "양", "default": -100}
        }


class MouseDragNode(BaseNode):
    node_type = "mouse_drag"
    node_label = "마우스 드래그"

    def execute(self, macro_state):
        pos = macro_state.get("target_pos")
        dur = self.config.get("duration", 0.5)
        if pos:
            print(f"마우스 드래그 시작: {pyautogui.position()} -> 끝: {pos}")
            pyautogui.dragTo(pos[0], pos[1], duration=dur)
        else:
            print("에러: 드래그할 목표 좌표가 없습니다.")
        return "output_pin"

    def get_schema(self):
        return {
            "duration": {"type": "number", "label": "시간(s)", "default": 0.5}
        }
