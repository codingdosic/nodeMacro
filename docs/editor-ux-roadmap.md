# 에디터 UX / 노드 개선 로드맵 & 세션 인수인계

> 목적: React Flow 기반 브라우저 에디터의 UX·노드 기능을, Dear PyGui 시절 동작과 맞추거나 그 이상으로 보완한다.  
> 이 문서는 **구현 순서·세부 요구사항·테스트·세션 간 인수인계**의 단일 기준이다.

---

## 0. 세션 인수인계 지침 (필수)

에이전트/개발자는 작업을 이어받을 때 아래를 따른다.

### 0.1 세션 시작 시

1. 이 문서를 읽고 **「진행 상태」** 표에서 첫 `pending` / `in_progress` 항목을 확인한다.
2. **관련 파일**·**완료 정의(DoD)**·**테스트 방법**을 확인한 뒤 해당 항목만 착수한다.
3. 문서와 코드가 어긋나면 **코드를 우선**하되, 문서의 진행 상태/메모를 즉시 고친다.

### 0.2 작업 수행 중

- 한 세션에서는 가능하면 **한 단계(또는 의존성이 묶인 소그룹)**만 완료한다.
- 범위 밖 리팩터·문서 무관 변경은 하지 않는다.
- 프론트 변경 후 사용자가 `:8000`으로 본다면 `frontend`에서 `npm run build`가 필요할 수 있다. (`frontend/dist` 서빙)

### 0.3 작업 완료 후 (체크리스트)

- [ ] DoD를 만족하는지 확인
- [ ] 아래 **테스트 방법**을 실행(또는 사용자에게 안내)하고 결과를 메모
- [ ] 이 문서 **「진행 상태」**를 `done` / `pending` / `blocked`로 갱신
- [ ] **「변경 이력」**에 날짜·요약·터치 파일 추가
- [ ] 남은 이슈·확인 필요 사항을 **「열린 이슈」**에 기록
- [ ] 사용자에게 **다음 세션 시작 프롬프트**를 안내(또는 문서 링크)

### 0.4 다음 세션 시작 프롬프트 (복사용)

```
docs/editor-ux-roadmap.md 를 읽고 인수인계 지침을 따른 뒤,
「진행 상태」표에서 아직 끝나지 않은 가장 앞 단계부터 이어서 구현해줘.
완료 후 테스트 방법을 안내하고, 같은 문서의 진행 상태·변경 이력·열린 이슈를 업데이트해줘.
프론트를 :8000 으로 보는 경우 필요하면 npm run build 도 해줘.
```

특정 단계만 지정할 때:

```
docs/editor-ux-roadmap.md 의 단계 N(제목)만 구현·테스트·문서 업데이트해줘.
```

저장/로드·undo 트랙 (13–15) — 새 세션 시작용:

```
docs/editor-ux-roadmap.md 를 읽고 인수인계 지침을 따른 뒤,
단계 12(반복문)는 건너뛰고 「진행 상태」에서 13–15 중 아직 끝나지 않은 가장 앞 단계부터 구현해줘.
한 세션에서는 가능하면 한 단계(13 또는 14 또는 15)만 완료한다.

확정된 결정(문서 「확인사항 · 결정 내용」과 동일):
- 저장 레이아웃: scripts/<이름>/<이름>.json + scripts/<이름>/imgs/ (사용 이미지만 복사, image_path는 imgs/… 상대경로)
- JSON 정본: React {nodes, edges}만. 옛 DPG 포맷 미지원
- assets/: 서버 재시작 시 초기화
- 같은 이름 저장: 덮어쓰기 확인 UI
- Undo 1차: 구조 변경만(추가/삭제/연결/복붙/로드). 드래그·config 제외. Ctrl+Z / Ctrl+Y
- 참고: src/main.py 의 save_macro / load_macro / history_stack

완료 후 해당 단계 테스트 방법을 안내하고, 같은 문서의 진행 상태·변경 이력·열린 이슈를 업데이트해줘.
프론트를 :8000 으로 보는 경우 필요하면 npm run build 도 해줘.
```

한 단계만 지정할 때:

```
docs/editor-ux-roadmap.md 의 단계 13(저장·이미지 번들)만 구현·테스트·문서 업데이트해줘.
(14 로드 / 15 Undo·Redo 도 동일 형식)
```

---

## 1. 현재 아키텍처 요약 (컨텍스트)

| 구분 | 경로 / 역할 |
|------|-------------|
| 프론트 에디터 | `frontend/` — React + `@xyflow/react` |
| 커스텀 노드 UI | `frontend/src/GenericNode.jsx` |
| 에디터 캔버스 | `frontend/src/NodeEditor.jsx` |
| 노드 갱신 버스 | `frontend/src/nodeUpdateBus.js` (캡처/좌표 WS 결과 즉시 반영) |
| 백엔드 API | `backend/main.py` |
| 노드 실행 로직 | `backend/nodes/action_nodes.py` |
| 실행기 | `backend/engine/executor.py` |
| 좌표 피커(OS) | `backend/engine/coordinate_picker_cli.py` + `capture.start_coordinate_tool` |
| 스크립트 저장소 | `scripts/<name>/<name>.json` + `scripts/<name>/imgs/` |
| 캡처 스크래치 | `assets/capture_*.png` → `/static/assets/...` (서버 재시작 시 초기화) |
| 구 Dear PyGui 참고 | `src/` (저장 이미지 번들·undo 스펙 참고용) |

**확정된 제품 결정**

- 좌표 녹화 확정: **클릭** 또는 **F8** (커서 OS 좌표). Esc = 취소.
- 키보드 Ctrl+Z 등: 매크로 **단축키 조합 저장/실행**이 목적 (`hotkey`).
- 이미지 오프셋 시각화: 캡처 미리보기에서 **실제 클릭될 지점**을 사용자에게 보여 줌.
- 반복문: 본문 끝이 **다시 반복문 Input**으로 돌아와야 N회 반복. Exit는 루프 종료 후 경로.
- 매크로 저장: `scripts/<이름>/<이름>.json` + `imgs/`에 사용 이미지. React JSON만. 덮어쓰기 확인. `assets/`는 재시작 시 초기화.
- Undo 1차: 그래프 구조 변경만 (드래그·입력값 제외).

**실행/빌드**

```bash
# 백엔드
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 프론트 개발
cd frontend && npm run dev

# :8000 정적 서빙용 빌드
cd frontend && npm run build
```

---

## 2. 구현 순서 (의존도 · 작업량)

작은 UX 기반 → 편집 편의 → 노드 기능 → 검증 순.

| 단계 | 제목 | 예상 공수 | 의존 |
|------|------|-----------|------|
| 1 | 노드 내부 `nodrag` | S | — |
| 2 | 숫자 입력 수정 | S | — |
| 3 | 핸들 확대 + connectionRadius | S | — |
| 4 | output 핀 라벨 | S | 3과 함께 가능 |
| 5 | 노드 삭제 (Del / 우클릭) | M | 1 권장 |
| 6 | 엣지 삭제 / 우클릭 연결 해제 | M | 3, 5 |
| 7 | 드래그 다중 선택 | S–M | — |
| 8 | 복사 / 붙여넣기 | M | 5, 7 |
| 9 | 좌표 녹화 F8 | M | 백엔드 피커 |
| 10 | 키보드 녹화 UX + 조합 | M | 2 권장 |
| 11 | 이미지 오프셋 십자선 | M | — |
| 12 | 반복문 검증·안내 | S | 2, 4 |
| 13 | 저장: 이미지 번들 + 경로 갱신 | M | 백엔드 save |
| 14 | 로드 UX + 경로/URL 복원 | M | 13 |
| 15 | Undo / Redo | M–L | 5–8 권장 |

> 단계 13–15는 **3세션**으로 나눈다. 단계 12(반복문 검증)는 사용자가 별도 수행 — 에이전트는 13부터 착수.

---

## 3. 단계별 세부사항

### 단계 1 — 노드 내부 조작 시 드래그 방지

**목표:** 입력·버튼·미리보기 조작 중 노드가 움직이지 않음.

**구현 포인트**

- 노드 본문(`.node-body` 또는 인터랙티브 요소)에 React Flow `nodrag` / 필요 시 `nowheel` 클래스.
- `onMouseDown` stopPropagation만으로는 부족한 경우가 있어 `nodrag`를 우선.

**관련 파일:** `GenericNode.jsx`, `App.css` / `index.css`

**DoD:** 숫자 입력·셀렉트·버튼을 드래그해도 노드 position 불변. 헤더/빈 영역은 드래그 이동 가능.

**테스트**

1. 시작 노드 지연(ms) 입력창을 클릭·드래그.
2. 노드 전체가 따라 움직이지 않는지 확인.
3. 헤더를 드래그하면 정상 이동하는지 확인.

---

### 단계 2 — 숫자 입력 (`0` 고착, `0123`, 스피너)

**목표:** 빈 값 편집 가능, 선행 0 없음, 스피너로 값이 폭주하지 않음.

**원인(현재):** `type="number"` + 빈 문자열을 즉시 `0`으로 커밋.

**구현 포인트**

- 입력 중에는 문자열 draft 유지, `blur`/Enter 시 숫자 파싱·커밋.
- `min`이 필요하면 스키마에만 두고, 타이핑 중엔 강제하지 않음.
- 스피너(`step`) 동작을 쓰려면 controlled value와 draft 동기화 주의. 필요 시 스피너 숨김(`appearance`)도 검토.

**관련 파일:** `GenericNode.jsx` (`FieldControl`)

**DoD:** `0`을 지우고 `123` 입력 시 `0123`이 되지 않음. 빈 칸 후 포커스 아웃 시 합리적 기본값(0 또는 필드 default).

**테스트**

1. 시작 노드 지연을 0 → 전부 삭제 → 500 입력 → 포커스 아웃. 값이 `500`.
2. 반복 횟수에도 동일.
3. 스피너 클릭 시 한 스텝씩만 변하는지 확인.

---

### 단계 3 — 연결부(핸들) 확대

**목표:** 핀이 잘 보이고, 커서를 정밀히 올리지 않아도 연결 가능.

**구현 포인트**

- Handle 크기 CSS (예: 12–16px), 히트 영역 확대.
- React Flow `connectionRadius` (및 필요 시 `connectOnClick`) 조정.
- `:8000` 사용 시 빌드 필요.

**관련 파일:** `GenericNode.jsx`, `NodeEditor.jsx`, CSS

**DoD:** 핀 근처 넉넉한 영역에서 드래그 연결 가능.

**테스트:** 시작 Out → 대기 In 연결이 수월한지 체감 확인.

---

### 단계 4 — output 핀 텍스트 라벨

**목표:** 분기 핀 의미가 텍스트로 보임.

| 노드 | 핀 id | 라벨 예 |
|------|-------|---------|
| loop | `loop_out_pin` | Loop |
| loop | `exit_out_pin` | Exit |
| if | `true_out_pin` | True |
| if | `false_out_pin` | False |
| 일반 | `output_pin` | Out (선택) |

**관련 파일:** `GenericNode.jsx`, CSS

**DoD:** 반복문/조건문에서 위·아래 핀 구분이 라벨로 명확.

**테스트:** 반복문 노드만 놓고 Loop/Exit 라벨 가시성 확인.

---

### 단계 5 — 노드 삭제

**목표:** 선택 후 Delete/Backspace, 우클릭 메뉴「삭제」.

**구현 포인트**

- `deleteKeyCode={['Backspace', 'Delete']}` (입력 포커스 중 삭제는 막아야 함 — React Flow 기본/포커스 이슈 확인).
- `onNodesDelete` / `onEdgesDelete`로 state 정리.
- 커스텀 컨텍스트 메뉴: 노드 우클릭 → 삭제.

**관련 파일:** `NodeEditor.jsx`, `GenericNode.jsx`

**DoD:** 선택된 노드가 Del로 제거되고, 연결 엣지도 함께 정리됨.

**테스트**

1. 노드 선택 후 Delete.
2. 우클릭 → 삭제.
3. 입력창 포커스 중 Delete는 글자 삭제만 (노드 삭제 X).

---

### 단계 6 — 엣지 연결 해제

**목표:** 선 선택 후 삭제, 우클릭으로 연결 해제.

**구현 포인트**

- edges focusable/selectable.
- 엣지 컨텍스트 메뉴 또는 선택 + Delete.
- `onEdgesDelete`.

**관련 파일:** `NodeEditor.jsx`

**DoD:** 연결된 선을 제거해도 노드는 남음.

**테스트:** A→B 연결 후 선만 삭제, 노드 잔존 확인.

---

### 단계 7 — 다중 선택

**목표:** 빈 캔버스 드래그로 박스 선택, Shift 클릭 등.

**구현 포인트**

- `selectionOnDrag`, `panOnDrag` 조합 (예: 중버튼/우클릭 팬, 좌클릭 드래그는 선택 — 팀 취향에 맞게).
- 기본: `selectionMode`, `multiSelectionKeyCode="Shift"`.

**관련 파일:** `NodeEditor.jsx`

**DoD:** 여러 노드가 동시에 selected.

**테스트:** 드래그 박스로 2개 이상 선택되는지 확인.

---

### 단계 8 — 복사 / 붙여넣기

**목표:** Ctrl+C / Ctrl+V (또는 메뉴)로 노드 복제.

**구현 포인트**

- 선택된 노드(+내부 연결 엣지) 클립보드(또는 메모리) 저장.
- 붙여넣기 시 **새 id** 발급, position 오프셋, `onChange` 핸들러 재부착.
- 저장 JSON과 충돌 없게 id 규칙 유지 (`dndnode_${id++}` 등).

**관련 파일:** `NodeEditor.jsx`

**DoD:** 복사한 노드가 새 id로 붙고, 설정값이 유지됨.

**테스트:** 좌표 노드 복사 → 붙여넣기 → x/y 동일, id 다름.

---

### 단계 9 — 좌표 녹화 F8

**목표:** 클릭 픽 제거(또는 비활성). **F8 = 현재 커서 OS 좌표 확정**. Esc = 취소.

**구현 포인트**

- `coordinate_picker_cli.py`: 좌클릭 finish 제거 또는 무시. **F8**에서 `pyautogui.position()`으로 finish. Esc 취소.
- UI 문구: 「F8: 좌표 확정 / Esc: 취소」(Z·클릭 안내 삭제).
- 폴링 + WS 경로 유지.
- DPI awareness 유지.

**관련 파일:**  
`backend/engine/coordinate_picker_cli.py`, `capture.py`, `backend/main.py`, `GenericNode.jsx`

**DoD:** 다른 창 위를 클릭하지 않고, 커서만 올린 뒤 F8로 좌표가 노드에 반영. 멀티모니터에서 동작.

**테스트**

1. 좌표 녹화 클릭 → 상태창/힌트에 F8 안내.
2. 메모장 등 다른 창 위에 커서만 올리고 F8.
3. 해당 창이 클릭으로 활성화되지 않았는지, X/Y가 커서를 반영하는지 확인.
4. Esc로 취소되는지 확인.
5. 백엔드 콘솔에 `좌표 선택됨: (x, y)` 로그.

---

### 단계 10 — 키보드 노드 녹화 UX + 조합

**목표**

- 생성 직후(단축키 모드)에도 **키 녹화 버튼 표시**. (`mode === '단축키'`일 때; 기본값이 단축키면 처음부터 보여야 함. 현재 버그: 전환 후에야 보임 → 초기 config/mode 동기화 수정.)
- 버튼 토글: 1회 클릭 = 녹음 대기, **다시 클릭 = 확정 저장** 후 대기 종료.
- Ctrl+Z 등: modifier 누른 채 일반 키를 묶거나, 순서 배열을 `hotkey(*keys)`로 실행 (이미 백엔드 존재). 녹화 UX가 조합을 만들기 쉽게.

**관련 파일:** `GenericNode.jsx`, `backend/nodes/action_nodes.py` (스키마 default), 필요 시 schema options

**DoD**

- 새 키보드 노드에서 즉시 녹화 버튼 보임.
- Ctrl 다음 Z 녹화 → 실행 시 붙여넣기/실행취소 등 조합 동작(앱에 따라 다름).
- 녹화 중 다시 버튼 누르면 대기 종료.

**테스트**

1. 키보드 노드 드롭 → 녹화 버튼 즉시 표시.
2. 녹화 → Ctrl, Z → 버튼으로 종료 → config.keys 확인.
3. 간단 매크로로 메모장에 단축키 동작 확인.

---

### 단계 11 — 이미지 오프셋 십자선

**목표:** 미리보기에서 클릭한 지점 = 매칭 후 클릭될 위치를 십자선/점으로 표시.

**구현 포인트**

- 기존 offset marker를 십자선으로 강화.
- **미리보기 표시 좌표 ↔ 실제 offset_x/y(원본 이미지 픽셀)** 스케일 변환이 맞는지 확인. (구 DPG는 img_size 대비 스케일 사용)
- if 노드는 오프셋 UI 없음 유지 가능.

**관련 파일:** `GenericNode.jsx`, CSS, 필요 시 `img_size`를 캡처 완료 시 config에 저장

**DoD:** 미리보기 모서리/중앙 클릭 시 마커가 그 위치에 오고, 실행 시 같은 상대 지점 클릭.

**테스트**

1. 이미지 캡처 후 미리보기 좌상단·우하단 클릭 → 마커 위치 확인.
2. (가능하면) 짧은 매크로로 클릭 위치가 의도한지 확인.

---

### 단계 12 — 반복문 검증 · 안내

**목표:** “1회만 실행”이 연결 누락인지 숫자 버그인지 구분. UI로 올바른 연결을 안내.

**올바른 그래프**

```
시작 → 반복문 ──Loop──► [본문…] ──► 다시 반복문 In
              └─Exit──► (루프 이후)
```

**구현 포인트**

- 노드 힌트 문구: 「본문 끝을 이 노드 In에 다시 연결하세요」.
- 단계 2 이후 횟수 N 입력·실행 검증.
- 엔진: `LoopNode.execute`는 `current_count <= max_count`일 때 `loop_out_pin` (변경 최소화).

**관련 파일:** `GenericNode.jsx` (힌트), `action_nodes.py` (필요 시만)

**DoD:** 복귀 선 + 횟수 3일 때 본문이 3회 실행.

**테스트**

1. 시작 → 반복(3) → 대기(200ms) → (복귀) 반복 In, Exit는 비움.
2. Run 후 상태/로그로 3회 도는지 확인.
3. 복귀 선 없으면 1회만인 것도 문서/힌트와 일치하는지 확인.

---

### 단계 13–15 — 매크로 저장/로드 · Undo/Redo (3세션)

> 목표: Dear PyGui(`src/main.py`)의 저장·이미지 번들·undo 수준을 React 에디터에 이식하고, redo까지 보완한다.  
> 세션 프롬프트 예: `docs/editor-ux-roadmap.md 의 단계 13만 …`

#### 현황 (코드 기준) — 2026-07-17 단계 13–15 반영 후

| 구분 | React / FastAPI (현재) | Dear PyGui 참고 (`src/`) |
|------|------------------------|---------------------------|
| 저장 API | `POST /api/scripts/save` — `imgs/` 번들, 상대 `image_path`, `overwrite`/`exists` | `save_macro` — `images/` 폴더명만 다름 |
| 로드 | `POST /api/scripts/load` `{path}` — 상대경로 전체, 절대경로+`image_url` 복원 | `load_macro(rel_path)` 동일 개념 |
| 프론트 | Save/Load 모달, 덮어쓰기 확인, 응답으로 경로 동기화 | 모달 UI |
| 캡처 위치 | `assets/` 스크래치 → 저장 시 `imgs/`. **기동 시 assets 초기화** | 동일 |
| Undo | 구조 변경 스택 + Redo (Ctrl+Z/Y) | `history_stack` undo만 |

**이미지 번들: 가능·결정됨.**  
캡처는 `assets/`(스크래치) → 저장 시 사용 이미지만 `scripts/<입력이름>/imgs/`로 복사하고 노드 `image_path`를 상대경로로 갱신.

확정 디스크 레이아웃:

```
scripts/
  <입력한_이름>/
    <입력한_이름>.json
    imgs/
      capture_….png
assets/                    # 캡처 임시. 서버 재시작 시 비움
  capture_….png
```

JSON `config.image_path`: `imgs/capture_….png` (스크립트 폴더 상대).  
로드 시 `image_url` → `http://127.0.0.1:8000/static/scripts/<name>/imgs/<file>`.

---

#### 세션 A / 단계 13 — 저장: 이미지 번들 + 경로 갱신

**목표:** 저장 한 번에 JSON + 사용 이미지가 스크립트 폴더에 모이고, 노드 경로가 상대경로로 바뀐다.

**참고 구현:** `src/main.py` `save_macro` (대략 285–308행)

**구현 포인트**

- `backend/main.py` `save_script`:
  1. 입력 이름으로 `scripts/<name>/`, `scripts/<name>/imgs/` 생성
  2. `macro_data.nodes[].data.config.image_path` 수집 (`image` / `if`)
  3. 존재 시 `shutil.copy2` → `imgs/<basename>` (충돌 시 노드 id 접두 등)
  4. JSON에 `image_path = "imgs/<basename>"` 기록
  5. `image_url`은 저장본에서 제거(로드 시 재생성)
  6. 직렬화 시 제외: `onChange` 등 (프론트 sanitize)
- **같은 이름 폴더가 있으면** 덮어쓰기 확인 UI 후 진행(단계 14 UX와 맞춤, 저장 API는 `overwrite` 플래그 가능)
- 응답에 갱신된 `macro_data`를 돌려 프론트 메모리 경로 동기화
- `backend` 기동 시 `assets/` 내 캡처 파일 초기화 (DPG `clear_assets_folder` 참고)

**관련 파일:** `backend/main.py`, `frontend/src/NodeEditor.jsx` (`handleSave`), 필요 시 sanitize 유틸

**DoD**

- 저장 후 `scripts/<name>/<name>.json` + `scripts/<name>/imgs/*.png`
- JSON `image_path`가 `imgs/...` 상대경로
- 절대경로·localhost URL이 저장본 config에 없음

**테스트**

1. 이미지 캡처 → Save `test_bundle`
2. `scripts/test_bundle/test_bundle.json` + `imgs/` 확인
3. JSON의 `image_path`가 `imgs/...` 인지 확인
4. 서버 재시작 후 `assets/`가 비었는지 확인

---

#### 세션 B / 단계 14 — 로드: 경로·URL 복원 + UX

**목표:** 저장한 매크로를 열면 미리보기·실행이 바로 된다. 로드 경로 버그 수정.

**참고 구현:** `src/main.py` `load_macro` (대략 310–344행)

**구현 포인트**

- Load API: `scripts/` 아래 **상대 경로 전체** 허용  
  - 예: `macro_fgo/macro_fgo.json` (현재 프론트가 basename만 넘겨 실패하기 쉬움)
- 로드 시:
  - 상대 `image_path` → `abspath(script_dir, rel)` (실행용)
  - `image_url` → `/static/scripts/<name>/imgs/<file>` (+ 캐시버스터)
- 프론트: 목록 선택 UI + **같은 이름 저장 시 덮어쓰기 확인**, `onChange`/`configSchema` 재부착, `syncIdCounter`
- JSON 정본은 React `{nodes, edges}`만 (아래 확인사항 1번 설명 참고). 옛 DPG 파일은 로드 대상 아님(1차).

**관련 파일:** `backend/main.py`, `frontend/src/NodeEditor.jsx`

**DoD**

- 저장 → 새로고침 → Load → 미리보기 이미지 표시
- Run 시 이미지 매칭이 동일하게 동작
- `assets/` 없이도 `imgs/`만으로 로드·실행
- 기존 이름 저장 시 확인 없이 덮어쓰지 않음

**테스트**

1. 단계 13 산출물 Load
2. 미리보기·오프셋 마커 유지
3. `assets/` 비운 뒤에도 스크립트 `imgs/`만으로 로드·실행
4. 같은 이름으로 다시 Save → 확인 UI → 취소/확인 동작

---

#### 세션 C / 단계 15 — Undo / Redo

**목표:** 그래프 편집을 Ctrl+Z / Ctrl+Y(또는 Ctrl+Shift+Z)로 되돌리기·다시실행.

**참고 구현:** `src/main.py` `save_snapshot` / `undo` / `history_stack` (대략 93–151, Ctrl+Z). DPG는 undo만 있음 → React에서는 **redo 스택까지** 구현.

**구현 포인트**

- 스냅샷: `{ nodes, edges }` deep clone (structuredClone / JSON)
- 스택: `undoStack`, `redoStack`, `MAX_HISTORY` ≈ 30–50
- 스냅샷 시점 (**1차 = 구조 변경만**, 결정됨):
  - 노드/엣지 추가·삭제, 연결·연결 해제
  - 붙여넣기, 로드 직전
  - 1차에서 **제외**: 노드 드래그 중/종료, 필드 config 타이핑
- 적용 시 `onChange` 등 핸들러 재부착
- **충돌:** 키보드 녹화·입력 포커스 중 Ctrl+Z → 에디터 undo 무시

**관련 파일:** `frontend/src/NodeEditor.jsx` (또는 `history.js`), 단축키 핸들러

**DoD**

- 노드 삭제 → Ctrl+Z 복구, Ctrl+Y 재삭제
- 로드 전 상태가 undo로 복구 가능
- 입력 포커스 중 Ctrl+Z는 노드 삭제/undo 안 함
- 노드 위치만 옮긴 것은 1차 undo 대상 아님

**테스트**

1. 노드 2개 추가 → 연결 → Del → Ctrl+Z → 연결 복구
2. Ctrl+Y로 다시 삭제
3. 입력창 포커스에서 Ctrl+Z 시 그래프 불변

---

#### 확인사항 · 결정 내용

**1번이 무엇을 묻는지 (설명)**  
에디터에 그래프를 파일로 쓸 때 JSON **모양**이 두 종류 있다.

| | React 에디터 (현재) | 옛 Dear PyGui |
|--|---------------------|---------------|
| 노드 | `nodes[]` + `position` + `data.config` | `nodes[]` + `pos` + `data` |
| 연결 | `edges[]` (`source`/`target`/`handles`) | `links[]` (`from`/`to` 인덱스 + pin) |

같은 “매크로 파일”이라도 키가 달라 **서로 그대로 Load하면 깨진다**.  
“1번”은: **앞으로 저장/로드 정본을 React 포맷만 쓸지**, 옛 DPG `scripts/macro_*`도 변환해 열지 묻는 것이었다.

→ **결정: React `{nodes, edges}`만 정본.** 기존 DPG JSON은 1차 로드 대상 아님.

| # | 항목 | 결정 |
|---|------|------|
| 1 | JSON 포맷 | React `{nodes, edges}`만. DPG 포맷 미지원(1차) |
| 2 | `assets/` | **서버 재시작 시 초기화** (캡처 스크래치만 유지 목적) |
| 3 | Undo 1차 범위 | **구조 변경만** (추가/삭제/연결/복붙/로드). 드래그·config는 이후 |
| 4 | 같은 이름 저장 | **덮어쓰기 확인 UI** |
| — | 이미지 폴더명 | `scripts/<name>/imgs/` (사용자 지정; DPG의 `images/`와 다름) |
| — | 단계 12 반복문 | 사용자가 나중에 검증. 에이전트는 13–15 우선 |

---

## 4. 진행 상태

| 단계 | 상태 | 담당/세션 | 메모 |
|------|------|-----------|------|
| 1 nodrag | done | 2026-07-17 | `.node-body` + 입력/버튼/미리보기에 `nodrag`/`nowheel`. 헤더는 드래그 유지 |
| 2 숫자 입력 | done | 2026-07-17 | draft 문자열 + blur/Enter 커밋. 빈 칸은 default/0 |
| 3 핸들 확대 | done | 2026-07-17 | 핸들 14px + `::before` 히트영역, `connectionRadius={36}` |
| 4 핀 라벨 | done | 2026-07-17 | Out / True·False / Loop·Exit. if·loop는 공통 output_pin 숨김 |
| 5 노드 삭제 | done | 2026-07-17 | Del/Backspace + 우클릭 삭제. 입력 포커스 시 RF 기본 무시 |
| 6 엣지 삭제 | done | 2026-07-17 | 선/핸들 우클릭「연결 해제」, 선택+Del. interactionWidth 40 |
| 7 다중 선택 | done | 2026-07-17 | 좌클릭 박스 선택, Shift 추가선택, 중버튼 팬, 휠 확대/축소 |
| 8 복붙 | done | 2026-07-17 | Ctrl+C/V + 메뉴. 새 id, 붙여넣기=뷰포트 중앙 |
| 9 좌표 F8 | done | 2026-07-17 | CLI·UI F8 확정/Esc 취소. 클릭 확정 제거. 취소 시 poll/WS 반영 |
| 10 키보드 녹화 | done | 2026-07-17 | 드롭 시 schema default로 mode 동기화. 버튼 토글 대기/확정. Ctrl+Z 조합 |
| 11 오프셋 십자선 | done | 2026-07-17 | object-fit contain 스케일, 십자선+점, img_size 저장. if는 오프셋 UI 없음 |
| 12 반복문 | pending | 사용자 | 에이전트 보류 — 사용자 검증 예정 |
| 13 저장·이미지 번들 | done | 2026-07-17 | `scripts/<name>/` + `imgs/` 번들, 상대 `image_path`, assets 기동 시 초기화, 덮어쓰기 `exists` |
| 14 로드·URL 복원 | done | 2026-07-17 | 상대경로 로드 API, 절대경로+`image_url` 복원, 목록 모달, 덮어쓰기 확인 UI |
| 15 Undo/Redo | done | 2026-07-17 | 구조 변경만 스냅샷. Ctrl+Z / Ctrl+Y(또는 Ctrl+Shift+Z). 입력 포커스 시 무시 |

상태 값: `pending` | `in_progress` | `done` | `blocked`

---

## 5. 열린 이슈

- 2026-07-17: if/loop에서 공통 `output_pin`을 숨김. 예전 저장 매크로가 `output_pin`으로 연결돼 있으면 재연결 필요 / 관련 단계 4
- 2026-07-17: 좌클릭 드래그=박스 선택 → 빈 캔버스 팬은 중버튼. 휠=확대/축소. 우클릭=컨텍스트 메뉴 / 관련 단계 7
- 2026-07-17: 좌표 녹화는 클릭 또는 F8로 확정 / 관련 단계 9
- 2026-07-17: 오프셋 미리보기는 이미지 width:100% + % 마커(letterbox 제거). 옛 contain 기준 offset은 다시 찍을 것 / 관련 단계 11
- 2026-07-17: 문자열 모드 한글 타자 입력은 두벌식 키열+IME 프로브 / 관련 키보드
- 2026-07-17: 옛 DPG `scripts/macro_*`(`links`/`pos`/`images/`)는 로드 거부. React로 다시 저장 필요 / 관련 단계 14
- 2026-07-17: Undo 1차는 구조만 — 노드 드래그·config 타이핑은 Ctrl+Z로 안 돌아감(이후 확장) / 관련 단계 15
- 2026-07-17: 단계 12 반복문 검증은 사용자 보류 / 관련 단계 12

예시 형식:

```
- YYYY-MM-DD: 증상 / 재현 / 임시 회피 / 관련 단계
```

---

## 6. 변경 이력

| 날짜 | 요약 | 파일 |
|------|------|------|
| 2026-07-17 | 단계 13–15: 저장 imgs 번들·assets 초기화, 로드 경로/URL·덮어쓰기 모달, Undo/Redo(구조만) | `backend/main.py`, `frontend/src/NodeEditor.jsx`, `frontend/src/index.css`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 13–15 결정 반영: imgs/ 레이아웃, assets 재시작 초기화, undo 구조만, 덮어쓰기 UI, 12 사용자 보류 | `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 단계 13–15 로드맵 추가: 저장 이미지 번들·로드·Undo/Redo 3세션, DPG 참고·확인사항 | `docs/editor-ux-roadmap.md`, `docs/README.md` |
| 2026-07-17 | 오프셋 마커 정렬 수정, 좌표 클릭 확정 복구, 한글 문자열 클립보드 입력 | `coordinate_picker_cli.py`, `action_nodes.py`, `GenericNode.jsx`, `index.css`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 단계 9–11: F8 좌표 확정, 키보드 녹화 토글·조합·초기 mode, 오프셋 십자선·스케일 | `backend/engine/coordinate_picker_cli.py`, `capture.py`, `state.py`, `backend/main.py`, `backend/nodes/action_nodes.py`, `frontend/src/GenericNode.jsx`, `NodeEditor.jsx`, `index.css`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 휠 `panOnScroll` 제거 → 확대/축소 복원. 단계 7 메모·열린 이슈 정리 | `frontend/src/NodeEditor.jsx`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 단계 6·8 보완: 핸들/엣지 우클릭 연결 해제, 붙여넣기 뷰포트 중앙, 우클릭 팬 제거 | `frontend/src/NodeEditor.jsx`, `frontend/src/index.css`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 단계 5–8: 노드/엣지 삭제·컨텍스트 메뉴, 박스/Shift 다중선택, Ctrl+C/V 복붙 | `frontend/src/NodeEditor.jsx`, `frontend/src/index.css`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 단계 2–4: 숫자 draft 커밋, 핸들 확대·connectionRadius, Out/True·False/Loop·Exit 라벨 | `frontend/src/GenericNode.jsx`, `frontend/src/NodeEditor.jsx`, `frontend/src/index.css`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 단계 1: 노드 본문·입력·버튼·이미지 미리보기에 `nodrag`/`nowheel` 적용 (헤더 드래그 유지) | `frontend/src/GenericNode.jsx`, `docs/editor-ux-roadmap.md` |
| 2026-07-17 | 로드맵·인수인계 문서 최초 작성 | `docs/editor-ux-roadmap.md`, `docs/README.md` |

---

## 7. 참고: 의도적으로 하지 않는 것

- Dear PyGui(`src/`)로 에디터를 되돌리는 것 — 브라우저 에디터 유지.
- 반복문을 “복귀 선 없이” 자동 루프하도록 엔진을 크게 바꾸는 것 (명시적 그래프 유지).
