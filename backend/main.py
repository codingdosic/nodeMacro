import os
import sys
import json
import shutil
import asyncio
import base64
import time
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.nodes.action_nodes import (
    StartNode, CoordNode, WaitNode, ImageNode, MouseClickNode,
    LoopNode, IfNode, KeyboardNode, MouseMoveNode, MouseScrollNode, MouseDragNode,
    WindowNode,
)
from backend.engine.executor import Executor
from backend.engine import state

app = FastAPI(title="NodeMacro API")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

for d in [SCRIPTS_DIR, ASSETS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)


def clear_assets_folder():
    """캡처 스크래치(assets/)를 비운다. 서버 기동 시 호출."""
    if not os.path.exists(ASSETS_DIR):
        return
    for filename in os.listdir(ASSETS_DIR):
        file_path = os.path.join(ASSETS_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"임시 파일 삭제 실패: {e}")


clear_assets_folder()


def _sanitize_script_name(raw_name: str) -> str:
    name = (raw_name or "macro_1").strip().replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-", "."))
    name = name.rstrip(".")
    return name or "macro_1"


def _write_script_batch(script_folder: str, script_name: str):
    payload = json.dumps(
        {"path": f"{script_name}/{script_name}.json"},
        ensure_ascii=True,
    ).encode("utf-8")
    encoded = base64.b64encode(payload).decode("ascii")
    content = f"""@echo off
cd /d "%~dp0\..\.."
call NodeMacro.bat --no-browser
python -c "import base64,urllib.request; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/scripts/run',data=base64.b64decode('{encoded}'),headers={{'Content-Type':'application/json'}})).read()"
"""
    batch_path = os.path.join(script_folder, f"{script_name}.bat")
    with open(batch_path, "w", encoding="utf-8", newline="") as file:
        file.write(content.replace("\n", "\r\n"))
    return batch_path


def _resolve_image_source(image_path: str):
    """image_path(절대/상대/static URL)를 존재하는 절대 경로로 해석."""
    if not image_path or not isinstance(image_path, str):
        return None

    path = image_path.strip()
    if not path:
        return None

    # http(s)://host/static/... → BASE_DIR 상대
    if path.startswith("http://") or path.startswith("https://"):
        marker = "/static/"
        idx = path.find(marker)
        if idx == -1:
            return None
        rel = path[idx + len(marker):].split("?", 1)[0]
        path = os.path.join(BASE_DIR, rel.replace("/", os.sep))
    elif path.startswith("/static/"):
        rel = path[len("/static/"):].split("?", 1)[0]
        path = os.path.join(BASE_DIR, rel.replace("/", os.sep))

    if os.path.isabs(path):
        return path if os.path.isfile(path) else None

    candidate = os.path.join(BASE_DIR, path.replace("/", os.sep))
    if os.path.isfile(candidate):
        return candidate
    return None


def _bundle_images_for_save(macro_data: dict, script_folder: str) -> dict:
    """사용 이미지를 imgs/로 복사하고 image_path를 상대경로로 갱신. image_url 제거."""
    imgs_dir = os.path.join(script_folder, "imgs")
    os.makedirs(imgs_dir, exist_ok=True)

    nodes = macro_data.get("nodes") or []
    used_names = set()

    for node in nodes:
        data = node.get("data") or {}
        data.pop("onChange", None)
        config = data.get("config")
        if not isinstance(config, dict):
            continue

        config.pop("image_url", None)
        image_path = config.get("image_path")
        if not image_path:
            continue

        src = _resolve_image_source(image_path)
        if src is None and isinstance(image_path, str):
            rel = image_path.replace("\\", "/")
            if rel.startswith("imgs/") or rel.startswith("images/"):
                alt = os.path.join(script_folder, rel.replace("/", os.sep))
                if os.path.isfile(alt):
                    src = alt

        if src is None or not os.path.isfile(src):
            base = os.path.basename(str(image_path).replace("\\", "/").split("?")[0])
            if base:
                config["image_path"] = f"imgs/{base}"
            continue

        base = os.path.basename(src)
        node_id = str(node.get("id") or data.get("id") or "node")
        dest_name = base
        dest_path = os.path.join(imgs_dir, dest_name)
        # 다른 소스가 같은 basename을 쓰면 노드 id 접두
        if dest_name in used_names:
            dest_name = f"{node_id}_{base}"
            dest_path = os.path.join(imgs_dir, dest_name)
        elif os.path.isfile(dest_path) and os.path.abspath(dest_path) != os.path.abspath(src):
            # 기존 파일이 다른 내용일 수 있음 → 접두 사용
            dest_name = f"{node_id}_{base}"
            dest_path = os.path.join(imgs_dir, dest_name)

        try:
            if os.path.abspath(src) != os.path.abspath(dest_path):
                shutil.copy2(src, dest_path)
            used_names.add(dest_name)
            config["image_path"] = f"imgs/{dest_name}"
        except Exception as e:
            print(f"이미지 복사 실패 ({src}): {e}")
            config["image_path"] = f"imgs/{dest_name}"

    # 이번 저장에서 쓰이지 않은 imgs 파일 정리
    try:
        for filename in list(os.listdir(imgs_dir)):
            if filename not in used_names:
                fp = os.path.join(imgs_dir, filename)
                if os.path.isfile(fp) or os.path.islink(fp):
                    os.unlink(fp)
    except Exception as e:
        print(f"미사용 이미지 정리 실패: {e}")

    return macro_data


def _attach_runtime_image_fields(macro_data: dict, script_rel_name: str, script_folder: str) -> dict:
    """로드/저장 응답용: 실행용 절대 image_path + 미리보기 image_url."""
    stamp = int(time.time() * 1000)
    nodes = macro_data.get("nodes") or []
    for node in nodes:
        data = node.get("data") or {}
        config = data.get("config")
        if not isinstance(config, dict):
            continue
        image_path = config.get("image_path")
        if not image_path or not isinstance(image_path, str):
            continue

        rel = image_path.replace("\\", "/")
        if os.path.isabs(image_path):
            abs_path = image_path
            base = os.path.basename(image_path)
            url_rel = f"scripts/{script_rel_name}/imgs/{base}"
        else:
            abs_path = os.path.abspath(os.path.join(script_folder, rel.replace("/", os.sep)))
            url_rel = f"scripts/{script_rel_name}/{rel}".replace("\\", "/")

        if os.path.isfile(abs_path):
            config["image_path"] = abs_path
            config["image_url"] = f"http://127.0.0.1:8000/static/{url_rel}?t={stamp}"
        else:
            base = os.path.basename(rel)
            config["image_url"] = (
                f"http://127.0.0.1:8000/static/scripts/{script_rel_name}/imgs/{base}?t={stamp}"
            )
    return macro_data


def _strip_non_serializable(macro_data: dict) -> dict:
    """저장 JSON용: 함수 등 직렬화 불가 필드 제거."""
    nodes_out = []
    for node in macro_data.get("nodes") or []:
        data = dict(node.get("data") or {})
        data.pop("onChange", None)
        config = data.get("config")
        if isinstance(config, dict):
            config = dict(config)
            config.pop("image_url", None)
            data["config"] = config
        nodes_out.append({
            "id": node.get("id"),
            "type": node.get("type"),
            "position": node.get("position"),
            "data": {
                "id": data.get("id", node.get("id")),
                "type": data.get("type"),
                "label": data.get("label"),
                "configSchema": data.get("configSchema"),
                "config": data.get("config") or {},
            },
        })
    edges_out = []
    for edge in macro_data.get("edges") or []:
        edges_out.append({
            "id": edge.get("id"),
            "source": edge.get("source"),
            "target": edge.get("target"),
            "sourceHandle": edge.get("sourceHandle"),
            "targetHandle": edge.get("targetHandle"),
        })
    return {"nodes": nodes_out, "edges": edges_out}

# Static files for images
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

# Static files for frontend build
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

from fastapi.responses import FileResponse
import fastapi.staticfiles
import mimetypes

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="frontend_assets")

    @app.get("/")
    def serve_frontend_index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


NODE_MAP = {
    "start": StartNode,
    "window": WindowNode,
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

executor = Executor()

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# Update state callback to use WebSocket broadcast
def on_status_update(message):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast({"type": "status", "message": message}))
    except RuntimeError:
        # If no event loop in this thread, we can't broadcast easily,
        # but asyncio.run_coroutine_threadsafe could be used if we had the loop reference.
        # For simplicity in this macro engine, we'll try to find a way to dispatch it.
        pass

# We need the main event loop to dispatch events from executor thread
main_loop = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

    def threadsafe_status_update(message):
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "status", "message": message}),
                main_loop
            )

    def threadsafe_execution_update(node_id, phase, message):
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "execution",
                    "node_id": node_id,
                    "phase": phase,
                    "message": message,
                }),
                main_loop,
            )

    state.status_callback = threadsafe_status_update
    state.execution_callback = threadsafe_execution_update


@app.get("/api/health")
def health():
    return {"status": "ok", "running": executor.running}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/nodes/types")
def get_node_types():
    types_info = []
    for type_name, cls in NODE_MAP.items():
        # Instantiate temporarily to get schema/label
        temp_node = cls(node_id="temp")
        types_info.append({
            "type": type_name,
            "label": temp_node.label,
            "schema": temp_node.get_schema()
        })
    return types_info

class MacroRunRequest(BaseModel):
    nodes: Dict[str, dict]  # e.g., {"node_1": {"type": "start", "config": {}}}
    links: List[dict]       # e.g., [{"source": "node_1", "sourceHandle": "output_pin", "target": "node_2", "targetHandle": "input_pin"}]

@app.post("/api/macro/run")
def run_macro(req: MacroRunRequest):
    if executor.running:
        return {"status": "error", "message": "Macro is already running"}

    all_nodes_dict = {}
    for n_id, n_data in req.nodes.items():
        n_type = n_data.get("type")
        if n_type in NODE_MAP:
            all_nodes_dict[n_id] = NODE_MAP[n_type](node_id=n_id, config=n_data.get("config", {}))

    if not executor.start(all_nodes_dict, req.links):
        return {"status": "error", "message": "Start node is required"}
    return {"status": "started"}

@app.post("/api/macro/stop")
def stop_macro():
    executor.stop()
    return {"status": "stopped"}

@app.get("/api/scripts")
def list_scripts():
    script_files = []
    if os.path.exists(SCRIPTS_DIR):
        for root, dirs, files in os.walk(SCRIPTS_DIR):
            for file in files:
                if file.endswith(".json"):
                    rel_path = os.path.relpath(os.path.join(root, file), SCRIPTS_DIR)
                    script_files.append(rel_path.replace("\\", "/"))
    return script_files

@app.post("/api/scripts/save")
async def save_script(request: Request):
    data = await request.json()
    raw_name = _sanitize_script_name(data.get("name", "macro_1"))
    overwrite = bool(data.get("overwrite", False))
    generate_batch = bool(data.get("generate_batch", False))
    script_folder = os.path.join(SCRIPTS_DIR, raw_name)
    save_path = os.path.join(script_folder, f"{raw_name}.json")

    if os.path.exists(save_path) and not overwrite:
        return {
            "status": "exists",
            "message": f"'{raw_name}' 매크로가 이미 있습니다. 덮어쓸까요?",
            "name": raw_name,
        }

    os.makedirs(script_folder, exist_ok=True)

    # 디스크 저장본: React {nodes, edges} + 상대 image_path, image_url 없음
    cleaned = _strip_non_serializable(data.get("macro_data") or {})
    cleaned = _bundle_images_for_save(cleaned, script_folder)

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    batch_path = None
    if generate_batch:
        batch_path = _write_script_batch(script_folder, raw_name)

    # 프론트 동기화용: 절대 경로 + image_url
    runtime = json.loads(json.dumps(cleaned))
    runtime = _attach_runtime_image_fields(runtime, raw_name, script_folder)

    return {
        "status": "saved",
        "path": save_path.replace("\\", "/"),
        "name": raw_name,
        "batch_path": batch_path.replace("\\", "/") if batch_path else None,
        "macro_data": runtime,
    }


@app.post("/api/scripts/load")
async def load_script(request: Request):
    """scripts/ 아래 상대 경로 전체로 로드. 예: macro_fgo/macro_fgo.json"""
    body = await request.json()
    rel_path = (body.get("path") or body.get("name") or "").strip().replace("\\", "/")
    if not rel_path:
        return {"status": "error", "message": "path required"}

    # 경로 탈출 방지
    if rel_path.startswith("/") or ".." in rel_path.split("/"):
        return {"status": "error", "message": "Invalid path"}

    if not rel_path.endswith(".json"):
        # 이름만 온 경우 scripts/<name>/<name>.json 시도
        candidate = f"{rel_path}/{rel_path}.json"
        if os.path.isfile(os.path.join(SCRIPTS_DIR, candidate.replace("/", os.sep))):
            rel_path = candidate
        else:
            rel_path = f"{rel_path}.json"

    load_path = os.path.abspath(os.path.join(SCRIPTS_DIR, rel_path.replace("/", os.sep)))
    scripts_root = os.path.abspath(SCRIPTS_DIR)
    try:
        if os.path.commonpath([load_path, scripts_root]) != scripts_root:
            return {"status": "error", "message": "Invalid path"}
    except ValueError:
        return {"status": "error", "message": "Invalid path"}
    if not os.path.isfile(load_path):
        return {"status": "error", "message": "File not found"}

    with open(load_path, "r", encoding="utf-8") as f:
        macro_data = json.load(f)

    # React 포맷만 지원
    if not isinstance(macro_data, dict) or "nodes" not in macro_data or "edges" not in macro_data:
        return {
            "status": "error",
            "message": "React {nodes, edges} 포맷만 지원합니다. (옛 DPG 포맷 미지원)",
        }

    script_folder = os.path.dirname(load_path)
    script_rel_name = os.path.relpath(script_folder, SCRIPTS_DIR).replace("\\", "/")
    runtime = _attach_runtime_image_fields(macro_data, script_rel_name, script_folder)
    return {"status": "success", "path": rel_path, "macro_data": runtime}


class ScriptRunRequest(BaseModel):
    path: str


@app.post("/api/scripts/run")
async def run_saved_script(req: ScriptRunRequest):
    class _Body:
        async def json(self):
            return {"path": req.path}

    loaded = await load_script(_Body())
    if loaded.get("status") != "success":
        return loaded

    macro = loaded["macro_data"]
    nodes = {}
    for node in macro.get("nodes") or []:
        data = node.get("data") or {}
        nodes[node["id"]] = {
            "type": data.get("type"),
            "config": data.get("config") or {},
        }
    links = [
        {
            "source": edge.get("source"),
            "sourceHandle": edge.get("sourceHandle") or "output_pin",
            "target": edge.get("target"),
            "targetHandle": edge.get("targetHandle") or "input_pin",
        }
        for edge in macro.get("edges") or []
    ]
    return run_macro(MacroRunRequest(nodes=nodes, links=links))


@app.post("/api/scripts/{name:path}/load")
async def load_script_legacy(name: str):
    """하위 호환: URL 경로로도 로드 가능."""
    class _Body:
        async def json(self_inner):
            return {"path": name}

    return await load_script(_Body())

class CaptureRequest(BaseModel):
    node_id: str
    delay: int = 0

@app.post("/api/capture/start")
def start_capture(req: CaptureRequest):
    from backend.engine import capture

    def on_captured(file_path):
        import os
        try:
            rel_path = os.path.relpath(file_path, BASE_DIR)
            url_path = f"/static/{rel_path}".replace("\\", "/")
        except:
            url_path = file_path

        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "capture_complete",
                    "node_id": req.node_id,
                    "file_path": file_path,
                    "url": url_path
                }),
                main_loop
            )

    import threading
    threading.Thread(
        target=capture.start_capture_tool,
        args=(on_captured,),
        kwargs={"delay": req.delay},
        daemon=True
    ).start()
    return {"status": "capture_started"}

class RegionRequest(BaseModel):
    node_id: str

@app.post("/api/region/start")
def start_region(req: RegionRequest):
    from backend.engine import capture

    def on_region_selected(x, y, w, h):
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "region_complete",
                    "node_id": req.node_id,
                    "search_region": [x, y, w, h]
                }),
                main_loop
            )

    import threading
    threading.Thread(target=capture.start_region_tool, args=(on_region_selected,), daemon=True).start()
    return {"status": "region_started"}

class CoordinateRequest(BaseModel):
    node_id: str

# node_id -> {"x": int, "y": int} | {"cancelled": True}
_coordinate_results = {}

@app.post("/api/coordinate/start")
def start_coordinate(req: CoordinateRequest):
    """pynput 전역 좌표 피커 결과를 브라우저로 전달합니다. 클릭/F8 확정 / Esc 취소."""
    from backend.engine import capture

    _coordinate_results.pop(req.node_id, None)
    state.update_status("좌표 선택 모드: 클릭 또는 F8 확정 / Esc 취소")

    def on_coordinate_picked(x, y):
        _coordinate_results[req.node_id] = {"x": int(x), "y": int(y)}
        state.update_status(f"좌표 선택됨: ({x}, {y})")
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "coordinate_complete",
                    "node_id": req.node_id,
                    "x": int(x),
                    "y": int(y),
                }),
                main_loop
            )

    def on_coordinate_cancelled():
        _coordinate_results[req.node_id] = {"cancelled": True}
        state.update_status("좌표 선택 취소됨")
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "coordinate_cancelled",
                    "node_id": req.node_id,
                }),
                main_loop
            )

    import threading
    threading.Thread(
        target=capture.start_coordinate_tool,
        args=(on_coordinate_picked,),
        kwargs={"on_cancel": on_coordinate_cancelled},
        daemon=True
    ).start()
    return {"status": "coordinate_started"}

@app.get("/api/coordinate/poll/{node_id}")
def poll_coordinate(node_id: str):
    """WebSocket이 백그라운드 탭에서 늦을 때를 위한 폴링."""
    result = _coordinate_results.pop(node_id, None)
    if not result:
        return {"done": False}
    return {"done": True, **result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
