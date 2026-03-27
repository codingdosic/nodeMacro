import os
import sys
import json
import dearpygui.dearpygui as dpg

# --- 실행 환경에 따른 경로 설정 (Portable/EXE 대응) ---
if getattr(sys, 'frozen', False):
    # EXE 실행 시: EXE 파일이 있는 폴더 기준
    BASE_DIR = os.path.dirname(sys.executable)
    # 내부 모듈 참조를 위해 임시 폴더(sys._MEIPASS)를 path에 추가
    sys.path.append(sys._MEIPASS)
else:
    # 파이썬 실행 시: 현재 파일의 상위 폴더(프로젝트 루트) 기준
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.append(BASE_DIR)

from src.nodes.action_nodes import AnchorNode, StartNode, CoordNode, WaitNode, ImageNode, MouseClickNode, LoopNode, IfNode, KeyboardNode
from src.engine.executor import Executor
from src.engine import state

# 노드 타입 매핑 레지스트리
NODE_MAP = {
    "start": StartNode,
    "click": CoordNode,
    "wait": WaitNode,
    "image": ImageNode,
    "mouse_click": MouseClickNode,
    "keyboard": KeyboardNode,
    "loop": LoopNode,
    "if": IfNode
}

# 전역 상태 관리
nodes = []
node_editor = None
executor = None
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# 필수 폴더 생성
for d in [SCRIPTS_DIR, ASSETS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

def link_callback(sender, app_data):
    dpg.add_node_link(app_data[0], app_data[1], parent=sender)

def delink_callback(sender, app_data):
    dpg.delete_item(app_data)

def delete_node_manual(node_obj):
    if isinstance(node_obj, StartNode):
        print("안내: '시작' 노드는 삭제할 수 없습니다.")
        return

    # 1. UI 요소 삭제 (노드를 삭제하면 연결된 링크는 DPG가 자동으로 처리함)
    if dpg.does_item_exist(node_obj.node_id):
        dpg.delete_item(node_obj.node_id)
    
    # 2. 데이터 리스트에서 제거
    global nodes
    if node_obj in nodes:
        nodes.remove(node_obj)

    # 3. 핸들러 레지스트리 삭제
    handler_tag = f"node_handler_{node_obj.node_id}"
    if dpg.does_item_exist(handler_tag):
        dpg.delete_item(handler_tag)
        
    print(f"노드 삭제 완료: {node_obj.label}")

def delete_selected_nodes():
    selected_nodes = dpg.get_selected_nodes(node_editor)
    if not selected_nodes: return
    
    # 여러 노드 삭제 시 리스트 복사본 사용 (반복 중 원본 변경 방지)
    nodes_to_delete = []
    for node_id in selected_nodes:
        node_obj = next((n for n in nodes if n.node_id == node_id), None)
        if node_obj:
            nodes_to_delete.append(node_obj)
            
    for node_obj in nodes_to_delete:
        delete_node_manual(node_obj)
    print(f"선택된 노드 {len(nodes_to_delete)}개 삭제 완료")

def show_node_menu(node_obj):
    # 우클릭 시 삭제 메뉴 팝업 생성
    menu_tag = "node_context_menu_window" # 공통 태그 사용
    if dpg.does_item_exist(menu_tag):
        dpg.delete_item(menu_tag)
        
    with dpg.window(popup=True, tag=menu_tag, pos=dpg.get_mouse_pos(local=False)):
        dpg.add_menu_item(label="삭제", callback=lambda: delete_node_manual(node_obj))

def get_canvas_mouse_pos():
    """마우스의 현재 화면 위치를 노드 에디터 내부(Canvas) 좌표로 변환하여 반환"""
    if not dpg.does_item_exist("origin_anchor"):
        return [50, 50] # 앵커가 없을 경우 기본값

    # 1. 앵커 노드(0,0)의 현재 '화면(Screen)' 좌표 획득 (Panning 상태 반영됨)
    anchor_screen_pos = dpg.get_item_rect_min("origin_anchor")
    # 2. 마우스의 현재 '화면(Screen)' 좌표 획득
    mouse_screen_pos = dpg.get_mouse_pos(local=False)

    # 3. 마우스의 '에디터 내부(Canvas)' 좌표 역산
    # 공식: MouseCanvas = MouseScreen - AnchorScreen
    return [
        mouse_screen_pos[0] - anchor_screen_pos[0],
        mouse_screen_pos[1] - anchor_screen_pos[1]
    ]

def add_node(sender, app_data, user_data):
    node_type = user_data
    if node_type not in NODE_MAP:
        print(f"에러: 알 수 없는 노드 타입입니다. ({node_type})")
        return None

    # 시작 노드 중복 생성 방지
    if node_type == "start" and any(isinstance(n, StartNode) for n in nodes):
        return None

    # 마우스 위치 기반 캔버스 좌표 획득 (붙여넣기 오프셋 로직 활용)
    pos = get_canvas_mouse_pos()

    # 노드 인스턴스 생성 및 UI 구성
    new_node = NODE_MAP[node_type](pos=pos)
    new_node.create_ui(node_editor)
    
    # 노드 우클릭 감지를 위한 핸들러 등록
    handler_tag = f"node_handler_{new_node.node_id}"
    with dpg.item_handler_registry(tag=handler_tag):
        dpg.add_item_clicked_handler(button=1, callback=lambda s, a, u: show_node_menu(new_node))
    dpg.bind_item_handler_registry(new_node.node_id, handler_tag)
        
    nodes.append(new_node)
    return new_node

def copy_nodes():
    global node_clipboard
    selected_nodes = dpg.get_selected_nodes(node_editor)
    if not selected_nodes:
        return

    node_clipboard = []
    for node_id in selected_nodes:
        node_obj = next((n for n in nodes if n.node_id == node_id), None)
        if node_obj and not isinstance(node_obj, StartNode):
            config = node_obj.get_config()
            config["type"] = node_obj.node_type
            node_clipboard.append(config)
    print(f"노드 복사됨: {len(node_clipboard)}개")

def paste_nodes():
    global node_clipboard
    # origin_anchor가 없으면 에러 방지
    if not node_clipboard or not dpg.does_item_exist("origin_anchor"):
        print("에러: 클립보드가 비어있거나 원점 앵커를 찾을 수 없습니다.")
        return

    # 마우스의 '에디터 내부(Canvas)' 좌표 획득
    mouse_canvas_pos = get_canvas_mouse_pos()

    # 3. 붙여넣기 로직 수행
    new_selection = []
    
    # 여러 노드 복사 시, 첫 번째 노드를 마우스 위치에 맞추고 나머지는 상대 간격 유지
    base_orig_pos = node_clipboard[0]["pos"]
    
    # 선택 해제 (안전한 방식으로 루프 수행)
    selected_nodes = dpg.get_selected_nodes(node_editor)
    if selected_nodes:
        for node_id in selected_nodes:
            if dpg.does_item_exist(node_id):
                try:
                    dpg.configure_item(node_id, selected=False)
                except:
                    pass

    for config in node_clipboard:
        # 복사될 당시의 첫 노드와의 거리 계산
        rel_x = config["pos"][0] - base_orig_pos[0]
        rel_y = config["pos"][1] - base_orig_pos[1]
        
        # 현재 마우스 캔버스 좌표에 해당 간격 적용
        target_pos = [mouse_canvas_pos[0] + rel_x, mouse_canvas_pos[1] + rel_y]
        
        new_node = add_node(None, None, config["type"])
        if new_node:
            dpg.set_item_pos(new_node.node_id, target_pos)
            new_node.apply_config(config["data"])
            new_selection.append(new_node.node_id)

    # 새로 붙여넣은 노드들 선택 (안전하게 처리)
    for node_id in new_selection:
        if dpg.does_item_exist(node_id):
            try:
                # 일부 DPG 환경에서 selected 키워드 에러 방지를 위해 에러 제어
                dpg.configure_item(node_id, selected=True)
            except Exception as e:
                print(f"노드 선택 설정 건너뜀: {e}")
    
    print(f"노드 {len(new_selection)}개 마우스 위치에 정밀 붙여넣기 완료")

def save_macro():
    filename = dpg.get_value("save_filename_input")
    if not filename.endswith(".json"):
        filename += ".json"
    
    save_path = os.path.join(SCRIPTS_DIR, filename)
    
    # 1. 노드 데이터 수집
    serialized_nodes = []
    for node in nodes:
        config = node.get_config()
        config["type"] = node.node_type
        serialized_nodes.append(config)
    
    # 2. 링크 데이터 수집
    serialized_links = []
    all_links = dpg.get_item_children(node_editor, 0)
    for link in all_links:
        config = dpg.get_item_configuration(link)
        p1 = config.get("attr_1") # 출발 핀 (보통 Out)
        p2 = config.get("attr_2") # 도착 핀 (보통 In)
        
        # DPG는 p1, p2가 방향에 따라 뒤바뀔 수 있으므로 정교하게 체크
        from_node_idx = -1
        from_pin_name = "output_pin"
        to_node_idx = -1
        
        for i, n in enumerate(nodes):
            # 출처 찾기
            if hasattr(n, 'output_pin') and (n.output_pin == p1 or n.output_pin == p2):
                from_node_idx = i
                from_pin_name = "output_pin"
            elif hasattr(n, 'loop_out_pin') and (n.loop_out_pin == p1 or n.loop_out_pin == p2):
                from_node_idx = i
                from_pin_name = "loop_out_pin"
            elif hasattr(n, 'exit_out_pin') and (n.exit_out_pin == p1 or n.exit_out_pin == p2):
                from_node_idx = i
                from_pin_name = "exit_out_pin"
            elif hasattr(n, 'true_out_pin') and (n.true_out_pin == p1 or n.true_out_pin == p2):
                from_node_idx = i
                from_pin_name = "true_out_pin"
            elif hasattr(n, 'false_out_pin') and (n.false_out_pin == p1 or n.false_out_pin == p2):
                from_node_idx = i
                from_pin_name = "false_out_pin"
                
            # 대상 찾기 (입력은 항상 input_pin)
            if hasattr(n, 'input_pin') and (n.input_pin == p1 or n.input_pin == p2):
                to_node_idx = i
                
        if from_node_idx != -1 and to_node_idx != -1:
            serialized_links.append({
                "from": from_node_idx, 
                "from_pin": from_pin_name,
                "to": to_node_idx
            })

    full_data = {
        "nodes": serialized_nodes,
        "links": serialized_links
    }
    
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(full_data, f, indent=2, ensure_ascii=False)
    
    print(f"매크로가 저장되었습니다: {save_path}")
    dpg.hide_item("save_dialog_window")

def load_macro(filename):
    global nodes
    load_path = os.path.join(SCRIPTS_DIR, filename)
    if not os.path.exists(load_path): return

    with open(load_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_links = dpg.get_item_children(node_editor, 0)
    for link in all_links: dpg.delete_item(link)
    for node in nodes: delete_node_manual(node)
    nodes.clear()

    new_nodes = []
    for n_data in data["nodes"]:
        node_obj = add_node(None, None, n_data["type"])
        dpg.set_item_pos(node_obj.node_id, n_data["pos"])
        node_obj.apply_config(n_data["data"])
        new_nodes.append(node_obj)
    
    nodes = new_nodes

    # 3. 링크 복구 (핀 이름 기반)
    for l_data in data["links"]:
        f_idx = l_data["from"]
        t_idx = l_data["to"]
        pin_name = l_data.get("from_pin", "output_pin")
        
        if f_idx < len(nodes) and t_idx < len(nodes):
            from_pin = getattr(nodes[f_idx], pin_name, nodes[f_idx].output_pin)
            to_pin = nodes[t_idx].input_pin
            dpg.add_node_link(from_pin, to_pin, parent=node_editor)
    
    print(f"매크로를 불러왔습니다: {filename}")

def open_add_node_dialog():
    if not dpg.does_item_exist("add_node_dialog"):
        with dpg.window(label="노드 추가", modal=True, show=True, tag="add_node_dialog", pos=(400, 200), width=400, height=350):
            with dpg.tab_bar():
                with dpg.tab(label="입력 노드"):
                    dpg.add_button(label="이미지 노드 (좌표 찾기)", width=-1, height=40, callback=add_node, user_data="image")
                    dpg.add_button(label="좌표 노드 (직접 지정)", width=-1, height=40, callback=add_node, user_data="click")
                
                with dpg.tab(label="동작 노드"):
                    dpg.add_button(label="마우스 입력 (클릭)", width=-1, height=40, callback=add_node, user_data="mouse_click")
                    dpg.add_button(label="키보드 입력", width=-1, height=40, callback=add_node, user_data="keyboard")
                    dpg.add_separator()
                    dpg.add_button(label="마우스 이동", width=-1, height=40, callback=add_node, user_data="mouse_move")
                    dpg.add_button(label="마우스 스크롤", width=-1, height=40, callback=add_node, user_data="mouse_scroll")
                    dpg.add_button(label="마우스 드래그", width=-1, height=40, callback=add_node, user_data="mouse_drag")

                with dpg.tab(label="제어 노드"):
                    dpg.add_button(label="대기 노드", width=-1, height=40, callback=add_node, user_data="wait")
                    dpg.add_button(label="조건문 (이미지)", width=-1, height=40, callback=add_node, user_data="if")
                    dpg.add_button(label="반복문", width=-1, height=40, callback=add_node, user_data="loop")
            
            dpg.add_spacer(height=10)
            dpg.add_button(label="닫기", width=-1, callback=lambda: dpg.hide_item("add_node_dialog"))
    else:
        dpg.show_item("add_node_dialog")

def reset_view():
    """에디터의 시점을 원점(0,0)으로 되돌립니다."""
    global node_editor
    print(f"RESET VIEW 클릭됨. node_editor ID: {node_editor}")
    if node_editor:
        try:
            # 2.2 버전 기준 패닝 리셋 시도
            dpg.set_node_editor_panning(node_editor, [0, 0])
            print("dpg.set_node_editor_panning(node_editor, [0, 0]) 실행 완료")
        except Exception as e:
            try:
                # 인자를 낱개로 전달하는 방식 시도
                dpg.set_node_editor_panning(node_editor, 0, 0)
                print("dpg.set_node_editor_panning(node_editor, 0, 0) 실행 완료")
            except Exception as e2:
                print(f"뷰 리셋 최종 실패: {e2}")
    else:
        print("에러: node_editor가 초기화되지 않았습니다.")

def run_macro():
    start_node = next((n for n in nodes if isinstance(n, StartNode)), None)
    if not start_node:
        print("에러: '시작' 노드가 없습니다.")
        return
    all_links = dpg.get_item_children(node_editor, 0)
    executor.start(start_node, nodes, all_links)

def stop_macro():
    executor.stop()

# --- 저장 및 불러오기 UI 로직 ---

def open_save_dialog():
    if not dpg.does_item_exist("save_dialog_window"):
        with dpg.window(label="매크로 저장", modal=True, show=True, tag="save_dialog_window", pos=(400, 300), width=300, height=120):
            dpg.add_input_text(label="이름", tag="save_filename_input", default_value="macro_1")
            with dpg.group(horizontal=True):
                dpg.add_button(label="저장", width=100, callback=save_macro)
                dpg.add_button(label="취소", width=100, callback=lambda: dpg.hide_item("save_dialog_window"))
    else:
        dpg.show_item("save_dialog_window")

def open_load_dialog():
    files = [f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".json")]
    if not files:
        print("불러올 파일이 없습니다.")
        return

    if dpg.does_item_exist("load_dialog_window"):
        dpg.delete_item("load_dialog_window")

    with dpg.window(label="매크로 불러오기", modal=True, show=True, tag="load_dialog_window", pos=(400, 300), width=350, height=300):
        dpg.add_text("불러올 파일을 선택하세요:")
        with dpg.child_window(height=200):
            for file in files:
                dpg.add_button(label=file, width=-1, callback=lambda s, a, u: (load_macro(u), dpg.hide_item("load_dialog_window")), user_data=file)
        
        dpg.add_spacer(height=5)
        dpg.add_button(label="닫기", width=-1, callback=lambda: dpg.hide_item("load_dialog_window"))

def on_key_press(sender, key_code):
    # Ctrl 키가 눌려있는지 확인
    is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
    
    if is_ctrl:
        if key_code == dpg.mvKey_C:
            copy_nodes()
        elif key_code == dpg.mvKey_V:
            paste_nodes()
    elif key_code == dpg.mvKey_Delete:
        delete_selected_nodes()

def setup_ui():
    global node_editor, executor
    
    dpg.create_context()

    # [중요] 한글 폰트 전역 설정: 모든 위젯(버튼, 입력필드 등)에 일괄 적용
    with dpg.font_registry():
        # 1. 폰트 경로 탐색 (로컬 fonts 폴더 우선)
        font_path = os.path.join(BASE_DIR, "fonts", "malgun.ttf")
        if not os.path.exists(font_path):
            font_path = "C:/Windows/Fonts/malgun.ttf" # 윈도우 기본 경로
            
        if os.path.exists(font_path):
            # 사용자의 힌트에 따라 태그를 "korean_font"로 고정
            with dpg.font(font_path, 20, tag="korean_font"):
                # 1. 기본 영문/숫자 및 한글 힌트 통합 추가
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Korean)
                
                # [표준] UI 및 노드 레이블 표시를 위한 한글 범위 수동 등록
                dpg.add_font_range(0x3130, 0x318F) # 한글 자모
                dpg.add_font_range(0xAC00, 0xD7A3) # 한글 완성형
            
            # 전역 기본 폰트로 지정
            dpg.bind_font("korean_font")
            print(f"Global Korean font (korean_font) loaded: {font_path}")
        else:
            print("경고: 한글 폰트 파일을 찾을 수 없습니다.")

    # 1. 고정된 이름의 텍스처 레지스트리 생성
    with dpg.texture_registry(tag="main_texture_registry", show=False):
        dpg.add_static_texture(width=1, height=1, default_value=[0, 0, 0, 0], tag="default_none")

    with dpg.window(label="Node Macro MVP", tag="primary_window", no_close=True):
        # [방어 1] 메인 윈도우에 한글 폰트 명시적 바인딩
        dpg.bind_item_font("primary_window", "korean_font")

        with dpg.group(horizontal=True):
            dpg.add_button(label="[+] 노드 추가", callback=open_add_node_dialog, width=150, height=40)
            dpg.add_spacer(width=20)
            dpg.add_button(label="RUN", callback=run_macro, width=80, height=40)
            dpg.add_button(label="STOP (ESC)", callback=stop_macro, width=120, height=40)
            dpg.add_spacer(width=20)
            dpg.add_button(label="SAVE", callback=open_save_dialog, width=80, height=40)
            dpg.add_button(label="OPEN", callback=open_load_dialog, width=100, height=40)

        with dpg.node_editor(
            callback=link_callback, 
            delink_callback=delink_callback,
            tag="main_node_editor", # 태그 명시
            width=-1, height=-1,
            minimap=True,
            minimap_location=dpg.mvNodeMiniMap_Location_BottomRight
        ) as node_editor:
            # [방어 2] 노드 에디터에도 한글 폰트 명시적 바인딩
            dpg.bind_item_font("main_node_editor", "korean_font")

            # 원점 추적용 앵커 노드 생성 (가장 먼저 생성하여 (0,0) 좌표 확보)
            AnchorNode().create_ui(node_editor)
            # 시작 시 기본 시작 노드 추가
            add_node(None, None, "start")

    executor = Executor(node_editor)
    dpg.set_primary_window("primary_window", True)

    # 모든 키보드 입력을 처리하는 통합 핸들러 등록
    with dpg.handler_registry():
        dpg.add_key_press_handler(callback=on_key_press)
        # 전역 휠 핸들러가 노드 에디터의 내부 줌 이벤트를 방해할 수 있으므로 제거하거나 
        # 필요한 경우에만 최소한으로 사용합니다.

if __name__ == "__main__":
    setup_ui()
    dpg.create_viewport(title='Node Macro MVP', width=1200, height=900)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()
