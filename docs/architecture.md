# 시스템 아키텍처 (System Architecture)

본 문서는 **NodeMacro Engine**의 내부 구조와 컴포넌트 간의 상호작용을 Mermaid 다이어그램으로 설명합니다.

## 1. 전체 구조도 (High-Level Overview)

```mermaid
graph TD
    subgraph "UI Layer (Dear PyGui)"
        Main["main.py (App Entry)"]
        Editor["Node Editor"]
        Picker["Coordinate/Key Picker"]
    end

    subgraph "Node System"
        Registry["NODE_MAP (Registry)"]
        Base["BaseNode (Abstract)"]
        BaseImg["BaseImageNode"]
        Nodes["Action Nodes (Mouse, Keyboard, Loop, etc.)"]
    end

    subgraph "Engine Layer"
        Exec["Executor (Multi-threaded)"]
        State["State Manager (Global)"]
    end

    subgraph "External Resources"
        JSON["scripts/*.json"]
        Assets["assets/*.png"]
    end

    subgraph "Hardware Interaction"
        HW["Mouse / Keyboard / Screen"]
    end

    %% 관계 정의
    Main --> Editor
    Main --> Registry
    Registry --> Nodes
    Nodes -- Inherits --> Base
    BaseImg -- Inherits --> Base
    Nodes -- Inherits --> BaseImg

    Main -- Save/Load --> JSON
    Nodes -- Capture --> Assets
    
    Editor -- Trigger --> Exec
    Exec -- Traverse --> Nodes
    Nodes -- Get/Set --> State
    Nodes -- Control --> HW
    Exec -- Stop (ESC) --> HW
```

---

## 2. 노드 클래스 계층 구조 (Class Hierarchy)

```mermaid
classDiagram
    class BaseNode {
        <<Abstract>>
        +String node_type
        +Int tag_id
        +create_ui(parent)
        +execute()*
        +get_config()
        +apply_config(data)
    }

    class BaseImageNode {
        <<Abstract>>
        +String image_path
        +Int offset_x, offset_y
        +_find_image()
        +_capture_image()
    }

    class ImageNode { +execute() }
    class IfNode { +execute() }
    class MouseClickNode { +execute() }
    class KeyboardNode { +execute() }
    class LoopNode { +execute() }

    BaseNode <|-- BaseImageNode
    BaseNode <|-- MouseClickNode
    BaseNode <|-- KeyboardNode
    BaseNode <|-- LoopNode
    BaseImageNode <|-- ImageNode
    BaseImageNode <|-- IfNode
```

---

## 3. 실행 흐름 (Execution Flow)

```mermaid
sequenceDiagram
    participant User
    participant UI as main.py
    participant Exec as Executor
    participant Node as ActionNode
    participant OS as OS / HW

    User->>UI: [RUN] 버튼 클릭
    UI->>Exec: start(start_node, links)
    loop 매크로 실행 루프
        Exec->>Node: execute()
        Node->>OS: 이미지 스캔 / 마우스 제어
        OS-->>Node: 결과 반환 (좌표 등)
        Node-->>Exec: 다음 노드 핀 ID 반환
    end
    User->>OS: [ESC] 키 입력
    OS->>Exec: stop() 시그널
    Exec-->>UI: 실행 중단 및 로그 출력
```

---

## 💡 기술적 특징 설명

1.  **Registry Pattern**: `NODE_MAP`을 사용하여 노드 타입을 중앙 관리함으로써, `main.py`의 수정 없이도 새로운 노드를 손쉽게 확장할 수 있습니다.
2.  **Multi-Threading**: 매크로 로직이 별도의 스레드에서 동작하므로, 이미지 검색이나 긴 대기 시간 중에도 UI가 응답 불능 상태에 빠지지 않습니다.
3.  **Coordinate Transformation**: 앵커 노드를 기준으로 하는 좌표 역산 알고리즘을 통해 에디터의 줌/패닝 상태와 관계없이 정확한 위치에 노드를 배치합니다.
