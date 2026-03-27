import dearpygui.dearpygui as dpg
import pyautogui
import time
import os
from src.nodes.base_node import BaseNode
from src.engine import state

class AnchorNode(BaseNode):
    """에디터의 (0,0) 위치를 추적하기 위한 노드"""
    node_type = "anchor"
    def __init__(self):
        super().__init__("ORIGIN", (0, 0))
        self.width = 1

    def create_ui(self, parent):
        with dpg.node(label="ORIGIN", parent=parent, pos=(0, 0), tag="origin_anchor", draggable=False):
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                dpg.add_text("(0,0)", color=(150, 150, 150))

    def execute(self): pass
    def get_config(self): return None
    def apply_config(self, data): pass

class StartNode(BaseNode):
    node_type = "start"
    def __init__(self, pos=(10, 10)):
        super().__init__("시작", pos)
        self.width = 150

    def create_ui(self, parent):
        with dpg.node(label=self.label, parent=parent, pos=self.pos) as self.node_id:
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                with dpg.group(width=self.width):
                    dpg.add_text("매크로 시작점", color=(100, 200, 255))
            
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as self.output_pin:
                with dpg.group(width=self.width):
                    dpg.add_text("Out", indent=self.width - 30)

    def execute(self):
        print("매크로 실행을 시작합니다.")

class CoordNode(BaseNode):
    node_type = "click" # 레거시 유지를 위해 click 사용
    def __init__(self, pos=(10, 10)):
        super().__init__("좌표 노드", pos)

    def _add_widgets(self):
        with dpg.group(horizontal=True):
            dpg.add_text("X:")
            self.x_input = dpg.add_input_int(default_value=0, width=80, step=0)
        with dpg.group(horizontal=True):
            dpg.add_text("Y:")
            self.y_input = dpg.add_input_int(default_value=0, width=80, step=0)
        
        dpg.add_button(label="좌표 선택 (좌클릭 or Z키)", callback=self._pick_coordinate, width=120)

    def _pick_coordinate(self):
        state.start_coordinate_picker(self._on_coordinate_picked)

    def _on_coordinate_picked(self, x, y):
        dpg.set_value(self.x_input, x)
        dpg.set_value(self.y_input, y)

    def execute(self):
        x = dpg.get_value(self.x_input)
        y = dpg.get_value(self.y_input)
        print(f"좌표 노드: ({x}, {y}) 저장")
        state.macro_state["target_pos"] = (x, y)
        return self.output_pin

    def get_config(self):
        config = super().get_config()
        config["data"] = {
            "x": dpg.get_value(self.x_input),
            "y": dpg.get_value(self.y_input)
        }
        return config

    def apply_config(self, data):
        dpg.set_value(self.x_input, data.get("x", 0))
        dpg.set_value(self.y_input, data.get("y", 0))

class WaitNode(BaseNode):
    node_type = "wait"
    def __init__(self, pos=(10, 10)):
        super().__init__("대기", pos)

    def _add_widgets(self):
        self.ms_input = dpg.add_input_int(label="ms", default_value=1000, width=80)

    def execute(self):
        ms = dpg.get_value(self.ms_input)
        print(f"대기 노드: {ms}ms 대기 중...")
        time.sleep(ms / 1000.0)
        return self.output_pin

    def get_config(self):
        config = super().get_config()
        config["data"] = {"ms": dpg.get_value(self.ms_input)}
        return config

    def apply_config(self, data):
        dpg.set_value(self.ms_input, data.get("ms", 1000))

class BaseImageNode(BaseNode):
    """이미지 인식 노드들의 공통 부모 클래스"""
    def __init__(self, label, pos=(10, 10)):
        super().__init__(label, pos)
        self.width = 200
        self.image_path = None
        self.offset_x = 0
        self.offset_y = 0
        self.img_size = [1, 1]
        self.search_region = None
        
        # 위젯 태그들
        self.texture_tag = self.get_tag("tex")
        self.image_widget_tag = self.get_tag("img_widget")
        self.draw_list_tag = self.get_tag("draw_list")
        self.region_text_tag = self.get_tag("region_text")
        self.cross_tag = self.get_tag("cross")

    def _add_image_widgets(self, show_offset=True):
        self.show_offset = show_offset
        with dpg.group(horizontal=True):
            dpg.add_button(label="이미지 캡처", callback=lambda: self._capture_image(delay=0), width=85)
            dpg.add_button(label="3초 뒤 캡처", callback=lambda: self._capture_image(delay=3), width=85)
        
        with dpg.group():
            click_cb = self._on_image_click if self.show_offset else None
            with dpg.drawlist(width=180, height=120, tag=self.draw_list_tag, callback=click_cb):
                dpg.draw_image("default_none", [0, 0], [180, 120], tag=self.image_widget_tag)
                if self.show_offset:
                    self._draw_crosshair()
        
        if self.show_offset:
            dpg.add_text("클릭 지점 (미리보기 클릭)", color=(150, 150, 150))
            with dpg.group(horizontal=True):
                dpg.add_text("X 오프셋:")
                self.off_x_input = dpg.add_input_int(default_value=0, width=110, step=0, callback=self._on_offset_manual)
            with dpg.group(horizontal=True):
                dpg.add_text("Y 오프셋:")
                self.off_y_input = dpg.add_input_int(default_value=0, width=110, step=0, callback=self._on_offset_manual)

        dpg.add_spacer(height=5)
        dpg.add_text("-" * 30, color=(80, 80, 80))
        dpg.add_spacer(height=5)
        with dpg.group(horizontal=True):
            dpg.add_text("탐색 영역:", color=(200, 200, 100))
            dpg.add_text("전체 화면", tag=self.region_text_tag, color=(150, 150, 150))
        
        dpg.add_button(label="영역 설정", callback=self._set_search_region, width=180)
        dpg.add_button(label="영역 초기화", callback=self._reset_search_region, width=180)
        dpg.add_spacer(height=5)
        dpg.add_text("-" * 30, color=(80, 80, 80))
        dpg.add_spacer(height=5)
        
        self.wait_time_input = dpg.add_input_float(label="검색(초)", default_value=5.0, width=80)
        self.interval_input = dpg.add_input_float(label="간격(s)", default_value=0.1, width=80)
        self.threshold_input = dpg.add_slider_float(label="감도", default_value=0.8, min_value=0.1, max_value=1.0, width=80)

    def _draw_crosshair(self):
        if dpg.does_alias_exist(self.cross_tag): dpg.delete_item(self.cross_tag)
        scale_x, scale_y = 180 / max(1, self.img_size[0]), 120 / max(1, self.img_size[1])
        px, py = 90 + (self.offset_x * scale_x), 60 + (self.offset_y * scale_y)
        with dpg.draw_node(tag=self.cross_tag, parent=self.draw_list_tag):
            dpg.draw_line([px - 10, py], [px + 10, py], color=(255, 0, 0), thickness=2)
            dpg.draw_line([px, py - 10], [px, py + 10], color=(255, 0, 0), thickness=2)
            dpg.draw_circle([px, py], 4, color=(255, 255, 0))

    def _on_image_click(self):
        m_pos = dpg.get_drawing_mouse_pos()
        dx, dy = m_pos[0] - 90, m_pos[1] - 60
        scale_x, scale_y = self.img_size[0] / 180, self.img_size[1] / 120
        self.offset_x, self.offset_y = int(dx * scale_x), int(dy * scale_y)
        dpg.set_value(self.off_x_input, self.offset_x)
        dpg.set_value(self.off_y_input, self.offset_y)
        self._draw_crosshair()

    def _on_offset_manual(self):
        self.offset_x, self.offset_y = dpg.get_value(self.off_x_input), dpg.get_value(self.off_y_input)
        self._draw_crosshair()

    def _capture_image(self, delay=0):
        from src.engine import capture
        capture.start_capture_tool(self._on_image_captured, delay=delay)

    def _on_image_captured(self, file_path):
        self.image_path = file_path
        try:
            width, height, _, data = dpg.load_image(file_path)
            self.img_size = [width, height]
            new_texture = self.get_tag(f"tex_{int(time.time())}")
            dpg.add_static_texture(width=width, height=height, default_value=data, tag=new_texture, parent="main_texture_registry")
            if dpg.does_item_exist(self.texture_tag): dpg.delete_item(self.texture_tag)
            self.texture_tag = new_texture
            if dpg.does_item_exist(self.image_widget_tag): dpg.delete_item(self.image_widget_tag)
            dpg.draw_image(self.texture_tag, [0, 0], [180, 120], tag=self.image_widget_tag, parent=self.draw_list_tag, before=self.cross_tag)
            self._draw_crosshair()
        except Exception as e: print(f"이미지 갱신 오류: {e}")

    def _set_search_region(self):
        from src.engine import capture
        capture.start_region_tool(self._on_region_set)

    def _on_region_set(self, x, y, w, h):
        self.search_region = (x, y, w, h)
        dpg.set_value(self.region_text_tag, f"({x},{y},{w},{h})")

    def _reset_search_region(self):
        self.search_region = None
        dpg.set_value(self.region_text_tag, "전체 화면")

    def _find_image(self):
        """공통 이미지 검색 로직"""
        if not self.image_path: return None
        max_wait = dpg.get_value(self.wait_time_input)
        interval = dpg.get_value(self.interval_input)
        conf = dpg.get_value(self.threshold_input)
        
        start_time = time.time()
        while True:
            try:
                pos = pyautogui.locateCenterOnScreen(self.image_path, confidence=conf, region=self.search_region)
                if pos: return (pos[0] + self.offset_x, pos[1] + self.offset_y)
            except: pass
            
            # 최대 검색 시간 체크
            if time.time() - start_time >= max_wait: break
            # 사용자 지정 간격만큼 대기
            if interval > 0: time.sleep(interval)
        return None

    def get_config(self):
        config = super().get_config()
        config["data"] = {
            "image_path": self.image_path, "wait_time": dpg.get_value(self.wait_time_input),
            "threshold": dpg.get_value(self.threshold_input), "offset_x": self.offset_x,
            "offset_y": self.offset_y, "img_size": self.img_size, "search_region": self.search_region
        }
        return config

    def apply_config(self, data):
        self.image_path = data.get("image_path")
        self.offset_x, self.offset_y = data.get("offset_x", 0), data.get("offset_y", 0)
        self.img_size = data.get("img_size", [1, 1])
        self.search_region = data.get("search_region")
        dpg.set_value(self.wait_time_input, data.get("wait_time", 5.0))
        dpg.set_value(self.threshold_input, data.get("threshold", 0.8))
        dpg.set_value(self.off_x_input, self.offset_x)
        dpg.set_value(self.off_y_input, self.offset_y)
        self._reset_search_region() if not self.search_region else dpg.set_value(self.region_text_tag, str(self.search_region))
        if self.image_path and os.path.exists(self.image_path): self._on_image_captured(self.image_path)

class ImageNode(BaseImageNode):
    node_type = "image"
    def __init__(self, pos=(10, 10)):
        super().__init__("이미지 노드", pos)

    def _add_widgets(self):
        self._add_image_widgets()

    def execute(self):
        pos = self._find_image()
        if pos: state.macro_state["target_pos"] = pos
        return self.output_pin

class IfNode(BaseImageNode):
    node_type = "if"
    def __init__(self, pos=(10, 10)):
        super().__init__("조건문(이미지)", pos)
        self.true_out_pin = None
        self.false_out_pin = None

    def create_ui(self, parent):
        with dpg.node(label=self.label, parent=parent, pos=self.pos) as self.node_id:
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input) as self.input_pin:
                dpg.add_text("In")
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                with dpg.group(width=self.width):
                    # 조건문 노드에서는 클릭 지점 설정이 필요 없으므로 False 전달
                    self._add_image_widgets(show_offset=False)
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as self.true_out_pin:
                dpg.add_text("True (발견)", indent=self.width - 80)
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as self.false_out_pin:
                dpg.add_text("False (미발견)", indent=self.width - 95)

    def execute(self):
        pos = self._find_image()
        if pos:
            state.macro_state["target_pos"] = pos
            return self.true_out_pin
        return self.false_out_pin

class MouseClickNode(BaseNode):
    node_type = "mouse_click"
    def __init__(self, pos=(10, 10)):
        super().__init__("마우스 입력", pos)

    def _add_widgets(self):
        self.button_input = dpg.add_combo(items=["좌클릭", "우클릭", "더블클릭"], default_value="좌클릭", width=120)

    def execute(self):
        pos = state.macro_state.get("target_pos")
        btn_type = dpg.get_value(self.button_input)
        if pos:
            x, y = pos
            if btn_type == "좌클릭": pyautogui.click(x, y)
            elif btn_type == "우클릭": pyautogui.rightClick(x, y)
            elif btn_type == "더블클릭": pyautogui.doubleClick(x, y)
            print(f"마우스 클릭 실행: {btn_type} 위치: ({x}, {y})")
        else:
            print("에러: 클릭할 목표 좌표가 없습니다.")
        return self.output_pin

    def get_config(self):
        config = super().get_config()
        config["data"] = {"button": dpg.get_value(self.button_input)}
        return config

    def apply_config(self, data):
        dpg.set_value(self.button_input, data.get("button", "좌클릭"))

class LoopNode(BaseNode):
    node_type = "loop"
    def __init__(self, pos=(10, 10)):
        super().__init__("반복문", pos)
        self.current_count = 0
        self.loop_out_pin = None
        self.exit_out_pin = None
        self.text_tag = self.get_tag("loop_text")

    def create_ui(self, parent):
        with dpg.node(label=self.label, parent=parent, pos=self.pos) as self.node_id:
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input) as self.input_pin:
                dpg.add_text("In")
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                with dpg.group(width=self.width):
                    self.max_count_input = dpg.add_input_int(label="횟수", default_value=5, width=80)
                    dpg.add_text("진행: 0", tag=self.text_tag)
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as self.loop_out_pin:
                dpg.add_text("Loop", indent=self.width - 45)
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as self.exit_out_pin:
                dpg.add_text("Exit", indent=self.width - 40)

    def reset(self):
        self.current_count = 0
        if dpg.does_item_exist(self.text_tag): dpg.set_value(self.text_tag, "진행: 0")

    def execute(self):
        max_count = dpg.get_value(self.max_count_input)
        self.current_count += 1
        if dpg.does_item_exist(self.text_tag): dpg.set_value(self.text_tag, f"진행: {self.current_count}")
        if self.current_count <= max_count: return self.loop_out_pin
        else:
            self.current_count = 0
            return self.exit_out_pin

    def get_config(self):
        config = super().get_config()
        config["data"] = {"max_count": dpg.get_value(self.max_count_input)}
        return config

    def apply_config(self, data):
        dpg.set_value(self.max_count_input, data.get("max_count", 5))

class KeyboardNode(BaseNode):
    node_type = "keyboard"
    def __init__(self, pos=(10, 10)):
        super().__init__("키보드 입력", pos)
        self.width = 180
        self.keys = ["enter"]
        self.mode = "단축키"
        self.slot_tags = []
        self.hotkey_group = self.get_tag("hotkey_group")
        self.type_group = self.get_tag("type_group")
        self.slot_container = self.get_tag("slot_container")

    def _add_widgets(self):
        self.mode_combo = dpg.add_combo(items=["단축키", "문자열"], default_value=self.mode, width=160, callback=self._on_mode_change)
        dpg.add_spacer(height=5)
        dpg.add_text("-" * 30, color=(80, 80, 80))
        dpg.add_spacer(height=5)
        with dpg.group(tag=self.hotkey_group, show=(self.mode == "단축키")):
            dpg.add_text("Keys (Hotkey 조합):", color=(200, 200, 100))
            dpg.add_group(tag=self.slot_container)
            dpg.add_button(label="[+] 키 추가", width=-1, callback=self._add_key_slot)
        with dpg.group(tag=self.type_group, show=(self.mode == "문자열")):
            dpg.add_text("Typing 문자열:", color=(200, 200, 100))
            self.string_input = dpg.add_input_text(multiline=True, width=160, height=60)
            self.interval_input = dpg.add_input_float(label="간격(s)", default_value=0.05, width=100)
        self._render_slots()

    def _on_mode_change(self):
        self.mode = dpg.get_value(self.mode_combo)
        dpg.configure_item(self.hotkey_group, show=(self.mode == "단축키"))
        dpg.configure_item(self.type_group, show=(self.mode == "문자열"))
        # [핵심] 모드 전환 시 렌더링 리셋에 따른 재바인딩
        if dpg.does_item_exist(self.string_input):
            dpg.bind_item_font(self.string_input, "korean_font")

    def _render_slots(self):
        for tag in self.slot_tags:
            if dpg.does_item_exist(tag): dpg.delete_item(tag)
        self.slot_tags.clear()
        for i, k_val in enumerate(self.keys):
            with dpg.group(horizontal=True, parent=self.slot_container) as row_tag:
                self.slot_tags.append(row_tag)
                input_tag = dpg.add_input_text(default_value=k_val, width=80)
                dpg.add_button(label="REC", width=40, callback=lambda s, a, u: self._record_key(u), user_data=input_tag)
                if len(self.keys) > 1:
                    dpg.add_button(label="X", width=25, callback=lambda s, a, u: self._remove_key_slot(u), user_data=i)

    def _add_key_slot(self):
        self._sync_keys_from_ui()
        self.keys.append("enter")
        self._render_slots()

    def _remove_key_slot(self, index):
        self._sync_keys_from_ui()
        self.keys.pop(index)
        self._render_slots()

    def _sync_keys_from_ui(self):
        new_keys = []
        for tag in self.slot_tags:
            children = dpg.get_item_children(tag, 1)
            if children:
                val = dpg.get_value(children[0])
                # [보정] 가상 키코드 보정 (한영키 <21> -> hangul)
                if val == "<21>":
                    val = "hangul"
                new_keys.append(val)
        self.keys = new_keys

    def _record_key(self, target_input_tag):
        state.start_key_picker(lambda k: (dpg.set_value(target_input_tag, k), self._sync_keys_from_ui()))

    def execute(self):
        self.mode = dpg.get_value(self.mode_combo)
        if self.mode == "단축키":
            self._sync_keys_from_ui()
            valid_keys = [k for k in self.keys if k]
            if valid_keys: pyautogui.hotkey(*valid_keys)
        else:
            pyautogui.typewrite(dpg.get_value(self.string_input), interval=dpg.get_value(self.interval_input))
        return self.output_pin

    def get_config(self):
        self._sync_keys_from_ui()
        config = super().get_config()
        config["data"] = {"mode": self.mode, "keys": self.keys, "string": dpg.get_value(self.string_input), "interval": dpg.get_value(self.interval_input)}
        return config

    def apply_config(self, data):
        self.mode = data.get("mode", "단축키")
        self.keys = data.get("keys", ["enter"])
        dpg.set_value(self.mode_combo, self.mode)
        dpg.set_value(self.string_input, data.get("string", ""))
        dpg.set_value(self.interval_input, data.get("interval", 0.05))
        self._on_mode_change()
        self._render_slots()

class MouseMoveNode(BaseNode):
    node_type = "mouse_move"
    def __init__(self, pos=(10, 10)):
        super().__init__("마우스 이동", pos)

    def _add_widgets(self):
        dpg.add_text("좌표로 커서만 이동합니다.", color=(150, 150, 150))
        self.duration_input = dpg.add_input_float(label="시간(s)", default_value=0.2, width=80)

    def execute(self):
        pos = state.macro_state.get("target_pos")
        dur = dpg.get_value(self.duration_input)
        if pos:
            print(f"마우스 이동: ({pos[0]}, {pos[1]})")
            pyautogui.moveTo(pos[0], pos[1], duration=dur)
        else:
            print("에러: 이동할 목표 좌표가 없습니다.")
        return self.output_pin

    def get_config(self):
        config = super().get_config()
        config["data"] = {"duration": dpg.get_value(self.duration_input)}
        return config

    def apply_config(self, data):
        dpg.set_value(self.duration_input, data.get("duration", 0.2))

class MouseScrollNode(BaseNode):
    node_type = "mouse_scroll"
    def __init__(self, pos=(10, 10)):
        super().__init__("마우스 스크롤", pos)

    def _add_widgets(self):
        dpg.add_text("휠 스크롤 수행", color=(150, 150, 150))
        self.amount_input = dpg.add_input_int(label="양", default_value=-100, width=80)
        dpg.add_text("(양수: 위, 음수: 아래)", size=12, color=(120, 120, 120))

    def execute(self):
        amt = dpg.get_value(self.amount_input)
        print(f"마우스 스크롤: {amt}")
        pyautogui.scroll(amt)
        return self.output_pin

    def get_config(self):
        config = super().get_config()
        config["data"] = {"amount": dpg.get_value(self.amount_input)}
        return config

    def apply_config(self, data):
        dpg.set_value(self.amount_input, data.get("amount", -100))

class MouseDragNode(BaseNode):
    node_type = "mouse_drag"
    def __init__(self, pos=(10, 10)):
        super().__init__("마우스 드래그", pos)

    def _add_widgets(self):
        dpg.add_text("현재 위치 -> 목표 좌표", color=(150, 150, 150))
        self.duration_input = dpg.add_input_float(label="시간(s)", default_value=0.5, width=80)

    def execute(self):
        pos = state.macro_state.get("target_pos")
        dur = dpg.get_value(self.duration_input)
        if pos:
            print(f"마우스 드래그 시작: {pyautogui.position()} -> 끝: {pos}")
            pyautogui.dragTo(pos[0], pos[1], duration=dur)
        else:
            print("에러: 드래그할 목표 좌표가 없습니다.")
        return self.output_pin

    def get_config(self):
        config = super().get_config()
        config["data"] = {"duration": dpg.get_value(self.duration_input)}
        return config

    def apply_config(self, data):
        dpg.set_value(self.duration_input, data.get("duration", 0.5))
