import os
import sys
import json
import shutil
import asyncio
import time
import tempfile
import secrets
from typing import List, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.nodes.action_nodes import (
    StartNode, LaunchNode, CoordNode, WaitNode, ImageNode, MouseClickNode,
    LoopNode, IfNode, KeyboardNode, MouseMoveNode, MouseSequenceNode, MouseScrollNode, MouseDragNode,
    WindowNode,
)
from backend.engine.executor import Executor
from backend.engine.recorder import Recorder
from backend.engine import state
from backend.validation import validate_macro
from backend.config import (
    APP_ID, APP_NAME, APP_VERSION, CAPTURES_DIR, HOST, PACKAGE_DIR, PORT,
    SCRIPT_FORMAT, SCRIPT_SCHEMA_VERSION, SCRIPTS_DIR, SESSION_TOKEN,
    HOTKEY_CHOICES, SETTINGS, save_settings,
)

app = FastAPI(title=f"{APP_NAME} API", docs_url=None, redoc_url=None)
recorder = Recorder()

BASE_DIR = str(PACKAGE_DIR)
SCRIPTS_DIR = str(SCRIPTS_DIR)
ASSETS_DIR = str(CAPTURES_DIR)
ALLOWED_ORIGINS = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}
if os.environ.get("D5MACRO_DEV") == "1":
    ALLOWED_ORIGINS.update({"http://127.0.0.1:5173", "http://localhost:5173"})


@app.middleware("http")
async def local_request_guard(request: Request, call_next):
    host = request.headers.get("host", "").split(":", 1)[0].lower()
    if host not in {HOST, "localhost"}:
        return JSONResponse({"status": "error", "message": "Invalid host"}, status_code=403)
    protected = request.url.path.startswith(("/api/", "/media/", "/captures/"))
    if protected and request.url.path != "/api/health":
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"status": "error", "message": "Invalid origin"}, status_code=403)
        token = request.headers.get("x-d5-token") or request.cookies.get("d5_session")
        if not secrets.compare_digest(token or "", SESSION_TOKEN):
            return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws://127.0.0.1:8000 ws://localhost:8000; frame-ancestors 'none'"
    )
    return response


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


def _version_tuple(value: str):
    try:
        return tuple(int(part) for part in str(value).split(".")[:3])
    except ValueError:
        return (0,)


def _write_script_batch(script_folder: str, script_name: str):
    if getattr(sys, "frozen", False):
        command = f'"{sys.executable}"'
    else:
        launcher = os.path.join(BASE_DIR, "launcher.py")
        command = f'"{sys.executable}" "{launcher}"'
    content = f'@echo off\n{command} --run-script "%~dp0\\{script_name}.json"\n'
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

    # 브라우저 미리보기 URL은 scripts/ 또는 captures/ 아래로만 해석한다.
    if path.startswith("http://") or path.startswith("https://"):
        if "/media/" in path:
            path = os.path.join(SCRIPTS_DIR, path.split("/media/", 1)[1].split("?", 1)[0].replace("/", os.sep))
        elif "/captures/" in path:
            path = os.path.join(ASSETS_DIR, path.split("/captures/", 1)[1].split("?", 1)[0].replace("/", os.sep))
        else:
            return None
    elif path.startswith("/media/"):
        path = os.path.join(SCRIPTS_DIR, path[len("/media/"):].split("?", 1)[0].replace("/", os.sep))
    elif path.startswith("/captures/"):
        path = os.path.join(ASSETS_DIR, path[len("/captures/"):].split("?", 1)[0].replace("/", os.sep))

    if os.path.isabs(path):
        return path if os.path.isfile(path) else None

    candidate = os.path.join(SCRIPTS_DIR, path.replace("/", os.sep))
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
            config["image_url"] = f"/media/{url_rel.removeprefix('scripts/')}?t={stamp}"
        else:
            base = os.path.basename(rel)
            config["image_url"] = (
                f"/media/{script_rel_name}/imgs/{base}?t={stamp}"
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
    return {
        "format": SCRIPT_FORMAT,
        "schema_version": SCRIPT_SCHEMA_VERSION,
        "created_with": APP_VERSION,
        "minimum_app_version": APP_VERSION,
        "nodes": nodes_out,
        "edges": edges_out,
    }

# 사용자 이미지 외에는 파일 시스템을 공개하지 않는다.
app.mount("/media", StaticFiles(directory=SCRIPTS_DIR), name="script_media")
app.mount("/captures", StaticFiles(directory=ASSETS_DIR), name="captures")

# Static files for frontend build
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

import mimetypes

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="frontend_assets")

    @app.get("/")
    def serve_frontend_index():
        response = FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
        response.set_cookie("d5_session", SESSION_TOKEN, httponly=True, samesite="strict")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/favicon.svg")
    def serve_favicon():
        return FileResponse(os.path.join(FRONTEND_DIST, "favicon.svg"))


NODE_MAP = {
    "start": StartNode,
    "launch": LaunchNode,
    "window": WindowNode,
    "click": CoordNode,
    "wait": WaitNode,
    "image": ImageNode,
    "mouse_click": MouseClickNode,
    "keyboard": KeyboardNode,
    "loop": LoopNode,
    "if": IfNode,
    "mouse_move": MouseMoveNode,
    "mouse_sequence": MouseSequenceNode,
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

# We need the main event loop to dispatch events from executor thread
main_loop = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

    def threadsafe_status_update(message, key=None, params=None):
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "status",
                    "message": message,
                    "key": key,
                    "params": params or {},
                }),
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

    def threadsafe_recorder_update(payload):
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "recorder", **payload}),
                main_loop,
            )

    state.status_callback = threadsafe_status_update
    state.execution_callback = threadsafe_execution_update
    recorder.callback = threadsafe_recorder_update


@app.on_event("shutdown")
async def shutdown_event():
    executor.close()
    recorder.close()
    state.stop_listeners()


@app.get("/api/health")
def health():
    return {
        "status": "ok", "app": APP_ID, "version": APP_VERSION,
        "running": executor.running, "recording": recorder.running,
    }


class SettingsRequest(BaseModel):
    record_stop_key: str
    panic_stop_key: str


@app.get("/api/settings")
def get_settings():
    return {**SETTINGS, "hotkey_choices": HOTKEY_CHOICES}


@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    try:
        return {**save_settings(req.model_dump()), "hotkey_choices": HOTKEY_CHOICES}
    except ValueError as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    token = websocket.cookies.get("d5_session") or websocket.headers.get("x-d5-token")
    if origin not in ALLOWED_ORIGINS or not secrets.compare_digest(token or "", SESSION_TOKEN):
        await websocket.close(code=1008)
        return
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
    allow_warnings: bool = False
    start_node_id: str | None = None

@app.post("/api/macro/run")
def run_macro(req: MacroRunRequest):
    if executor.running:
        return {"status": "error", "message": "Macro is already running"}
    if recorder.running:
        return {"status": "error", "message": "녹화 중에는 매크로를 실행할 수 없습니다."}

    issues = validate_macro(req.nodes, req.links, NODE_MAP)
    errors = [issue for issue in issues if issue["level"] == "error"]
    if errors:
        return {"status": "validation_error", "message": errors[0]["message"], "issues": issues}
    if issues and not req.allow_warnings:
        return {"status": "validation_warning", "message": issues[0]["message"], "issues": issues}

    all_nodes_dict = {}
    for n_id, n_data in req.nodes.items():
        n_type = n_data.get("type")
        if n_type in NODE_MAP:
            all_nodes_dict[n_id] = NODE_MAP[n_type](node_id=n_id, config=n_data.get("config", {}))

    if req.start_node_id and req.start_node_id not in all_nodes_dict:
        return {"status": "error", "message": "선택한 시작 노드를 찾을 수 없습니다."}
    if not executor.start(all_nodes_dict, req.links, req.start_node_id):
        return {"status": "error", "message": "Start node is required"}
    return {"status": "started", "issues": issues}

@app.post("/api/macro/stop")
def stop_macro():
    executor.stop()
    return {"status": "stopped"}


@app.post("/api/recorder/start")
def start_recorder():
    if executor.running:
        return {"status": "error", "message": "매크로 실행 중에는 녹화할 수 없습니다."}
    if not recorder.start(delay=3):
        return {"status": "error", "message": "이미 녹화 중입니다."}
    return {"status": "countdown", "seconds": 3}


@app.post("/api/recorder/stop")
def stop_recorder():
    if not recorder.stop(drop_last_click=True):
        return {"status": "error", "message": "녹화 중이 아닙니다."}
    return {"status": "stopping"}

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


@app.post("/api/scripts/open-folder")
def open_scripts_folder():
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    os.startfile(SCRIPTS_DIR)
    return {"status": "opened"}


@app.post("/api/scripts/delete")
async def delete_script(request: Request):
    body = await request.json()
    rel_path = str(body.get("path") or "").strip().replace("\\", "/")
    if not rel_path.endswith(".json") or rel_path.startswith("/") or ".." in rel_path.split("/"):
        return JSONResponse({"status": "error", "message": "Invalid path"}, status_code=400)

    scripts_root = os.path.realpath(SCRIPTS_DIR)
    script_path = os.path.realpath(os.path.join(scripts_root, rel_path.replace("/", os.sep)))
    try:
        if os.path.commonpath([script_path, scripts_root]) != scripts_root or not os.path.isfile(script_path):
            raise ValueError
    except ValueError:
        return JSONResponse({"status": "error", "message": "File not found"}, status_code=404)

    script_folder = os.path.dirname(script_path)
    script_name = os.path.splitext(os.path.basename(script_path))[0]
    if script_folder != scripts_root and os.path.basename(script_folder).casefold() == script_name.casefold():
        shutil.rmtree(script_folder)
    else:
        os.remove(script_path)
    return {"status": "deleted", "path": rel_path}

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

    if os.path.isfile(save_path):
        shutil.copy2(save_path, f"{save_path}.bak")
    fd, temp_path = tempfile.mkstemp(prefix=f".{raw_name}-", suffix=".tmp", dir=script_folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(cleaned, file, indent=2, ensure_ascii=False)
        os.replace(temp_path, save_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

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
    force = bool(body.get("force", False))
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

    if not isinstance(macro_data, dict) or macro_data.get("format") != SCRIPT_FORMAT:
        return {
            "status": "error",
            "message": "지원하는 D5 Macro 스크립트가 아닙니다.",
        }
    schema_version = macro_data.get("schema_version")
    minimum_version = macro_data.get("minimum_app_version", "0.0.0")
    warning = None
    if not isinstance(schema_version, int) or schema_version > SCRIPT_SCHEMA_VERSION:
        warning = "이 스크립트는 더 새로운 파일 형식으로 저장되었습니다. 일부 설정이 올바르게 동작하지 않을 수 있습니다."
    elif _version_tuple(minimum_version) > _version_tuple(APP_VERSION):
        warning = f"이 스크립트에는 D5 Macro {minimum_version} 이상이 필요합니다."
    if warning and not force:
        return {"status": "warning", "message": warning, "path": rel_path}

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
    return run_macro(MacroRunRequest(nodes=nodes, links=links, allow_warnings=True))


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
        try:
            rel_path = os.path.relpath(file_path, ASSETS_DIR)
            if rel_path.startswith(".."):
                raise ValueError("capture outside capture directory")
            url_path = f"/captures/{rel_path}".replace("\\", "/")
        except (OSError, ValueError):
            url_path = ""

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
    state.update_status(
        "좌표 선택 모드: 클릭 또는 F8 확정 / Esc 취소",
        "status_coordinate_mode",
    )

    def on_coordinate_picked(x, y):
        _coordinate_results[req.node_id] = {"x": int(x), "y": int(y)}
        state.update_status(
            f"좌표 선택됨: ({x}, {y})",
            "status_coordinate_selected",
            x=x,
            y=y,
        )
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
        state.update_status("좌표 선택 취소됨", "status_coordinate_cancelled")
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
    uvicorn.run(app, host=HOST, port=PORT)
