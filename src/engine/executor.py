import os
import sys
import threading
import time
from pynput import keyboard

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.engine import state

class Executor:
    def __init__(self, node_editor_id):
        self.node_editor_id = node_editor_id
        self.running = False
        self.thread = None
        self._stop_requested = False
        
        # 비상 정지 리스너 시작 (ESC 키)
        self.listener = keyboard.Listener(on_press=self._on_press)
        self.listener.start()

    def _on_press(self, key):
        if key == keyboard.Key.esc:
            print("비상 중단 요청됨 (ESC)")
            self.stop()

    def start(self, start_node, all_nodes, all_links):
        if self.running:
            return
        
        self.running = True
        self._stop_requested = False
        self.thread = threading.Thread(
            target=self._run_loop, 
            args=(start_node, all_nodes, all_links),
            daemon=True
        )
        self.thread.start()

    def stop(self):
        self._stop_requested = True
        self.running = False

    def _run_loop(self, start_node, all_nodes, all_links):
        # 실행 전 전역 매크로 상태 초기화 및 모든 노드 리셋
        state.macro_state.clear()
        for node in all_nodes:
            node.reset()
        
        current_node = start_node
        
        while current_node and not self._stop_requested:
            # 1. 현재 노드 실행 및 다음 핀 ID 획득
            next_pin_id = current_node.execute()
            
            # 2. 다음 노드 찾기 (지정된 핀 또는 기본 출력 핀 확인)
            next_node = self._get_next_node(current_node, all_nodes, all_links, next_pin_id)
            if not next_node:
                print("더 이상 연결된 노드가 없습니다. 실행 종료.")
                break
            
            current_node = next_node
            time.sleep(0.01) # CPU 점유율 방지
            
        self.running = False
        print("매크로 실행이 종료되었습니다.")

    def _get_next_node(self, node, all_nodes, all_links, specific_out_pin=None):
        # 탐색할 출력 핀 결정
        out_pin = specific_out_pin if specific_out_pin else node.output_pin
        
        # 해당 핀에서 출발하는 링크 찾기
        for link in all_links:
            import dearpygui.dearpygui as dpg
            config = dpg.get_item_configuration(link)
            attr1 = config.get('attr_1')
            attr2 = config.get('attr_2')
            
            # out_pin 이 attr1(출력)인 경우 attr2(입력)에 연결된 노드를 찾음
            if attr1 == out_pin:
                target_in_pin = attr2
                for n in all_nodes:
                    if n.input_pin == target_in_pin:
                        return n
            # 방향이 반대인 경우 (DPG 링크 특성상 p1, p2가 바뀔 수 있음)
            elif attr2 == out_pin:
                target_in_pin = attr1
                for n in all_nodes:
                    if n.input_pin == target_in_pin:
                        return n
        return None
