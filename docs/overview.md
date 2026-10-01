# 프로젝트 개요: 노드 기반 시각적 매크로 프로그램

## 1. 개요
사용자가 '스크래치(Scratch)'와 같이 블록(노드)을 연결하여 복잡한 자동화 워크플로우를 직관적으로 설계할 수 있는 Python 기반의 매크로 프로그램입니다. 좌표 기반 클릭뿐만 아니라 이미지 인식 기술을 도입하여, 화면상의 특정 객체를 추적하고 상호작용할 수 있도록 설계되었습니다.

## 2. 주요 기술 스택 (Tech Stack)
- **언어:** Python 3.x
- **GUI 프레임워크:** [Dear PyGui](https://github.com/hoffstadt/DearPyGui) (GPU 가속 지원 및 내장 노드 에디터 활용)
- **자동화 로직:** [PyAutoGUI](https://github.com/asweigart/pyautogui) (마우스/키보드 제어), [pynput](https://github.com/moses-palmer/pynput) (전역 이벤트 리스너)
- **이미지 처리:** [OpenCV](https://opencv.org/) (템플릿 매칭), [Pillow](https://python-pillow.org/) (화면 캡처)

## 3. 핵심 아키텍처
- **노드 시스템 (Node System):** `BaseNode` 추상 클래스를 상속받아 개별 동작(시작, 클릭, 대기, 이미지 클릭)을 모듈화.
- **실행 엔진 (Execution Engine):** 노드 간의 그래프 연결(Link) 정보를 해석하여 순차적(또는 조건부)으로 실행하는 스레드 기반 엔진.
- **상태 관리 (State Management):** 순환 참조를 방지하고 UI와 로직 간의 데이터 통신을 위한 중앙 집중식 상태 관리 모듈.
