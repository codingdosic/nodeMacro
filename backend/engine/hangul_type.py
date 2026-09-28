"""
한글 문자열 → 두벌식 영문 키열 변환 및 IME 모드 맞춤 타이핑.

IME API(Imm/WM_IME_CONTROL)는 환경에 따라 한글/영문을 구별하지 못하는 경우가 있어,
시작 시 'a' 프로브로 실제 모드를 확인한 뒤 한영키 토글만으로 상태를 추적한다.
"""
from __future__ import annotations

import ctypes
import time
from typing import List, Optional, Tuple

import pyautogui

# 초성 / 중성 / 종성 → 두벌식 키
_CHOSEONG = [
    "r", "R", "s", "e", "E", "f", "a", "q", "Q", "t", "T", "d", "w", "W", "c", "z", "x", "v", "g",
]
_JUNGSEONG = [
    "k", "o", "i", "O", "j", "p", "u", "P", "h", "hk", "ho", "hl", "y", "n", "nj", "np", "nl", "b", "m", "ml", "l",
]
_JONGSEONG = [
    "", "r", "R", "rt", "s", "sw", "sg", "e", "f", "fr", "fa", "fq", "ft", "fx", "fv", "fg",
    "a", "q", "qt", "t", "T", "d", "w", "c", "z", "x", "v", "g",
]

_COMPAT_JAMO = {
    "ㄱ": "r", "ㄲ": "R", "ㄳ": "rt", "ㄴ": "s", "ㄵ": "sw", "ㄶ": "sg", "ㄷ": "e", "ㄸ": "E",
    "ㄹ": "f", "ㄺ": "fr", "ㄻ": "fa", "ㄼ": "fq", "ㄽ": "ft", "ㄾ": "fx", "ㄿ": "fv", "ㅀ": "fg",
    "ㅁ": "a", "ㅂ": "q", "ㅃ": "Q", "ㅄ": "qt", "ㅅ": "t", "ㅆ": "T", "ㅇ": "d", "ㅈ": "w",
    "ㅉ": "W", "ㅊ": "c", "ㅋ": "z", "ㅌ": "x", "ㅍ": "v", "ㅎ": "g",
    "ㅏ": "k", "ㅐ": "o", "ㅑ": "i", "ㅒ": "O", "ㅓ": "j", "ㅔ": "p", "ㅕ": "u", "ㅖ": "P",
    "ㅗ": "h", "ㅘ": "hk", "ㅙ": "ho", "ㅚ": "hl", "ㅛ": "y", "ㅜ": "n", "ㅝ": "nj", "ㅞ": "np",
    "ㅟ": "nl", "ㅠ": "b", "ㅡ": "m", "ㅢ": "ml", "ㅣ": "l",
}

VK_HANGUL = 0x15
KEYEVENTF_KEYUP = 0x0002


def hangul_char_to_keys(ch: str) -> str:
    if ch in _COMPAT_JAMO:
        return _COMPAT_JAMO[ch]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        base = code - 0xAC00
        cho = base // (21 * 28)
        jung = (base % (21 * 28)) // 28
        jong = base % 28
        return _CHOSEONG[cho] + _JUNGSEONG[jung] + _JONGSEONG[jong]
    return ""


def is_hangul_char(ch: str) -> bool:
    o = ord(ch)
    return (
        0xAC00 <= o <= 0xD7A3
        or 0x3131 <= o <= 0x318E
        or 0x1100 <= o <= 0x11FF
    )


def is_latin_letter(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


Segment = Tuple[str, str]


def split_script_segments(text: str) -> List[Segment]:
    if not text:
        return []

    segments: List[Segment] = []
    buf: List[str] = []
    kind: Optional[str] = None

    def flush():
        nonlocal buf, kind
        if buf and kind:
            segments.append((kind, "".join(buf)))
        buf = []
        kind = None

    for ch in text:
        if is_hangul_char(ch):
            next_kind = "hangul"
        elif is_latin_letter(ch):
            next_kind = "latin"
        else:
            next_kind = "raw"

        if kind is None:
            kind = next_kind
            buf.append(ch)
        elif next_kind == kind:
            buf.append(ch)
        elif next_kind == "raw":
            buf.append(ch)
        elif kind == "raw":
            flush()
            kind = next_kind
            buf.append(ch)
        else:
            flush()
            kind = next_kind
            buf.append(ch)

    flush()
    return segments


def hangul_text_to_keys(text: str) -> str:
    keys = []
    for ch in text:
        if is_hangul_char(ch):
            mapped = hangul_char_to_keys(ch)
            if mapped:
                keys.append(mapped)
        else:
            keys.append(ch)
    return "".join(keys)


def _get_clipboard_text() -> Optional[str]:
    """클립보드 유니코드 텍스트 읽기 (64-bit restype 주의)."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13

    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.CloseClipboard.restype = ctypes.c_bool
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def press_hangul_key():
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_HANGUL, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_HANGUL, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)


def probe_hangul_mode() -> Optional[bool]:
    """
    'a'를 한 글자 입력해 결과로 한글 모드인지 판별한 뒤 지운다.
    - 'ㅁ' → 한글 모드
    - 'a' → 영문 모드
    """
    try:
        old_clip = _get_clipboard_text()
    except Exception:
        old_clip = None

    try:
        pyautogui.press("a")
        time.sleep(0.08)
        pyautogui.hotkey("shift", "left")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.05)

        text = (_get_clipboard_text() or "").strip()
        print(f"IME 프로브 결과: {text!r}")

        if not text:
            return None
        if text == "ㅁ" or "ㅁ" in text:
            return True
        if text.lower() == "a":
            return False
        # 기타 한글 자모/음절이면 한글 모드로 간주
        for ch in text:
            o = ord(ch)
            if 0x3131 <= o <= 0x318E or 0xAC00 <= o <= 0xD7A3:
                return True
        return False
    except Exception as exc:
        print(f"IME 프로브 실패: {exc}")
        return None
    finally:
        # 가능하면 클립보드 복구는 생략 (pyperclip 없음). 프로브 문자가 남아 있지 않게만 처리.
        _ = old_clip


def ensure_ime_mode(want_hangul: bool, tracked: bool) -> bool:
    """추적 상태가 목표와 다를 때만 한영키 1회."""
    if tracked == want_hangul:
        print(f"IME 유지: {'한글' if want_hangul else '영문'} (전환 없음)")
        return tracked

    print(
        f"IME 전환: {'한글' if tracked else '영문'} → {'한글' if want_hangul else '영문'}"
    )
    press_hangul_key()
    return want_hangul


def type_text_as_keys(text: str, interval: float = 0.05):
    if not text:
        return

    segments = split_script_segments(text)
    if not segments:
        return

    # 한글/영문 블록이 하나라도 있을 때만 프로브 (기호만이면 불필요)
    needs_mode = any(kind in ("hangul", "latin") for kind, _ in segments)
    if needs_mode:
        probed = probe_hangul_mode()
        if probed is None:
            print("IME 프로브 실패 → 영문 모드로 가정")
            tracked = False
        else:
            print(f"IME 시작 모드(프로브): {'한글' if probed else '영문'}")
            tracked = probed
    else:
        tracked = False

    for kind, chunk in segments:
        if not chunk:
            continue

        if kind == "hangul":
            tracked = ensure_ime_mode(True, tracked)
            keys = hangul_text_to_keys(chunk)
            if keys:
                pyautogui.typewrite(keys, interval=interval)
        elif kind == "latin":
            tracked = ensure_ime_mode(False, tracked)
            pyautogui.typewrite(chunk, interval=interval)
        else:
            pyautogui.typewrite(chunk, interval=interval)
