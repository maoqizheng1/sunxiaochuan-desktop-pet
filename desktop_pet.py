#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""孙笑川「闲庭信步」桌宠（Windows 分层窗口版）

- WS_EX_LAYERED + UpdateLayeredWindow，逐像素 alpha，边缘平滑无锯齿
- 帧序列循环播放（默认 15fps）
- 站在屏幕底部（任务栏上方）左右来回走，碰到左右边缘转身
- 右键菜单：暂停/继续、立即转身、大小（75%/100%/125%/150%）、退出
- 大小写入 pet_config.json，下次启动自动套用
- 左键拖动

依赖：Python 3 + Pillow + numpy（无 Tkinter）。
"""

import atexit
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMES_ROOT = os.path.join(APP_DIR, "frames")
PID_FILE = Path(APP_DIR) / "pet.pid"
CONFIG_FILE = Path(APP_DIR) / "pet_config.json"

ANIM_FPS = 15       # 动画循环帧率
TICK_MS = 30        # 定时器间隔（约 33fps）
WALK_SPEED = 55     # 走路速度：像素/秒
EDGE_MARGIN = 0     # 离屏幕左右边缘的留白
DEBUG = os.environ.get("PET_DEBUG") == "1"

SCALES = [
    (0.75, "75", "小 75%"),
    (1.00, "100", "中 100%"),
    (1.25, "125", "大 125%"),
    (1.50, "150", "特大 150%"),
]
DEFAULT_SCALE = 1.0

# ---------------------------------------------------------------- Win32 常量
WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
WM_NULL = 0x0000

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = ctypes.c_void_p(-1)
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1

MF_STRING = 0x00000000
MF_POPUP = 0x00000010
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

ID_PAUSE = 1001
ID_FLIP = 1002
ID_EXIT = 1003
ID_SIZE_BASE = 2000

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wt.HWND, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong
)
UINT_PTR = ctypes.c_size_t


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", wt.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]


# ---------------------------------------------------------------- Win32 签名
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, ctypes.c_ulonglong, ctypes.c_longlong]
user32.RegisterClassExW.restype = wt.ATOM
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
    wt.HDC, ctypes.POINTER(wt.POINT), wt.DWORD,
    ctypes.POINTER(BLENDFUNCTION), wt.DWORD,
]
user32.SetWindowPos.restype = wt.BOOL
user32.SetWindowPos.argtypes = [
    wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT
]
user32.ShowWindow.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetTimer.restype = UINT_PTR
user32.SetTimer.argtypes = [wt.HWND, UINT_PTR, wt.UINT, ctypes.c_void_p]
user32.KillTimer.restype = wt.BOOL
user32.KillTimer.argtypes = [wt.HWND, UINT_PTR]
user32.DestroyWindow.restype = wt.BOOL
user32.DestroyWindow.argtypes = [wt.HWND]
user32.PostQuitMessage.restype = None
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.GetMessageW.restype = wt.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.TranslateMessage.restype = wt.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.GetCursorPos.restype = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetCapture.restype = wt.HWND
user32.SetCapture.argtypes = [wt.HWND]
user32.ReleaseCapture.restype = wt.BOOL
user32.ReleaseCapture.argtypes = []
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.restype = wt.BOOL
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, UINT_PTR, wt.LPCWSTR]
user32.TrackPopupMenu.restype = wt.UINT
user32.TrackPopupMenu.argtypes = [
    wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.LPVOID
]
user32.DestroyMenu.restype = wt.BOOL
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.SetForegroundWindow.restype = wt.BOOL
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.PostMessageW.restype = wt.BOOL
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_ulonglong, ctypes.c_longlong]
user32.LoadCursorW.restype = wt.HANDLE
user32.LoadCursorW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
user32.SystemParametersInfoW.restype = wt.BOOL
user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, wt.LPVOID, wt.UINT]

gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
    ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD,
]
gdi32.SelectObject.restype = wt.HANDLE
gdi32.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteObject.argtypes = [wt.HANDLE]

kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.GetLastError.restype = wt.DWORD
kernel32.GetLastError.argtypes = []


# ---------------------------------------------------------------- 配置 / 单实例
def scale_tag(scale):
    for value, tag, _ in SCALES:
        if abs(value - scale) < 1e-6:
            return tag
    return "100"


def load_saved_scale():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        scale = float(data.get("scale", DEFAULT_SCALE))
    except Exception:
        return DEFAULT_SCALE
    for value, _, _ in SCALES:
        if abs(value - scale) < 1e-6:
            return value
    return DEFAULT_SCALE


def save_scale(scale):
    try:
        CONFIG_FILE.write_text(
            json.dumps({"scale": scale}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


_MUTEX = None


def acquire_single_instance():
    global _MUTEX
    _MUTEX = kernel32.CreateMutexW(None, False, "Local\\SunXiaochuanDesktopPet")
    if not _MUTEX:
        return True
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(_MUTEX)
        _MUTEX = None
        return False
    return True


def write_pid_file():
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def remove_pid_file():
    try:
        if PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except Exception:
        pass


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def get_work_area():
    rect = RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, 1920, 1080


# ---------------------------------------------------------------- 桌宠
class DesktopPet:
    def __init__(self):
        self.scale = load_saved_scale()
        self.tag = scale_tag(self.scale)
        self.frames = self._load_frames(self.tag)
        self.n = len(self.frames)
        self.h, self.w = self.frames[0].shape[:2]

        self.left, self.top, self.right, self.bottom = get_work_area()
        self.x = float(self.left)
        self.y = float(self.bottom - self.h - 2)
        self.facing = 1
        self.paused = False
        self.menu_open = False
        self.dragging = False
        self.drag_dx = 0
        self.drag_dy = 0
        self.idx = 0
        self.shown_idx = -1
        self.last_tick = time.perf_counter()
        self.t0 = self.last_tick
        self.last_pos = (None, None)

        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.hbitmap = None
        self.dib_ptr = ctypes.c_void_p()
        self.old_bitmap = None

        self._wndproc = WNDPROC(self._on_message)
        self.hwnd = self._create_window()
        self._create_dib(self.w, self.h)
        self._render(self.idx, update=True)
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetTimer(self.hwnd, 1, TICK_MS, None)

    # ---------- 帧 ----------
    def _load_frames(self, tag):
        folder = os.path.join(FRAMES_ROOT, tag)
        if not os.path.isdir(folder):
            raise SystemExit(f"找不到帧目录：{folder}")
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".png"))
        if not names:
            raise SystemExit(f"{folder} 里没有 PNG 帧")
        return [np.array(Image.open(os.path.join(folder, n)).convert("RGBA")) for n in names]

    # ---------- 窗口 ----------
    def _create_window(self):
        class_name = "SunXiaochuanPetWnd"
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
        wc.lpszClassName = class_name
        user32.RegisterClassExW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            class_name, "孙笑川桌宠", WS_POPUP,
            int(self.x), int(self.y), self.w, self.h,
            None, None, hinst, None,
        )
        if not hwnd:
            raise SystemExit(f"创建窗口失败：{kernel32.GetLastError()}")
        return hwnd

    def _create_dib(self, width, height):
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        ptr = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(
            self.mem_dc, ctypes.byref(bmi), 0, ctypes.byref(ptr), None, 0
        )
        if not hbmp:
            raise SystemExit("创建 DIB 失败")
        if self.hbitmap:
            gdi32.SelectObject(self.mem_dc, self.old_bitmap)
            gdi32.DeleteObject(self.hbitmap)
        self.old_bitmap = gdi32.SelectObject(self.mem_dc, hbmp)
        self.hbitmap = hbmp
        self.dib_ptr = ptr

    def _update_layered(self):
        size = wt.SIZE(self.w, self.h)
        src = wt.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(
            self.hwnd, self.screen_dc, None, ctypes.byref(size),
            self.mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA,
        )

    def _render(self, idx, update=True):
        arr = self.frames[idx]
        if self.facing < 0:
            arr = arr[:, ::-1]
        alpha = arr[:, :, 3].astype(np.uint16)
        bgra = np.empty((self.h, self.w, 4), dtype=np.uint8)
        bgra[:, :, 0] = (arr[:, :, 2].astype(np.uint16) * alpha // 255).astype(np.uint8)
        bgra[:, :, 1] = (arr[:, :, 1].astype(np.uint16) * alpha // 255).astype(np.uint8)
        bgra[:, :, 2] = (arr[:, :, 0].astype(np.uint16) * alpha // 255).astype(np.uint8)
        bgra[:, :, 3] = arr[:, :, 3]
        ctypes.memmove(self.dib_ptr, bgra.ctypes.data, bgra.nbytes)
        if update:
            self._update_layered()

    # ---------- 消息 ----------
    def _on_message(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TIMER:
                self._tick()
                return 0
            if msg == WM_LBUTTONDOWN:
                self._start_drag()
                return 0
            if msg == WM_MOUSEMOVE:
                self._drag_move()
                return 0
            if msg == WM_LBUTTONUP:
                self._end_drag()
                return 0
            if msg == WM_RBUTTONUP:
                self._show_menu()
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception as exc:  # 避免异常从回调里冒出导致窗口卡死
            if DEBUG:
                with open(os.path.join(APP_DIR, "pet_error.log"), "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%H:%M:%S')} {exc!r}\n")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---------- 交互 ----------
    def _start_drag(self):
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        self.drag_dx = pt.x - self.x
        self.drag_dy = pt.y - self.y
        self.dragging = True
        user32.SetCapture(self.hwnd)

    def _drag_move(self):
        if not self.dragging:
            return
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        self.x = float(pt.x - self.drag_dx)
        self.y = float(pt.y - self.drag_dy)
        self._move_window()

    def _end_drag(self):
        if not self.dragging:
            return
        self.dragging = False
        user32.ReleaseCapture()
        self.x = min(max(self.x, self.left), self.right - self.w)
        self.y = min(max(self.y, self.top), self.bottom - self.h)
        self._move_window()

    def _move_window(self):
        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, int(self.x), int(self.y), 0, 0,
            SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def _flip(self):
        self.facing *= -1
        self.shown_idx = -1
        self._render(self.idx)
        self.shown_idx = self.idx
        self._log(f"flip facing={self.facing:+.0f}")

    def _show_menu(self):
        self.menu_open = True
        menu = user32.CreatePopupMenu()
        cmd = 0
        try:
            user32.AppendMenuW(menu, MF_STRING, ID_PAUSE, "继续" if self.paused else "暂停")
            user32.AppendMenuW(menu, MF_STRING, ID_FLIP, "立即转身")

            sub = user32.CreatePopupMenu()
            for i, (value, _tag, label) in enumerate(SCALES):
                flags = MF_STRING | (MF_CHECKED if abs(value - self.scale) < 1e-9 else 0)
                user32.AppendMenuW(sub, flags, ID_SIZE_BASE + i, label)
            sub_id = sub.value if hasattr(sub, "value") else int(sub)
            user32.AppendMenuW(menu, MF_POPUP, sub_id, "大小")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_EXIT, "退出")

            pt = wt.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.hwnd)
            cmd = user32.TrackPopupMenu(
                menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None
            )
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)
            self.menu_open = False

        if cmd == ID_PAUSE:
            self.paused = not self.paused
        elif cmd == ID_FLIP:
            self._flip()
        elif ID_SIZE_BASE <= cmd < ID_SIZE_BASE + len(SCALES):
            self.apply_scale(SCALES[cmd - ID_SIZE_BASE][0])
        elif cmd == ID_EXIT:
            user32.DestroyWindow(self.hwnd)

    # ---------- 大小 ----------
    def apply_scale(self, scale):
        if abs(scale - self.scale) < 1e-9:
            return
        bottom = self.y + self.h
        self.scale = scale
        self.tag = scale_tag(scale)
        save_scale(scale)
        self._log(f"scale -> {scale:g}")

        self.frames = self._load_frames(self.tag)
        self.n = len(self.frames)
        self.h, self.w = self.frames[0].shape[:2]
        self.idx %= self.n
        self._create_dib(self.w, self.h)

        self.y = min(max(bottom - self.h, self.top), self.bottom - self.h)
        self.x = min(max(self.x, self.left), self.right - self.w)
        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, int(self.x), int(self.y), self.w, self.h,
            SWP_NOACTIVATE,
        )
        self._render(self.idx, update=True)
        self.shown_idx = self.idx

    # ---------- 主循环 ----------
    def _tick(self):
        if self.menu_open:
            return
        now = time.perf_counter()
        dt = min(now - self.last_tick, 0.1)
        self.last_tick = now
        if self.paused:
            return

        idx = int((now - self.t0) * ANIM_FPS) % self.n
        if idx != self.shown_idx:
            self._render(idx, update=True)
            self.shown_idx = idx

        self.x += self.facing * WALK_SPEED * dt
        if self.facing > 0 and self.x + self.w >= self.right - EDGE_MARGIN:
            self.x = float(self.right - self.w - EDGE_MARGIN)
            self._flip()
        elif self.facing < 0 and self.x <= self.left + EDGE_MARGIN:
            self.x = float(self.left + EDGE_MARGIN)
            self._flip()

        pos = (int(self.x), int(self.y))
        if pos != self.last_pos:
            self._move_window()
            self.last_pos = pos

    def _log(self, msg):
        if DEBUG:
            with open(os.path.join(APP_DIR, "pet_debug.log"), "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    # ---------- 运行 ----------
    def run(self):
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def close(self):
        try:
            user32.KillTimer(self.hwnd, 1)
        except Exception:
            pass
        if self.hbitmap:
            gdi32.SelectObject(self.mem_dc, self.old_bitmap)
            gdi32.DeleteObject(self.hbitmap)
            self.hbitmap = None
        if self.mem_dc:
            gdi32.DeleteDC(self.mem_dc)
            self.mem_dc = None
        if self.screen_dc:
            user32.ReleaseDC(None, self.screen_dc)
            self.screen_dc = None


def main():
    enable_dpi_awareness()
    if not acquire_single_instance():
        return
    write_pid_file()
    atexit.register(remove_pid_file)
    pet = None
    try:
        pet = DesktopPet()
        pet.run()
    finally:
        if pet is not None:
            pet.close()
        remove_pid_file()


if __name__ == "__main__":
    main()
