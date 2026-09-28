import ctypes
import os
import time
import tkinter as tk
from PIL import ImageGrab, ImageTk


def _enable_dpi_awareness():
    """Windows DPI 스케일링과 실제 픽셀 좌표를 맞춤."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _virtual_screen_rect():
    """모든 모니터를 포함한 가상 화면 (left, top, width, height)."""
    _enable_dpi_awareness()
    user32 = ctypes.windll.user32
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    return left, top, width, height


def _grab_all_screens():
    _enable_dpi_awareness()
    try:
        return ImageGrab.grab(all_screens=True)
    except TypeError:
        return ImageGrab.grab()


class BasePicker:
    """멀티모니터 가상 화면 전체를 덮는 고정 오버레이."""

    def __init__(self, callback, delay=0):
        if delay > 0:
            print(f"{delay}초 후 화면을 고정합니다. 준비하세요...")
            time.sleep(delay)

        self.callback = callback
        self.vx, self.vy, self.vw, self.vh = _virtual_screen_rect()
        self.full_screen_img = _grab_all_screens()

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{self.vw}x{self.vh}+{self.vx}+{self.vy}")
        self.root.config(cursor="cross")

        # 캡처 이미지가 가상 화면보다 크거나 작을 수 있어 리사이즈
        img = self.full_screen_img
        if img.size != (self.vw, self.vh):
            img = img.resize((self.vw, self.vh))
            self.full_screen_img = img

        self.bg_image = ImageTk.PhotoImage(self.full_screen_img)
        self.canvas = tk.Canvas(self.root, cursor="cross", highlightthickness=0, width=self.vw, height=self.vh)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")
        self.canvas.create_rectangle(0, 0, self.vw, self.vh, fill="grey", stipple="gray25")

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.focus_force()
        self.root.lift()

    def on_button_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, 1, 1, outline="red", width=2
        )

    def on_move_press(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def get_coords(self, event):
        end_x, end_y = event.x, event.y
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        right = max(self.start_x, end_x)
        bottom = max(self.start_y, end_y)
        return left, top, right, bottom

    def to_screen_bbox(self, left, top, right, bottom):
        """캔버스 로컬 좌표 → OS 화면 좌표."""
        return (
            left + self.vx,
            top + self.vy,
            right + self.vx,
            bottom + self.vy,
        )

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
            img = self.full_screen_img.crop((left, top, right, bottom))
            if not os.path.exists("assets"):
                os.makedirs("assets")
            filename = os.path.abspath(f"assets/capture_{int(time.time())}.png")
            img.save(filename)
            if self.callback:
                self.callback(filename)
        except Exception as e:
            print(f"캡처 오류: {e}")


class RegionPicker(BasePicker):
    """드래그한 영역의 좌표 (x, y, w, h)를 OS 화면 좌표로 반환"""

    def on_button_release(self, event):
        left, top, right, bottom = self.get_coords(event)
        self.root.destroy()

        width, height = right - left, bottom - top
        if width < 5 or height < 5:
            return

        sx1, sy1, sx2, sy2 = self.to_screen_bbox(left, top, right, bottom)
        if self.callback:
            self.callback(sx1, sy1, sx2 - sx1, sy2 - sy1)


def start_capture_tool(callback, delay=0):
    ImagePicker(callback, delay).run()


def start_region_tool(callback, delay=0):
    RegionPicker(callback, delay).run()


def start_coordinate_tool(callback, on_cancel=None):
    """
    pynput 전역 훅으로 OS 화면 좌표를 잡습니다.
    클릭 또는 F8 = 현재 커서 좌표 확정, Esc = 취소.
    uvicorn 스레드 훅 문제를 피하기 위해 독립 프로세스로 실행합니다.
    """
    import json
    import subprocess
    import sys

    _enable_dpi_awareness()

    script = os.path.join(os.path.dirname(__file__), "coordinate_picker_cli.py")
    print("좌표 선택 프로세스 시작 (클릭 또는 F8 확정 / Esc 취소)")

    creationflags = 0
    if sys.platform == "win32":
        # 콘솔 창 없이 실행하되, 훅은 정상 동작
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )

    result_line = None
    try:
        # READY + 결과 JSON
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            if line == "READY":
                print("좌표 선택 준비 완료: 클릭 또는 F8 확정 / Esc 취소")
                continue
            result_line = line
            break
    finally:
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()

    stderr = ""
    try:
        stderr = proc.stderr.read() or ""
    except Exception:
        pass
    if stderr.strip():
        print(f"[coordinate_picker stderr] {stderr.strip()}")

    if not result_line:
        print("좌표 선택 실패: 결과 없음")
        if on_cancel:
            on_cancel()
        return

    try:
        payload = json.loads(result_line)
    except json.JSONDecodeError:
        print(f"좌표 선택 실패: JSON 파싱 오류 ({result_line})")
        if on_cancel:
            on_cancel()
        return

    if payload.get("cancelled"):
        print("좌표 선택 취소됨")
        if on_cancel:
            on_cancel()
        return

    x, y = payload.get("x"), payload.get("y")
    if x is None or y is None:
        print(f"좌표 선택 실패: 잘못된 결과 {payload}")
        if on_cancel:
            on_cancel()
        return

    print(f"좌표 선택됨: ({x}, {y})")
    if callback:
        callback(int(x), int(y))
