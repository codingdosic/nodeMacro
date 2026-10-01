import math
import os


def validate_macro(nodes, links, node_map):
    """실행 전에 확실한 오류와 의심스러운 구성을 가볍게 검사한다."""
    issues = []
    seen = set()

    def add(level, code, message, node_id=None):
        key = (level, code, node_id)
        if key not in seen:
            seen.add(key)
            issues.append({
                "level": level,
                "code": code,
                "message": message,
                "node_id": node_id,
            })

    node_ids = set(nodes)
    starts = []
    adjacency = {node_id: [] for node_id in node_ids}
    reverse = {node_id: [] for node_id in node_ids}

    for node_id, data in nodes.items():
        node_type = data.get("type")
        if node_type == "start":
            starts.append(node_id)
        if node_type not in node_map:
            add("error", "unsupported_node", f"지원하지 않는 노드입니다: {node_type}", node_id)
            continue

        config = data.get("config", {})
        if not isinstance(config, dict):
            add("error", "invalid_config", "노드 설정 형식이 올바르지 않습니다.", node_id)
            continue

        schema = node_map[node_type](node_id=node_id, config=config).get_schema()
        for name, field in schema.items():
            if field.get("type") == "select":
                value = config.get(name, field.get("default"))
                if value not in field.get("options", []):
                    add("error", f"invalid_option:{name}", f"'{field.get('label', name)}' 선택값이 올바르지 않습니다.", node_id)
                continue
            if field.get("type") != "number":
                continue
            value = config.get(name, field.get("default", 0))
            try:
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError
            except (TypeError, ValueError):
                add("error", f"invalid_number:{name}", f"'{field.get('label', name)}' 값이 숫자가 아닙니다.", node_id)
                continue
            if "min" in field and number < field["min"]:
                add("error", f"number_min:{name}", f"'{field.get('label', name)}' 값은 {field['min']} 이상이어야 합니다.", node_id)
            if "max" in field and number > field["max"]:
                add("error", f"number_max:{name}", f"'{field.get('label', name)}' 값은 {field['max']} 이하여야 합니다.", node_id)

        if node_type == "window" and not str(config.get("title", "")).strip():
            add("error", "window_title", "창 제목을 입력하세요.", node_id)
        if node_type == "launch":
            target = str(config.get("path", "")).strip().strip('"')
            resolved = os.path.expandvars(os.path.expanduser(target))
            if not target:
                add("error", "launch_path", "실행할 파일, 문서 또는 URL을 입력하세요.", node_id)
            elif not resolved.lower().startswith(("http://", "https://")) and not os.path.exists(resolved):
                add("error", "launch_missing", "실행할 파일 또는 문서를 찾을 수 없습니다.", node_id)
        if node_type in {"image", "if"}:
            image_path = config.get("image_path")
            if not isinstance(image_path, str) or not image_path.strip():
                add("error", "image_required", "검색할 이미지를 캡처하거나 지정하세요.", node_id)
            elif not os.path.isfile(image_path):
                add("error", "image_missing", "검색 이미지 파일을 찾을 수 없습니다.", node_id)
        if node_type == "keyboard":
            mode = config.get("mode", "hotkey")
            value = config.get("keys", ["enter"]) if mode == "hotkey" else config.get("string", "")
            if not value:
                add("warning", "empty_keyboard", "입력할 키 또는 문자열이 비어 있습니다.", node_id)

    if len(starts) != 1:
        add("error", "start_count", "시작 노드는 정확히 하나여야 합니다.", starts[0] if starts else None)

    used_outputs = set()
    for link in links:
        if not isinstance(link, dict):
            add("error", "invalid_link", "연결 정보 형식이 올바르지 않습니다.")
            continue
        source, target = link.get("source"), link.get("target")
        if source not in node_ids or target not in node_ids:
            add("error", "broken_link", "존재하지 않는 노드를 가리키는 연결이 있습니다.", source if source in node_ids else target if target in node_ids else None)
            continue
        source_type = nodes[source].get("type")
        allowed_handles = {
            "if": {"true_out_pin", "false_out_pin"},
            "loop": {"loop_out_pin", "exit_out_pin"},
        }.get(source_type, {"output_pin"})
        source_handle = link.get("sourceHandle") or "output_pin"
        if source_handle not in allowed_handles:
            add("error", "invalid_output", "노드 종류와 맞지 않는 출력 연결이 있습니다.", source)
            continue
        output = (source, source_handle)
        if output in used_outputs:
            add("error", "duplicate_output", "같은 출력 핀에 연결이 둘 이상 있습니다.", source)
            continue
        used_outputs.add(output)
        adjacency[source].append(target)
        reverse[target].append(source)

    if len(starts) == 1:
        reachable = set()
        pending = [starts[0]]
        while pending:
            node_id = pending.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            pending.extend(adjacency[node_id])
        for node_id in node_ids - reachable:
            add("warning", "unreachable", "시작 노드에서 도달할 수 없는 노드입니다.", node_id)
        if not adjacency[starts[0]]:
            add("warning", "empty_macro", "시작 노드가 다른 노드에 연결되어 있지 않습니다.", starts[0])

    def has_ancestor(node_id, node_types):
        checked = set()
        pending = list(reverse[node_id])
        while pending:
            parent = pending.pop()
            if parent in checked:
                continue
            checked.add(parent)
            if nodes[parent].get("type") in node_types:
                return True
            pending.extend(reverse[parent])
        return False

    for node_id, data in nodes.items():
        node_type = data.get("type")
        config = data.get("config") if isinstance(data.get("config"), dict) else {}
        if node_type in {"mouse_click", "mouse_move", "mouse_drag"} and not has_ancestor(node_id, {"click", "image", "if"}):
            add("warning", "missing_position", "앞에서 좌표 또는 이미지를 지정하지 않아 이전 마우스 위치를 사용할 수 있습니다.", node_id)
        if node_type == "click" and config.get("relative_to_window") and not has_ancestor(node_id, {"window"}):
            add("warning", "missing_window", "창 기준 좌표 앞에 창 선택 노드가 없습니다.", node_id)

    color = {}
    path = []

    def visit(node_id):
        color[node_id] = 1
        path.append(node_id)
        for target in adjacency[node_id]:
            if color.get(target) == 1:
                cycle = path[path.index(target):]
                if not any(nodes[item].get("type") == "loop" for item in cycle):
                    add("warning", "cycle_without_loop", "반복 노드가 없는 순환 연결은 무한 실행될 수 있습니다.", target)
            elif color.get(target) != 2:
                visit(target)
        path.pop()
        color[node_id] = 2

    for node_id in node_ids:
        if color.get(node_id) is None:
            visit(node_id)

    return issues
