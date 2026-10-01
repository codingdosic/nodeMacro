import os
import sys
import threading
import time
from pynput import keyboard

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from backend.engine import state
from backend.config import get_setting

class Executor:
    def __init__(self):
        self.running = False
        self.thread = None
        self._stop_requested = False

        # 비상 정지 리스너 시작
        self.listener = keyboard.Listener(on_press=self._on_press)
        self.listener.start()

    def _on_press(self, key):
        name = getattr(key, "name", None) or getattr(key, "char", None)
        if name and name.lower() == get_setting("panic_stop_key"):
            print(f"비상 중단 요청됨 ({name.upper()})")
            self.stop()

    def start(self, all_nodes_dict, all_links, start_node_id=None):
        """
        all_nodes_dict: {node_id: NodeInstance}
        all_links: [{"source": source_id, "sourceHandle": pin_name, "target": target_id, "targetHandle": pin_name}, ...]
        """
        if self.running:
            return False

        state.update_status("매크로 준비 중...")

        start_node = all_nodes_dict.get(start_node_id) if start_node_id else None
        if not start_node:
            start_node = next((node for node in all_nodes_dict.values() if node.node_type == "start"), None)

        if not start_node:
            state.update_status("시작 노드가 없습니다.")
            return False

        self.running = True
        self._stop_requested = False
        state.stop_event.clear()
        state.update_execution(None, "reset")
        self.thread = threading.Thread(
            target=self._run_loop,
            args=(start_node, all_nodes_dict, all_links),
            daemon=True
        )
        self.thread.start()
        return True

    def stop(self):
        self._stop_requested = True
        state.stop_event.set()
        state.update_status("매크로 중단됨")

    def close(self):
        self.stop()
        if self.listener:
            self.listener.stop()

    def _run_loop(self, start_node, all_nodes_dict, all_links):
        current_node = None
        try:
            state.macro_state.clear()
            for node in all_nodes_dict.values():
                node.reset()

            current_node = start_node
            while current_node and not self._stop_requested:
                state.update_execution(current_node.node_id, "running")
                state.update_status(f"실행 중: {current_node.label}")
                next_pin_id = current_node.execute(state.macro_state)
                state.update_execution(current_node.node_id, "completed")
                next_node = self._get_next_node(current_node, all_nodes_dict, all_links, next_pin_id)
                if not next_node:
                    state.update_status("매크로 완료")
                    print("더 이상 연결된 노드가 없습니다. 실행 종료.")
                    break
                current_node = next_node
                state.stop_event.wait(0.01)
        except Exception as exc:
            state.update_execution(current_node.node_id if current_node else None, "error", str(exc))
            state.update_status(f"매크로 오류: {exc}")
            print(f"매크로 실행 오류: {exc}")
        finally:
            self.running = False
            state.update_execution(None, "finished")
            print("매크로 실행이 종료되었습니다.")

    def _get_next_node(self, node, all_nodes_dict, all_links, specific_out_pin):
        """
        현재 노드의 out_pin에서 출발하는 link를 찾아 target 노드를 반환
        """
        for link in all_links:
            # React Flow format: source, sourceHandle, target, targetHandle
            if link.get("source") == node.node_id and link.get("sourceHandle") == specific_out_pin:
                target_id = link.get("target")
                return all_nodes_dict.get(target_id)

        return None
