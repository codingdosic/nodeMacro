# 프로젝트 심층 리서치 (Research Report)

본 문서는 포트폴리오 기재를 위해 프로젝트의 아키텍처, 핵심 기술 스택, 구현 세부 사항 및 기술적 도전 과제를 분석한 리서치 보고서입니다.

## 1. 프로젝트 개요
- **명칭**: Node-Based Visual Macro Engine (MVP)
- **목적**: 코딩 지식 없이도 노드 연결을 통해 복잡한 자동화 로직을 구성할 수 있는 범용 매크로 제작 도구.
- **핵심 가치**: 직관적인 시각적 프로그래밍, 이미지 인식 기반의 동적 대응, 높은 확장성.

## 2. 기술 스택 (Tech Stack)
- **Language**: Python 3.x
- **GUI Framework**: 
    - `DearPyGui`: 메인 노드 에디터 및 UI 구성 (GPU 가속 기반의 빠른 렌더링).
    - `Tkinter`: 화면 캡처 및 영역 선택을 위한 투명 오버레이 도구.
- **Automation & CV**:
    - `PyAutoGUI`: 마우스/키보드 제어 및 이미지 템플릿 매칭.
    - `OpenCV`: 이미지 인식 엔진 (PyAutoGUI 내부 활용).
    - `Pillow (PIL)`: 화면 캡처 및 이미지 프로세싱.
- **Input Handling**:
    - `pynput`: 전역 키보드/마우스 리스너 (비상 정지 및 좌표 픽커 구현).

## 3. 핵심 아키텍처 및 디자인 패턴

### 3.1 노드 시스템 (Node-Base Architecture)
- **BaseNode**: 모든 노드의 추상 기초 클래스. UI 생성, 데이터 직렬화(get_config), 실행 인터페이스(execute) 정의.
- **Modular Action Nodes**:
    - **입력**: `ImageNode` (이미지 인식), `CoordNode` (좌표 지정).
    - **동작**: `MouseClickNode`, `KeyboardNode`, `MouseMoveNode` 등.
    - **제어**: `IfNode` (이미지 존재 여부 분기), `LoopNode` (횟수 반복).
- **Graph Execution**: `Executor`가 `StartNode`부터 연결된 링크를 따라 순차/분기 실행하는 스레드 기반 엔진.

### 3.2 상태 관리 및 복구 (State & Undo)
- **Snapshot-based Undo**: 에디터 상태가 변경될 때마다 전체 노드 및 링크 정보를 직렬화하여 `history_stack`에 저장. `Ctrl+Z` 시 UI를 재건축하는 방식.
- **Global Macro State**: 실행 중 노드 간 공유 데이터(예: 이미지로 찾은 좌표)를 `macro_state` 딕셔너리에 관리하여 파이프라인 형성.

### 3.3 화면 캡처 워크플로우 (Frozen Screen Capture)
- `capture.py`: 캡처 시 현재 화면을 즉시 `ImageGrab`하여 고정된 이미지를 `Tkinter` 풀스크린 캔버스에 띄움. 사용자는 움직이는 화면에 방해받지 않고 정밀하게 대상 영역을 크롭 가능.

## 4. 주요 기술적 특징 및 구현 세부 사항

### 4.1 동적 좌표 오프셋 (Click Offset)
- `BaseImageNode`에서 이미지를 찾은 후, 해당 이미지의 정중앙이 아닌 사용자가 지정한 상대적 위치를 클릭할 수 있도록 **Crosshair 기반 오프셋 설정** 기능 구현.

### 4.2 비상 정지 및 안전 장치
- `Executor` 내부에 `pynput` 리스너를 별도 스레드로 운용하여, 매크로 실행 중 언제든지 `ESC` 키로 즉시 중단할 수 있는 Safety-First 설계.

### 4.3 데이터 직렬화 및 자산 관리
- 매크로 저장 시 `.json` 파일과 사용된 이미지 자산(`images/`)을 패키징하여 관리. 경로 문제를 해결하기 위해 상대 경로 전환 로직 포함.

## 5. 기술적 도전 및 해결 방안 (Troubleshooting)

| 문제점 | 해결 방안 |
| :--- | :--- |
| **DearPyGui 한글 깨짐** | `malgun.ttf` 폰트 레지스트리 등록 및 전역 폰트 바인딩 처리를 통해 해결. |
| **순환 참조 및 경로 문제** | `sys.path` 수동 설정 및 `frozen` 환경(PyInstaller) 고려한 경로 로직 구축. |
| **실행 중 GUI 프리징** | 매크로 실행 로직을 별도 `threading.Thread`로 분리하고 `time.sleep`을 통한 CPU 점유율 최적화. |
| **동적인 노드 UI 갱신** | `item_handler_registry`를 활용하여 노드별 우클릭 컨텍스트 메뉴 및 실시간 프리뷰 갱신 구현. |

## 6. 포트폴리오 활용 포인트
1.  **객체 지향 설계**: `BaseNode` 상속 구조를 통한 확장성 있는 노드 시스템 설계 강조.
2.  **멀티스레딩**: GUI 스레드와 실행 엔진 스레드 간의 동기화 및 자원 공유 경험.
3.  **컴퓨터 비전 활용**: 단순 좌표 매크로를 넘어 템플릿 매칭을 통한 지능형 자동화 구현.
4.  **도구 제작 능력**: 사용자 편의를 위한 캡처 도구, Undo 시스템 등 완성도 있는 유틸리티 개발 역량.
