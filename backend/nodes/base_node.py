class BaseNode:
    node_type = "unknown"
    node_label = "Unknown"

    def __init__(self, node_id, config=None):
        self.node_id = node_id
        self.config = config or {}
        self.label = self.node_label

    def execute(self):
        """
        실행 로직.
        기본적으로 다음으로 실행할 출력 핀(핸들)의 이름을 반환합니다.
        분기가 없는 노드는 기본적으로 "output_pin"을 반환합니다.
        """
        return "output_pin"

    def reset(self):
        """실행 전 내부 상태 초기화"""
        pass

    def get_schema(self):
        """프론트엔드에 전달할 노드 설정 UI 스키마"""
        return {}
