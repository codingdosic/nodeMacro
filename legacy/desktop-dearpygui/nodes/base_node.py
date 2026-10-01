import dearpygui.dearpygui as dpg

class BaseNode:
    node_type = "unknown" # 클래스 레벨에서 정의 (시리얼라이제이션용)

    def __init__(self, label, pos=(10, 10)):
        self.label = label
        self.pos = pos
        self.node_id = None
        self.input_pin = None
        self.output_pin = None
        self.width = 150 # 모든 노드의 기본 너비 고정
        self.tag_id = id(self) # 고유 태그 생성을 위한 ID

    def get_tag(self, suffix):
        """노드별 고유한 위젯 태그 생성"""
        return f"{suffix}_{self.tag_id}"

    def create_ui(self, parent):
        with dpg.node(label=self.label, parent=parent, pos=self.pos) as self.node_id:
            # 입력 핀
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input) as self.input_pin:
                dpg.add_text("In")
            
            # 노드별 커스텀 위젯 (고정 너비 그룹 적용)
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                with dpg.group(width=self.width):
                    self._add_widgets()
            
            # 출력 핀
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as self.output_pin:
                with dpg.group(width=self.width): # 출력 핀 레이아웃 고정
                    dpg.add_text("Out", indent=self.width - 30)

        # [방어 3] 노드 생성 즉시 한글 폰트 강제 바인딩 (입력 필드 깨짐 방지)
        try:
            dpg.bind_item_font(self.node_id, "korean_font")
        except:
            pass

    def _add_widgets(self):
        pass

    def execute(self):
        # 실행 후 다음에 따라갈 출력 핀 ID를 반환함
        return self.output_pin

    def reset(self):
        # 실행 전 내부 상태(카운터 등) 초기화
        pass

    def get_config(self):
        # 모든 노드에 공통적으로 필요한 데이터 반환
        return {
            "pos": dpg.get_item_pos(self.node_id),
            "data": {}
        }

    def apply_config(self, data):
        # 자식 클래스에서 위젯 값 설정을 오버라이드함
        pass
