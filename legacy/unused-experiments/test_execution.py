import sys
import os

# Ensure backend path is recognized
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.nodes.action_nodes import StartNode, CoordNode, MouseClickNode
from backend.engine.executor import Executor
from backend.engine import state

def test_run():
    # 1. Create nodes
    node_start = StartNode(node_id="n_start", config={"delay": 500})
    node_coord = CoordNode(node_id="n_coord", config={"x": 100, "y": 100})
    node_click = MouseClickNode(node_id="n_click", config={"button": "좌클릭", "duration": 0})

    nodes_dict = {
        "n_start": node_start,
        "n_coord": node_coord,
        "n_click": node_click
    }

    # 2. Create links (React Flow format)
    links = [
        {"source": "n_start", "sourceHandle": "output_pin", "target": "n_coord", "targetHandle": "input_pin"},
        {"source": "n_coord", "sourceHandle": "output_pin", "target": "n_click", "targetHandle": "input_pin"}
    ]

    # 3. Add a simple status callback to see what happens
    def my_status_cb(msg):
        print(f"UI Callback -> {msg}")
    
    state.status_callback = my_status_cb

    # 4. Run executor
    executor = Executor()
    print("Starting executor...")
    executor.start(nodes_dict, links)
    
    # Wait for completion
    import time
    while executor.running:
        time.sleep(0.1)
    
    print("Test finished.")

if __name__ == "__main__":
    test_run()
