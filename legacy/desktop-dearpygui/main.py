import os
import sys
import json
import shutil
import dearpygui.dearpygui as dpg

# --- 실행 환경에 따른 경로 설정 ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    sys.path.append(sys._MEIPASS)
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.append(BASE_DIR)

from src.nodes.action_nodes import AnchorNode, StartNode, CoordNode, WaitNode, ImageNode, MouseClickNode, LoopNode, IfNode, KeyboardNode, MouseMoveNode, MouseScrollNode, MouseDragNode
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
    "if": IfNode,
    "mouse_move": MouseMoveNode,
    "mouse_scroll": MouseScrollNode,
    "mouse_drag": MouseDragNode
}

# 전역 상태 관리
nodes = []
node_editor = "main_node_editor" 
executor = None
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
history_stack = [] 
MAX_HISTORY = 30   

# 필수 폴더 생성 및 초기화
for d in [SCRIPTS_DIR, ASSETS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

def clear_assets_folder():
    if not os.path.exists(ASSETS_DIR): return
    for filename in os.listdir(ASSETS_DIR):
        file_path = os.path.join(ASSETS_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path): os.unlink(file_path)
            elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e: print(f"임시 파일 삭제 실패: {e}")

clear_assets_folder()

# --- Undo (히스토리) 관리 로직 ---

def get_current_editor_state():
    """현재 노드 에디터의 전체 상태를 직렬화하여 반환"""
    global nodes
    serialized_nodes = []
    for node in nodes:
        config = node.get_config()
        if config is None: continue
        config["type"] = node.node_type
        serialized_nodes.append(config)
        
    serialized_links = []
    if dpg.does_item_exist(node_editor):
        all_links = dpg.get_item_children(node_editor, 0)
        if all_links:
            for link in all_links:
                config = dpg.get_item_configuration(link)
                p1, p2 = config.get("attr_1"), config.get("attr_2")
                from_node_idx, from_pin_name, to_node_idx = -1, "output_pin", -1
                
                for i, n in enumerate(nodes):
                    for pin_attr in ["output_pin", "loop_out_pin", "exit_out_pin", "true_out_pin", "false_out_pin"]:
                        if hasattr(n, pin_attr) and getattr(n, pin_attr) in [p1, p2]:
                            from_node_idx, from_pin_name = i, pin_attr
                            break
                    if hasattr(n, 'input_pin') and getattr(n, 'input_pin') in [p1, p2]:
                        to_node_idx = i
                
                if from_node_idx != -1 and to_node_idx != -1:
                    serialized_links.append({"from": from_node_idx, "from_pin": from_pin_name, "to": to_node_idx})
            
    return {"nodes": serialized_nodes, "links": serialized_links}

def save_snapshot():
    """현재 상태를 스택에 저장 (변화 직전에 호출)"""
    global history_stack
    try:
        state_snapshot = get_current_editor_state()
        history_stack.append(state_snapshot)
        if len(history_stack) > MAX_HISTORY: history_stack.pop(0)
        print(f"[Undo] 스냅샷 저장됨 (현재 스택: {len(history_stack)})")
    except Exception as e:
        print(f"[Undo] 스냅샷 저장 중 오류 발생: {e}")

def undo():
    """마지막 상태로 복구 (Ctrl+Z)"""
    global history_stack, nodes
    if not history_stack:
        print("[Undo] 되돌릴 작업이 없습니다.")
        return
        
    data = history_stack.pop()
    print(f"[Undo] 되돌리기 실행... (남은 스택: {len(history_stack)})")
    
    # 1. UI 및 데이터 초기화
    try:
        if dpg.does_item_exist(node_editor):
            all_links = dpg.get_item_children(node_editor, 0)
            for link in all_links:
                if dpg.does_item_exist(link): dpg.delete_item(link)
        
        for node in list(nodes): 
            delete_node_manual(node, force=True, record_history=False)
        nodes.clear()
        
        # 2. 노드 복원
        for n_data in data["nodes"]:
            node_type = n_data["type"]
            new_node = NODE_MAP[node_type](pos=n_data["pos"])
            new_node.create_ui(node_editor)
            
            # 우클릭 메뉴 핸들러
            handler_tag = f"node_handler_{new_node.node_id}"
            with dpg.item_handler_registry(tag=handler_tag):
                dpg.add_item_clicked_handler(button=1, callback=lambda s, a, u, n=new_node: show_node_menu(n))
            dpg.bind_item_handler_registry(new_node.node_id, handler_tag)
            
            new_node.apply_config(n_data["data"])
            nodes.append(new_node)
        
        # 3. 링크 복원
        for l_data in data["links"]:
            f_idx, t_idx = l_data["from"], l_data["to"]
            pin_name = l_data.get("from_pin", "output_pin")
            if f_idx < len(nodes) and t_idx < len(nodes):
                from_pin = getattr(nodes[f_idx], pin_name, getattr(nodes[f_idx], "output_pin", None))
                to_pin = nodes[t_idx].input_pin
                if from_pin and to_pin:
                    dpg.add_node_link(from_pin, to_pin, parent=node_editor)
        print("[Undo] 복구 완료")
    except Exception as e:
        print(f"[Undo] 복구 중 치명적 오류 발생: {e}")

# --- 에디터 조작 ---

def link_callback(sender, app_data):
    save_snapshot()
    dpg.add_node_link(app_data[0], app_data[1], parent=sender)

def delink_callback(sender, app_data):
    save_snapshot()
    dpg.delete_item(app_data)

def delete_node_manual(node_obj, force=False, record_history=True):
    global nodes
    if not force and isinstance(node_obj, StartNode): return
    node_id = node_obj.node_id
    if not node_id or not dpg.does_item_exist(node_id): return

    if record_history: save_snapshot()

    # 링크 정리
    pins = []
    for pin_attr in ["input_pin", "output_pin", "true_out_pin", "false_out_pin", "loop_out_pin", "exit_out_pin"]:
        if hasattr(node_obj, pin_attr):
            val = getattr(node_obj, pin_attr)
            if val: pins.append(val)
    
    if dpg.does_item_exist(node_editor):
        all_links = dpg.get_item_children(node_editor, 0)
        for link in all_links:
            config = dpg.get_item_configuration(link)
            if config.get("attr_1") in pins or config.get("attr_2") in pins:
                if dpg.does_item_exist(link): dpg.delete_item(link)

    # 핸들러 및 UI 삭제
    handler_tag = f"node_handler_{node_id}"
    if dpg.does_item_exist(handler_tag): dpg.delete_item(handler_tag)
    if dpg.does_item_exist(node_id): dpg.delete_item(node_id)
    
    if node_obj in nodes: nodes.remove(node_obj)

def delete_selected_nodes():
    save_snapshot()
    selected_links = dpg.get_selected_links(node_editor)
    for link in selected_links:
        if dpg.does_item_exist(link): dpg.delete_item(link)
            
    selected_nodes = dpg.get_selected_nodes(node_editor)
    if not selected_nodes: return
    
    nodes_to_delete = [n for n in nodes if n.node_id in selected_nodes]
    for node_obj in nodes_to_delete: delete_node_manual(node_obj, record_history=False)
    print(f"선택된 항목 삭제 완료")

def show_node_menu(node_obj):
    menu_tag = "node_context_menu_window"
    if dpg.does_item_exist(menu_tag): dpg.delete_item(menu_tag)
    with dpg.window(popup=True, tag=menu_tag, pos=dpg.get_mouse_pos(local=False)):
        dpg.add_menu_item(label="삭제", callback=lambda: (dpg.hide_item(menu_tag), delete_node_manual(node_obj)))

def get_canvas_mouse_pos():
    if not dpg.does_item_exist("origin_anchor"): return [50, 50]
    anchor_screen_pos = dpg.get_item_rect_min("origin_anchor")
    mouse_screen_pos = dpg.get_mouse_pos(local=False)
    return [mouse_screen_pos[0] - anchor_screen_pos[0], mouse_screen_pos[1] - anchor_screen_pos[1]]

def add_node(sender, app_data, user_data):
    global nodes
    node_type = user_data
    if node_type not in NODE_MAP: return None
    if node_type == "start" and any(isinstance(n, StartNode) for n in nodes): return None

    print(f"[Action] 노드 추가 시도: {node_type}")
    save_snapshot() # 추가 전 현재 상태 저장

    pos = get_canvas_mouse_pos()
    new_node = NODE_MAP[node_type](pos=pos)
    new_node.create_ui(node_editor)
    
    handler_tag = f"node_handler_{new_node.node_id}"
    with dpg.item_handler_registry(tag=handler_tag):
        dpg.add_item_clicked_handler(button=1, callback=lambda s, a, u, n=new_node: show_node_menu(n))
    dpg.bind_item_handler_registry(new_node.node_id, handler_tag)
        
    nodes.append(new_node)
    return new_node

def copy_nodes():
    global node_clipboard
    selected_nodes = dpg.get_selected_nodes(node_editor)
    if not selected_nodes: return
    node_clipboard = []
    for node_id in selected_nodes:
        node_obj = next((n for n in nodes if n.node_id == node_id), None)
        if node_obj and not isinstance(node_obj, StartNode):
            config = node_obj.get_config(); config["type"] = node_obj.node_type
            node_clipboard.append(config)
    print(f"노드 복사됨: {len(node_clipboard)}개")

def paste_nodes():
    global node_clipboard, nodes
    if not node_clipboard or not dpg.does_item_exist("origin_anchor"): return

    save_snapshot()
    mouse_canvas_pos = get_canvas_mouse_pos()
    new_selection = []
    base_orig_pos = node_clipboard[0]["pos"]
    
    selected_nodes = dpg.get_selected_nodes(node_editor)
    for node_id in selected_nodes:
        if dpg.does_item_exist(node_id): 
            try: dpg.configure_item(node_id, selected=False)
            except: pass

    for config in node_clipboard:
        rel_x, rel_y = config["pos"][0] - base_orig_pos[0], config["pos"][1] - base_orig_pos[1]
        target_pos = [mouse_canvas_pos[0] + rel_x, mouse_canvas_pos[1] + rel_y]
        
        new_node = NODE_MAP[config["type"]](pos=target_pos)
        new_node.create_ui(node_editor)
        handler_tag = f"node_handler_{new_node.node_id}"
        with dpg.item_handler_registry(tag=handler_tag):
            dpg.add_item_clicked_handler(button=1, callback=lambda s, a, u, n=new_node: show_node_menu(n))
        dpg.bind_item_handler_registry(new_node.node_id, handler_tag)
        new_node.apply_config(config["data"])
        nodes.append(new_node)
        new_selection.append(new_node.node_id)

    for node_id in new_selection:
        if dpg.does_item_exist(node_id):
            try: dpg.configure_item(node_id, selected=True)
            except: pass
    print(f"노드 붙여넣기 완료")

def save_macro():
    raw_name = dpg.get_value("save_filename_input").strip()
    if not raw_name: return
    script_folder = os.path.join(SCRIPTS_DIR, raw_name)
    image_folder = os.path.join(script_folder, "images")
    os.makedirs(image_folder, exist_ok=True)
    save_path = os.path.join(script_folder, f"{raw_name}.json")
    
    state_data = get_current_editor_state()
    for n_data in state_data["nodes"]:
        if "data" in n_data and "image_path" in n_data["data"] and n_data["data"]["image_path"]:
            old_path = n_data["data"]["image_path"]
            if os.path.exists(old_path):
                img_name = os.path.basename(old_path)
                new_img_path = os.path.join(image_folder, img_name)
                if os.path.abspath(old_path) != os.path.abspath(new_img_path):
                    try: shutil.copy2(old_path, new_img_path)
                    except: pass
                n_data["data"]["image_path"] = os.path.join("images", img_name)
    
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, ensure_ascii=False)
    print(f"매크로가 저장되었습니다: {save_path}")
    dpg.hide_item("save_dialog_window")

def load_macro(json_relative_path):
    global nodes
    load_path = os.path.join(SCRIPTS_DIR, json_relative_path)
    if not os.path.exists(load_path): return
    script_dir = os.path.dirname(load_path)
    with open(load_path, "r", encoding="utf-8") as f: data = json.load(f)

    save_snapshot()

    if dpg.does_item_exist(node_editor):
        all_links = dpg.get_item_children(node_editor, 0)
        for link in all_links: dpg.delete_item(link)
    for node in list(nodes): delete_node_manual(node, force=True, record_history=False)
    nodes.clear()

    for n_data in data["nodes"]:
        node_obj = add_node(None, None, n_data["type"])
        if not node_obj: continue
        # add_node 내부에서 이미 snapshot을 찍으므로, 중복 방지를 위해 list 수동 관리 고려 가능하나 여기서는 단순화
        dpg.set_item_pos(node_obj.node_id, n_data["pos"])
        if "data" in n_data and "image_path" in n_data["data"] and n_data["data"]["image_path"]:
            rel_path = n_data["data"]["image_path"]
            if not os.path.isabs(rel_path):
                n_data["data"]["image_path"] = os.path.abspath(os.path.join(script_dir, rel_path))
        node_obj.apply_config(n_data["data"])
    
    # 링크 복구
    for l_data in data["links"]:
        f_idx, t_idx = l_data["from"], l_data["to"]
        pin_name = l_data.get("from_pin", "output_pin")
        if f_idx < len(nodes) and t_idx < len(nodes):
            from_pin = getattr(nodes[f_idx], pin_name, getattr(nodes[f_idx], "output_pin", None))
            to_pin = nodes[t_idx].input_pin
            if from_pin and to_pin: dpg.add_node_link(from_pin, to_pin, parent=node_editor)
    print(f"매크로를 불러왔습니다: {json_relative_path}")

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
    else: dpg.show_item("add_node_dialog")

def run_macro():
    start_node = next((n for n in nodes if isinstance(n, StartNode)), None)
    if not start_node: return
    all_links = dpg.get_item_children(node_editor, 0)
    executor.start(start_node, nodes, all_links)

def stop_macro(): executor.stop()

def open_save_dialog():
    if not dpg.does_item_exist("save_dialog_window"):
        with dpg.window(label="매크로 저장", modal=True, show=True, tag="save_dialog_window", pos=(400, 300), width=300, height=120):
            dpg.add_input_text(label="이름", tag="save_filename_input", default_value="macro_1")
            with dpg.group(horizontal=True):
                dpg.add_button(label="저장", width=100, callback=save_macro)
                dpg.add_button(label="취소", width=100, callback=lambda: dpg.hide_item("save_dialog_window"))
    else: dpg.show_item("save_dialog_window")

def open_load_dialog():
    script_files = []
    if os.path.exists(SCRIPTS_DIR):
        for root, dirs, files in os.walk(SCRIPTS_DIR):
            for file in files:
                if file.endswith(".json"):
                    rel_path = os.path.relpath(os.path.join(root, file), SCRIPTS_DIR)
                    script_files.append(rel_path)
    if not script_files: return
    if dpg.does_item_exist("load_dialog_window"): dpg.delete_item("load_dialog_window")
    with dpg.window(label="매크로 불러오기", modal=True, show=True, tag="load_dialog_window", pos=(400, 300), width=450, height=400):
        with dpg.child_window(height=300):
            for rel_path in script_files:
                dpg.add_button(label=rel_path.replace("\\", "/"), width=-1, 
                               callback=lambda s, a, u: (load_macro(u), dpg.hide_item("load_dialog_window")), user_data=rel_path)
        dpg.add_button(label="닫기", width=-1, callback=lambda: dpg.hide_item("load_dialog_window"))

def on_key_press(sender, key_code):
    is_ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
    if is_ctrl:
        if key_code == dpg.mvKey_C: copy_nodes()
        elif key_code == dpg.mvKey_V: paste_nodes()
        elif key_code == dpg.mvKey_Z: undo()
    elif key_code == dpg.mvKey_Delete: delete_selected_nodes()

def setup_ui():
    global nodes, executor
    dpg.create_context()
    with dpg.font_registry():
        font_path = os.path.join(BASE_DIR, "fonts", "malgun.ttf")
        if not os.path.exists(font_path): font_path = "C:/Windows/Fonts/malgun.ttf"
        if os.path.exists(font_path):
            with dpg.font(font_path, 20, tag="korean_font"):
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Korean)
                dpg.add_font_range(0x3130, 0x318F); dpg.add_font_range(0xAC00, 0xD7A3)
            dpg.bind_font("korean_font")

    with dpg.texture_registry(tag="main_texture_registry", show=False):
        dpg.add_static_texture(width=1, height=1, default_value=[0, 0, 0, 0], tag="default_none")

    # --- 실행 상태 오버레이 창 추가 ---
    with dpg.window(tag="status_overlay", no_title_bar=True, no_move=True, no_resize=True, 
                    no_background=True, show=False, pos=(900, 10), width=300, height=60):
        dpg.add_text("실행 중...", tag="status_overlay_text", color=(255, 255, 0))
        dpg.bind_item_font("status_overlay", "korean_font")

    with dpg.window(label="Node Macro MVP", tag="primary_window", no_close=True):
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
            callback=link_callback, delink_callback=delink_callback,
            tag=node_editor, width=-1, height=-1, minimap=True,
            minimap_location=dpg.mvNodeMiniMap_Location_BottomRight
        ):
            dpg.bind_item_font(node_editor, "korean_font")
            AnchorNode().create_ui(node_editor)
            
            start_node = StartNode(pos=(50, 50))
            start_node.create_ui(node_editor)
            nodes.append(start_node)
            
            # [수정] 시작 직후의 상태(StartNode만 있는 상태)를 첫 스냅샷으로 저장
            save_snapshot()

    executor = Executor(node_editor)
    dpg.set_primary_window("primary_window", True)
    with dpg.handler_registry():
        dpg.add_key_press_handler(callback=on_key_press)

if __name__ == "__main__":
    setup_ui()
    dpg.create_viewport(title='Node Macro MVP', width=1200, height=900)
    dpg.setup_dearpygui(); dpg.show_viewport(); dpg.start_dearpygui(); dpg.destroy_context()
