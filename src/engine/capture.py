import tkinter as tk
from PIL import ImageGrab, ImageTk
import os
import time

class BasePicker:
    """공통적인 화면 오버레이 및 드래그 로직을 담당하는 베이스 클래스"""
    def __init__(self, callback, delay=0):
        if delay > 0:
            print(f"{delay}초 후 화면을 고정합니다. 준비하세요...")
            time.sleep(delay)

        self.callback = callback
        # 전체 화면 스캔 (Freeze Screen)
        self.full_screen_img = ImageGrab.grab()
        
        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.config(cursor="cross")
        
        # 전체 화면 이미지를 Tkinter에서 사용할 수 있게 변환
        self.bg_image = ImageTk.PhotoImage(self.full_screen_img)
        
        self.canvas = tk.Canvas(self.root, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # 배경으로 전체 화면 이미지 배치
        self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")
        
        # 반투명 어두운 효과 (선택 영역을 강조하기 위해)
        self.overlay = self.canvas.create_rectangle(0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight(), fill="grey", stipple="gray25")

        self.start_x = None
        self.start_y = None
        self.rect = None
        
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def on_button_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='red', width=2)

    def on_move_press(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def get_coords(self, event):
        end_x, end_y = event.x, event.y
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        right = max(self.start_x, end_x)
        bottom = max(self.start_y, end_y)
        return left, top, right, bottom

    def run(self):
        self.root.mainloop()

class ImagePicker(BasePicker):
    """이미지를 캡처하고 파일 경로를 반환"""
    def on_button_release(self, event):
        left, top, right, bottom = self.get_coords(event)
        self.root.destroy()
        
        if right - left < 5 or bottom - top < 5:
            return
            
        try:
            # 미리 찍어둔 전체 화면 이미지에서 해당 영역만 Crop (가장 빠르고 정확함)
            img = self.full_screen_img.crop((left, top, right, bottom))
            
            if not os.path.exists("assets"):
                os.makedirs("assets")
            filename = os.path.abspath(f"assets/capture_{int(time.time())}.png")
            img.save(filename)
            if self.callback: self.callback(filename)
        except Exception as e: print(f"캡처 오류: {e}")

class RegionPicker(BasePicker):
    """드래그한 영역의 좌표 (x, y, w, h)를 반환"""
    def on_button_release(self, event):
        left, top, right, bottom = self.get_coords(event)
        self.root.destroy()
        
        width, height = right - left, bottom - top
        if width < 5 or height < 5:
            return
            
        if self.callback:
            self.callback(left, top, width, height)

def start_capture_tool(callback, delay=0):
    ImagePicker(callback, delay).run()

def start_region_tool(callback, delay=0):
    RegionPicker(callback, delay).run()
