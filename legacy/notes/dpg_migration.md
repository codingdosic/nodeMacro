# DPG 업그레이드 및 마이그레이션 가이드 (v2.2 -> Latest)

## 1. 현재 환경 (v2.2)
- **주요 사용 모듈:** `dearpygui.dearpygui`
- **핵심 기능:** 
    - `node_editor`를 통한 비주얼 프로그래밍 환경.
    - `handler_registry`를 통한 전역 키보드/마우스 이벤트 감지.
    - `drawlist`를 이용한 이미지 미리보기 및 십자선 표시.
    - `texture_registry`를 통한 동적 이미지 로딩.

## 2. 주요 DPG API 사용 목록 (추적 대상)

### A. 노드 에디터 관련
- `dpg.node_editor()`: 메인 에디터 생성.
- `dpg.node()`: 개별 노드 생성.
- `dpg.node_attribute()`: 입력/출력/정적 핀 생성.
- `dpg.add_node_link(p1, p2)`: 노드 연결.
- `dpg.get_selected_nodes()`: 선택된 노드 ID 리스트 반환.
- `dpg.fit_node_editor_view()`: (v2.2에서 누락 확인됨, 최신 버전 확인 필요)

### B. 위젯 및 데이터
- `dpg.add_input_xxx()`: 텍스트, 숫자 입력.
- `dpg.get_value()`, `dpg.set_value()`: 위젯 데이터 접근.
- `dpg.configure_item()`: 아이템 속성(show, enabled 등) 변경.
- `dpg.delete_item()`: 아이템 삭제.

### C. 이벤트 핸들러
- `dpg.handler_registry()`: 전역 핸들러 컨테이너.
- `dpg.add_key_press_handler()`: 키보드 입력 감지.
- `dpg.add_mouse_wheel_handler()`: 마우스 휠 감지.

## 3. 예상되는 변경 사항 및 오류 상황
- **함수명 변경:** `fit_node_editor_view`가 `zoom_to_fit` 등으로 바뀌었을 가능성.
- **파라미터 변경:** `add_node_link` 등의 인자 순서나 필수 인자 변경.
- **상수 이름:** `mvKey_LControl` 등 키 상수가 `Key_LControl` 등으로 간소화되었을 수 있음.

## 4. 복구 계획 (Rollback Plan)
만약 업그레이드 후 해결 불가능한 치명적 오류 발생 시 다음 명령어로 복구:
```powershell
pip install dearpygui==2.2
```

---
## 🚀 업그레이드 준비 완료
- [x] 현재 코드 사용 현황 전수 조사
- [x] 마이그레이션 문서 작성
- [ ] 라이브러리 업데이트 (`pip install --upgrade dearpygui`)
- [ ] 실행 테스트 및 에러 수정
