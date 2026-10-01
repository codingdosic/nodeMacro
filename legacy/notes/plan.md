# NodeMacro 마이그레이션 계획

**목표**: Dear PyGui 단일 프로세스 → React Flow (프론트) + FastAPI (백엔드) 분리 구조

---

## 재사용 / 교체 분류

| 파일 | 처리 | 내용 |
|---|---|---|
| `executor.py` | ✅ 재사용 | threading 실행 로직 UI 무관 |
| `capture.py` | ✅ 재사용 | Tkinter 오버레이 독립적 |
| `state.py` | 🔧 부분 수정 | `dpg.set_value` → WebSocket 브로드캐스트 |
| `base_node.py` | 🔧 핵심 수정 | dpg 의존성 제거, 순수 Python |
| `action_nodes.py` | 🔧 핵심 수정 | dpg 위젯 코드 제거, 실행 로직만 유지 |
| `main.py` | ❌ 교체 | FastAPI 서버로 대체 |

---

## 목표 디렉토리 구조

```
macro/
├── backend/
│   ├── main.py               ← FastAPI 앱, WebSocket
│   ├── engine/
│   │   ├── executor.py       ← 기존 재사용
│   │   ├── state.py          ← WebSocket으로 수정
│   │   └── capture.py        ← 기존 그대로
│   └── nodes/
│       ├── base_node.py      ← dpg 제거
│       └── action_nodes.py   ← dpg 제거
│
└── frontend/
    └── src/
        ├── App.jsx
        ├── NodeEditor.jsx
        └── nodes/            ← 노드별 커스텀 UI
```

---

## Phase 1: 노드 클래스 dpg 분리

> **현황**: ✅ 완료

각 노드 클래스의 UI 코드(`_add_widgets`, `create_ui`)와 실행 코드(`execute`)가 혼재.
dpg를 import하지 않아도 `execute()`가 동작하도록 분리.

### 변경 방향

```python
# 변경 전: 하나의 클래스에 UI + 실행 혼재
class MouseClickNode(BaseNode):
    def _add_widgets(self):       # dpg 코드
        dpg.add_combo(...)
    def execute(self):             # 실행 코드
        pyautogui.click(...)

# 변경 후: 설정값을 생성자에서 받아, execute만 남김
class MouseClickNode(BaseNode):
    def __init__(self, config={}):
        self.click_type = config.get("click_type", "left")
        self.x = config.get("x", 0)
        self.y = config.get("y", 0)

    def execute(self, macro_state):
        pyautogui.click(self.x, self.y, button=self.click_type)
        return "output"

    def get_schema(self):    # 프론트에 노드 설정 UI 정보 전달
        return { "click_type": {"type": "select", ...} }
```

### 할 일

- [x] `backend/` 디렉토리 생성 및 기존 `engine/`, `nodes/` 복사
- [x] `base_node.py`: dpg import 및 `create_ui()`, `_add_widgets()` 제거, `execute(macro_state)` 시그니처 통일
- [x] `action_nodes.py`: 각 노드 클래스별로 dpg 코드 제거, 설정값을 `__init__`의 `config` 파라미터로 수신하도록 변경
- [x] `state.py`: `dpg.set_value` 제거, 상태 업데이트는 콜백 방식으로 추상화
- [x] `executor.py`: `_run_loop` 내 dpg import 제거, `macro_state` 딕셔너리 직접 관리로 변경
- [x] 리팩토링된 노드로 기본 실행 동작 확인 (단위 테스트 수준)

---

## Phase 2: FastAPI 서버 구축

> **현황**: ✅ 완료

### API 설계

```
GET  /api/nodes/types         ← NODE_MAP 목록 및 각 노드 schema 반환
GET  /api/scripts             ← 저장된 매크로 파일 목록
POST /api/scripts/save        ← 매크로 저장
POST /api/scripts/{name}/load ← 매크로 불러오기
POST /api/macro/run           ← 실행 시작
POST /api/macro/stop          ← 실행 중단
WS   /ws                      ← 실행 상태 실시간 스트리밍
```

### 할 일

- [x] `pip install fastapi uvicorn websockets` 의존성 추가
- [x] `backend/main.py`: FastAPI 앱 생성, 정적 파일 서빙 설정
- [x] `/api/nodes/types` 엔드포인트: NODE_MAP 기반 노드 목록 + schema 반환
- [x] `/api/scripts` 엔드포인트: 저장/불러오기 (기존 `save_macro`, `load_macro` 로직 이식)
- [x] `/api/macro/run`, `/api/macro/stop` 엔드포인트: Executor 연동
- [x] WebSocket `/ws` 엔드포인트: 실행 상태(현재 노드, 완료, 오류) 브로드캐스트
- [x] `state.py` 수정: 상태 업데이트 시 WebSocket 브로드캐스트 호출
- [x] 이미지 업로드 엔드포인트 + 정적 파일 서빙 (`/static/images`)

---

## Phase 3: React Flow 프론트엔드

> **현황**: ✅ 완료

### 주요 컴포넌트

- `NodeEditor.jsx`: React Flow 메인 캔버스 (줌/팬/미니맵 기본 제공)
- `NodePalette.jsx`: 노드 추가 패널 (백엔드 `/api/nodes/types` 로드)
- `nodes/`: 노드 타입별 커스텀 UI 컴포넌트
- `useWebSocket.js`: 실행 상태 실시간 수신 훅

### 할 일

- [x] `frontend/` 디렉토리 생성, React 프로젝트 초기화
- [x] `reactflow` 패키지 설치
- [x] `NodeEditor.jsx`: React Flow 캔버스, 줌/팬/미니맵 설정
- [x] `NodePalette.jsx`: 노드 타입 목록 표시, 드래그로 캔버스에 추가
- [x] 노드별 커스텀 컴포넌트 구현 (설정 입력 UI)
- [x] Undo/Redo: `useNodesState` + history 스택 구현 (React Flow 기본 상태 관리로 대체)
- [x] 실행/중단 버튼 -> `/api/macro/run`, `/api/macro/stop` 호출
- [x] `useWebSocket.js`: `/ws` 연결, 실행 상태 실시간 반영
- [x] 저장/불러오기 UI 연동
- [x] 빌드 결과물을 FastAPI 정적 파일로 서빙 설정

---

## Phase 4: 캡처 도구 연동

> **현황**: ✅ 완료

### 할 일

- [x] `POST /api/capture/start` 엔드포인트: 백엔드에서 Tkinter 캡처 창 실행
- [x] 캡처 완료 후 이미지 경로를 WebSocket으로 프론트에 전달
- [x] 프론트: 캡처 완료 이벤트 수신 후 해당 노드 이미지 미리보기 업데이트

---

## 진행 현황

| Phase | 상태 | 완료일 |
|---|---|---|
| Phase 1: 노드 dpg 분리 | ✅ 완료 | 2026-07-14 |
| Phase 2: FastAPI 서버 | ✅ 완료 | 2026-07-14 |
| Phase 3: React Flow UI | ✅ 완료 | 2026-07-14 |
| Phase 4: 캡처 도구 연동 | ✅ 완료 | 2026-07-14 |
