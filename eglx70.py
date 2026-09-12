import xml.etree.ElementTree as ET
import colorsys
import math
import json
import os
import sys
import ctypes
from ctypes import wintypes
import threading
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# winreg доступен только на Windows — как и остальной WinAPI-функционал этой
# программы (HID-транспорт использует ctypes.WinDLL). На других платформах
# просто отключаем связанную с автозапуском функциональность.
try:
    import winreg
except ImportError:
    winreg = None

# Библиотеки для иконки в системном трее — опциональная зависимость.
# Если не установлены (pip install pystray pillow), функции "свернуть в
# трей" в настройках будут недоступны, но остальная программа работает как обычно.
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_LIBS_AVAILABLE = True
except ImportError:
    TRAY_LIBS_AVAILABLE = False


def resource_path(relative_path):
    """Возвращает абсолютный путь к ресурсу. 
    Работает как при обычном запуске, так и внутри скомпилированного .exe (PyInstaller).
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_app_dir():
    """Папка, где физически лежит .exe (PyInstaller) либо .py скрипт.

    Используется для постоянного хранения пользовательских данных (пресетов),
    в отличие от resource_path/_MEIPASS, который указывает на временную
    распакованную папку и не годится для записи.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


PRESETS_DIR_NAME = "presets"


def get_presets_dir():
    """Возвращает (и при необходимости создаёт) папку presets рядом с программой."""
    path = os.path.join(get_app_dir(), PRESETS_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def sanitize_filename(name):
    """Убирает символы, недопустимые в именах файлов Windows/Linux."""
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    cleaned = re.sub(r'\s+', " ", cleaned)
    return cleaned or "preset"


# ---------------------------------------------------------------------------
# Настройки приложения (settings.json рядом с программой)
# ---------------------------------------------------------------------------

SETTINGS_FILE_NAME = "settings.json"

DEFAULT_APP_SETTINGS = {
    "start_minimized": False,
    "minimize_on_close": False,
    "hotkey_next_preset": None,   # {"vk": int, "scan": int, "ext": bool} либо None
    "hotkey_prev_preset": None,
}

# Ключи настроек, значения которых — простые bool, а не структуры хоткеев.
_BOOL_SETTING_KEYS = ("start_minimized", "minimize_on_close")
_HOTKEY_SETTING_KEYS = ("hotkey_next_preset", "hotkey_prev_preset")


def get_settings_path():
    return os.path.join(get_app_dir(), SETTINGS_FILE_NAME)


def _sanitize_hotkey_binding(value):
    """Проверяет, что структура хоткея из settings.json корректна."""
    if not isinstance(value, dict):
        return None
    try:
        return {
            "vk": int(value["vk"]),
            "scan": int(value["scan"]),
            "ext": bool(value.get("ext", False)),
            "ctrl": bool(value.get("ctrl", False)),
            "alt": bool(value.get("alt", False)),
            "shift": bool(value.get("shift", False)),
            "win": bool(value.get("win", False)),
        }
    except (KeyError, TypeError, ValueError):
        return None


def load_app_settings():
    """Загружает настройки трея/сворачивания/хоткеев из settings.json (или значения по умолчанию)."""
    settings = dict(DEFAULT_APP_SETTINGS)
    try:
        with open(get_settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in _BOOL_SETTING_KEYS:
                if key in data:
                    settings[key] = bool(data[key])
            for key in _HOTKEY_SETTING_KEYS:
                if key in data:
                    settings[key] = _sanitize_hotkey_binding(data[key])
    except Exception:
        pass
    return settings


def save_app_settings(settings):
    try:
        with open(get_settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Глобальный низкоуровневый хук клавиатуры (WH_KEYBOARD_LL) — используется
# для горячих клавиш переключения пресетов (например, Fn+=/Fn+-).
#
# ВАЖНО: Windows в принципе не знает о клавише Fn — это чисто firmware-side
# концепция самой клавиатуры. Если прошивка Galaxy 70 не переназначает Fn+=
# на какой-то отдельный код, а просто пропускает голый скан-код "=" (как будто
# Fn не нажимался), то отличить "просто =" от "Fn+=" программно невозможно —
# в этом случае сработает ЛЮБОЕ нажатие "=", включая обычный набор текста.
# (Именно так и оказалось на практике с Fn+=/Fn+- на Galaxy 70 — прошивка не
# отличает их от голых "=" и "-".) Поэтому хоткеи строятся на обычных
# модификаторах Ctrl/Alt/Shift/Win — они, в отличие от Fn, реально видны
# Windows и корректно транслируются в события клавиатуры.
# ---------------------------------------------------------------------------

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
LLKHF_EXTENDED = 0x01

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12  # Alt = VK_MENU
VK_LWIN, VK_RWIN = 0x5B, 0x5C

# Все виртуальные коды, которые считаются "модификатором" и не могут сами по
# себе быть основной клавишей хоткея (левые/правые Shift/Ctrl/Alt/Win).
_MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C}

_LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

# ctypes.WINFUNCTYPE (соглашение вызова stdcall) существует только на Windows.
# Программа в любом случае Windows-only (см. Galaxy70HidTransport на ctypes.windll),
# но эта проверка не даёт упасть при простом импорте/анализе модуля на другой ОС.
if sys.platform == "win32":
    _HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
else:
    _HOOKPROC = None


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


def _get_modifier_state():
    """Текущее состояние Ctrl/Alt/Shift/Win через GetAsyncKeyState —
    в отличие от Fn, эти модификаторы Windows видит по-настоящему."""
    user32 = ctypes.windll.user32
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

    def is_down(vk):
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    return {
        "ctrl": is_down(VK_CONTROL),
        "alt": is_down(VK_MENU),
        "shift": is_down(VK_SHIFT),
        "win": is_down(VK_LWIN) or is_down(VK_RWIN),
    }


# Человекочитаемые названия для наиболее вероятных "основных" клавиш хоткея.
_VK_NAMES = {
    0xBB: "=", 0xBD: "-", 0x6B: "Num +", 0x6D: "Num -",
    0xAE: "Volume Down", 0xAF: "Volume Up", 0xAD: "Volume Mute",
    0xB0: "Media Next", 0xB1: "Media Prev", 0xB3: "Media Play/Pause",
    0x21: "Page Up", 0x22: "Page Down", 0x24: "Home", 0x23: "End",
    0x26: "Up", 0x28: "Down", 0x25: "Left", 0x27: "Right",
    0x2D: "Insert", 0x2E: "Delete", 0x2C: "PrtScn", 0x91: "ScrollLock", 0x13: "Pause",
}


def hotkey_binding_to_label(binding):
    if not binding:
        return None
    vk = binding.get("vk", 0)
    parts = []
    if binding.get("ctrl"):
        parts.append("Ctrl")
    if binding.get("alt"):
        parts.append("Alt")
    if binding.get("shift"):
        parts.append("Shift")
    if binding.get("win"):
        parts.append("Win")
    name = _VK_NAMES.get(vk)
    parts.append(name if name else f"VK 0x{vk:02X}")
    return "+".join(parts)


def hotkey_bindings_equal(binding, vk, scan, ext, mods):
    if not binding:
        return False
    return (
        int(binding.get("vk", -1)) == vk
        and bool(binding.get("ctrl", False)) == bool(mods.get("ctrl"))
        and bool(binding.get("alt", False)) == bool(mods.get("alt"))
        and bool(binding.get("shift", False)) == bool(mods.get("shift"))
        and bool(binding.get("win", False)) == bool(mods.get("win"))
    )


class HotkeyManager:
    """Держит низкоуровневый хук клавиатуры в отдельном потоке со своим
    циклом сообщений (это требование WinAPI для WH_KEYBOARD_LL) и
    пробрасывает каждое нажатие "основной" клавиши (не модификатора) вместе
    с текущим состоянием Ctrl/Alt/Shift/Win в основной Tk-поток через root.after."""

    def __init__(self, on_key_event):
        self.on_key_event = on_key_event  # callback(vkCode, scanCode, extended, mods)
        self._thread = None
        self._thread_id = None
        self._hook_id = None
        self._hook_proc_ref = None  # держим ссылку, иначе GC соберёт колбэк
        self._running = False

    def start(self):
        if sys.platform != "win32" or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._running or self._thread_id is None:
            return
        try:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        except Exception:
            pass

    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.CallNextHookEx.restype = _LRESULT
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        self._thread_id = kernel32.GetCurrentThreadId()

        def low_level_handler(nCode, wParam, lParam):
            if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                vk = int(kb.vkCode)
                # Модификатор сам по себе не может быть "основной" клавишей —
                # ждём, пока вместе с ним нажмут что-то ещё.
                if vk not in _MODIFIER_VKS:
                    extended = bool(kb.flags & LLKHF_EXTENDED)
                    scan = int(kb.scanCode)
                    mods = _get_modifier_state()
                    try:
                        self.on_key_event(vk, scan, extended, mods)
                    except Exception:
                        pass
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._hook_proc_ref = _HOOKPROC(low_level_handler)
        h_mod = kernel32.GetModuleHandleW(None)
        self._hook_id = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, h_mod, 0)

        if not self._hook_id:
            self._running = False
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnhookWindowsHookEx(self._hook_id)
        self._hook_id = None
        self._running = False


# ---------------------------------------------------------------------------
# Автозапуск при включении компьютера (HKCU\...\Run)
# ---------------------------------------------------------------------------

STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VALUE_NAME = "EpomakerGalaxy70Editor"


def get_startup_command():
    """Команда, которая будет прописана в реестре для автозапуска."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script_path = os.path.abspath(__file__)
    return f'"{sys.executable}" "{script_path}"'


def is_run_at_startup():
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_QUERY_VALUE)
        try:
            value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
            return bool(value)
        finally:
            winreg.CloseKey(key)
    except (FileNotFoundError, OSError):
        return False


def set_run_at_startup(enable):
    if winreg is None:
        raise RuntimeError("winreg is unavailable on this platform")

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE)
    try:
        if enable:
            winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, get_startup_command())
        else:
            try:
                winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


# Раскладка клавиш по стандартам USB HID Usage ID
KEYBOARD_LAYOUT = {
    # Ряд F-клавиш
    41: ("Esc", 0, 0, 1), 58: ("F1", 2, 0, 1), 59: ("F2", 3, 0, 1), 60: ("F3", 4, 0, 1), 61: ("F4", 5, 0, 1),
    62: ("F5", 6.5, 0, 1), 63: ("F6", 7.5, 0, 1), 64: ("F7", 8.5, 0, 1), 65: ("F8", 9.5, 0, 1),
    66: ("F9", 11, 0, 1), 67: ("F10", 12, 0, 1), 68: ("F11", 13, 0, 1), 69: ("F12", 14, 0, 1),
    70: ("PrtSc", 15.25, 0, 1),
    
    # Цифровой ряд
    53: ("~", 0, 1.2, 1), 30: ("1", 1, 1.2, 1), 31: ("2", 2, 1.2, 1), 32: ("3", 3, 1.2, 1), 33: ("4", 4, 1.2, 1),
    34: ("5", 5, 1.2, 1), 35: ("6", 6, 1.2, 1), 36: ("7", 7, 1.2, 1), 38: ("9", 9, 1.2, 1),
    39: ("0", 10, 1.2, 1), 37: ("8", 8, 1.2, 1), 45: ("-", 11, 1.2, 1), 46: ("=", 12, 1.2, 1), 42: ("Backspace", 13, 1.2, 2),
    74: ("Home", 15.25, 1.2, 1), 75: ("PgUp", 16.25, 1.2, 1),

    # Ряд QWERTY
    43: ("Tab", 0, 2.2, 1.5), 20: ("Q", 1.5, 2.2, 1), 26: ("W", 2.5, 2.2, 1), 8: ("E", 3.5, 2.2, 1), 21: ("R", 4.5, 2.2, 1),
    23: ("T", 5.5, 2.2, 1), 28: ("Y", 6.5, 2.2, 1), 24: ("U", 7.5, 2.2, 1), 12: ("I", 8.5, 2.2, 1), 18: ("O", 9.5, 2.2, 1),
    19: ("P", 10.5, 2.2, 1), 47: ("[", 11.5, 2.2, 1), 48: ("]", 12.5, 2.2, 1), 49: ("\\", 13.5, 2.2, 1.5),
    76: ("Del", 15.25, 2.2, 1), 78: ("PgDn", 16.25, 2.2, 1),

    # Ряд ASDF
    57: ("Caps", 0, 3.2, 1.75), 4: ("A", 1.75, 3.2, 1), 22: ("S", 2.75, 3.2, 1), 7: ("D", 3.75, 3.2, 1), 9: ("F", 4.75, 3.2, 1),
    10: ("G", 5.75, 3.2, 1), 11: ("H", 6.75, 3.2, 1), 13: ("J", 7.75, 3.2, 1), 14: ("K", 8.75, 3.2, 1), 15: ("L", 9.75, 3.2, 1),
    51: (";", 10.75, 3.2, 1), 52: ("'", 11.75, 3.2, 1), 40: ("Enter", 12.75, 3.2, 2.25),

    # Ряд ZXCV
    225: ("Shift", 0, 4.2, 2.25), 29: ("Z", 2.25, 4.2, 1), 27: ("X", 3.25, 4.2, 1), 6: ("C", 4.25, 4.2, 1), 25: ("V", 5.25, 4.2, 1),
    5: ("B", 6.25, 4.2, 1), 17: ("N", 7.25, 4.2, 1), 16: ("M", 8.25, 4.2, 1), 54: (",", 9.25, 4.2, 1), 55: (".", 10.25, 4.2, 1),
    56: ("/", 11.25, 4.2, 1), 229: ("Shift", 12.25, 4.2, 2.75),
    82: ("↑", 15.25, 4.2, 1),

    # Нижний ряд
    224: ("Ctrl", 0, 5.2, 1.25), 227: ("Win", 1.25, 5.2, 1.25), 226: ("Alt", 2.5, 5.2, 1.25),
    44: ("Space", 3.75, 5.2, 6.25),
    230: ("Alt", 10, 5.2, 1.25), 175: ("Fn", 11.25, 5.2, 1.25), 228: ("Ctrl", 12.5, 5.2, 1.25),
    80: ("←", 14.25, 5.2, 1), 81: ("↓", 15.25, 5.2, 1), 79: ("→", 16.25, 5.2, 1)
}

# Расчет геометрии клавиатуры для градиентов
KEY_CENTERS = {}
x_coords, y_coords = [], []
for k_code, (lbl, x_u, y_u, w_u) in KEYBOARD_LAYOUT.items():
    cx = x_u + w_u / 2.0
    cy = y_u + 0.5
    KEY_CENTERS[k_code] = (cx, cy)
    x_coords.append(cx)
    y_coords.append(cy)

MIN_X, MAX_X = min(x_coords), max(x_coords)
MIN_Y, MAX_Y = min(y_coords), max(y_coords)
MID_X, MID_Y = (MIN_X + MAX_X) / 2.0, (MIN_Y + MAX_Y) / 2.0
MAX_RAD = ((MAX_X - MID_X) ** 2 + (MAX_Y - MID_Y) ** 2) ** 0.5


def colorref_to_hex_and_rgb(val):
    val = int(val)
    r = val & 0xFF
    g = (val >> 8) & 0xFF
    b = (val >> 16) & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}", (r, g, b)

def rgb_to_colorref(r, g, b):
    return r + (g << 8) + (b << 16)

def get_text_color(r, g, b):
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luminance > 128 else "#ffffff"


# ---------------------------------------------------------------------------
# Galaxy 70 HID transport
# ---------------------------------------------------------------------------
# The working Galaxy70 PowerShell script talks to the lighting HID interface
# directly. The implementation below mirrors its protocol without creating a
# temporary .ps1 file:
#
#   PING -> BEGIN -> 20 DATA frames -> END
#
# The device exposes a 33-byte HID report: one report-ID byte (0) followed by
# the 32-byte protocol frame. DATA block 0 is special (6 keys, bytes 7..30),
# the remaining blocks contain 7 four-byte key/RGB entries starting at byte 3.

KEY_CODE_TO_SLOT = {
    # Function row
    41: 1, 58: 2, 59: 3, 60: 4, 61: 5, 62: 6, 63: 7,
    64: 8, 65: 9, 66: 10, 67: 11, 68: 12, 69: 13, 70: 112,
    # Number row + navigation
    53: 19, 30: 20, 31: 21, 32: 22, 33: 23, 34: 24, 35: 25,
    36: 26, 37: 27, 38: 28, 39: 29, 45: 30, 46: 31, 42: 103,
    74: 117, 75: 118,
    # QWERTY row
    43: 37, 20: 38, 26: 39, 8: 40, 21: 41, 23: 42, 28: 43,
    24: 44, 12: 45, 18: 46, 19: 47, 47: 48, 48: 49, 49: 67,
    76: 119, 78: 121,
    # ASDF row
    57: 55, 4: 56, 22: 57, 7: 58, 9: 59, 10: 60, 11: 61,
    13: 62, 14: 63, 15: 64, 51: 65, 52: 66, 40: 85,
    # ZXCV row
    225: 73, 29: 74, 27: 75, 6: 76, 25: 77, 5: 78, 17: 79,
    16: 80, 54: 81, 55: 82, 56: 83, 229: 84, 82: 101,
    # Bottom row
    224: 91, 227: 92, 226: 93, 44: 94, 230: 95, 175: 96,
    228: 98, 80: 99, 81: 100, 79: 102,
}

ACTIVE_KEY_INDICES = list(KEY_CODE_TO_SLOT.values())


def _checksum_31(body31):
    return sum(body31) & 0xFF


def _make_frame(body31):
    if len(body31) != 31:
        raise ValueError("Internal HID error: frame body must contain 31 bytes.")
    return bytes(body31) + bytes([_checksum_31(body31)])


def _make_ping_frame():
    body = bytearray(31)
    body[0] = 0x20
    body[1] = 0x01
    return _make_frame(body)


def _make_begin_frame():
    body = bytearray(31)
    body[0] = 0x05
    body[1] = 0x10
    body[3] = 0x80
    body[12] = 0x05
    body[17] = 0xAA
    body[18] = 0x55
    return _make_frame(body)


def _make_end_frame(total_blocks=20):
    body = bytearray(31)
    body[0] = 0x14
    body[1] = 0x10
    body[2] = total_blocks & 0xFF
    body[17] = 0xAA
    body[18] = 0x55
    return _make_frame(body)


def _make_data_frame(block_index, color_map):
    body = bytearray(31)
    body[0] = 0x14
    body[1] = 0x1C
    body[2] = block_index & 0xFF

    if block_index == 0:
        start_key = 1
        slot_count = 6
        data_offset = 7
    else:
        start_key = 7 * block_index
        slot_count = 7
        data_offset = 3

    for s in range(slot_count):
        key_index = start_key + s
        rgb = color_map.get(key_index)
        if rgb is None:
            continue

        off = data_offset + s * 4
        body[off] = key_index & 0xFF
        body[off + 1] = int(rgb[0]) & 0xFF
        body[off + 2] = int(rgb[1]) & 0xFF
        body[off + 3] = int(rgb[2]) & 0xFF

    return _make_frame(body)


def _build_command_sequence(color_map):
    sequence = [_make_ping_frame(), _make_begin_frame()]
    sequence.extend(_make_data_frame(block, color_map) for block in range(20))
    sequence.append(_make_end_frame(20))
    return sequence


class Galaxy70HidTransport:
    """Minimal ctypes port of the proven Galaxy70 PowerShell HID transport."""

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    DIGCF_PRESENT = 0x00000002
    DIGCF_DEVICEINTERFACE = 0x00000010
    ERROR_IO_PENDING = 997
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    INFINITE = 0xFFFFFFFF
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Apply RGB is supported on Windows only.")

        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.hid = ctypes.WinDLL("hid", use_last_error=True)
        self.setupapi = ctypes.WinDLL("setupapi", use_last_error=True)

        self._define_structs()
        self._define_functions()

    def _define_structs(self):
        class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint32),
                ("InterfaceClassGuid", ctypes.c_byte * 16),
                ("Flags", ctypes.c_uint32),
                ("Reserved", ctypes.c_void_p),
            ]

        class HIDP_CAPS(ctypes.Structure):
            _fields_ = [
                ("Usage", ctypes.c_uint16),
                ("UsagePage", ctypes.c_uint16),
                ("InputReportByteLength", ctypes.c_uint16),
                ("OutputReportByteLength", ctypes.c_uint16),
                ("FeatureReportByteLength", ctypes.c_uint16),
                ("Reserved", ctypes.c_uint16 * 17),
                ("NumberLinkCollectionNodes", ctypes.c_uint16),
                ("NumberInputButtonCaps", ctypes.c_uint16),
                ("NumberInputValueCaps", ctypes.c_uint16),
                ("NumberInputDataIndices", ctypes.c_uint16),
                ("NumberOutputButtonCaps", ctypes.c_uint16),
                ("NumberOutputValueCaps", ctypes.c_uint16),
                ("NumberOutputDataIndices", ctypes.c_uint16),
                ("NumberFeatureButtonCaps", ctypes.c_uint16),
                ("NumberFeatureValueCaps", ctypes.c_uint16),
                ("NumberFeatureDataIndices", ctypes.c_uint16),
            ]

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.c_uint32),
                ("OffsetHigh", ctypes.c_uint32),
                ("hEvent", ctypes.c_void_p),
            ]

        self.SP_DEVICE_INTERFACE_DATA = SP_DEVICE_INTERFACE_DATA
        self.HIDP_CAPS = HIDP_CAPS
        self.OVERLAPPED = OVERLAPPED

    def _define_functions(self):
        k32 = self.kernel32
        hid = self.hid
        setup = self.setupapi

        k32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p
        ]
        k32.CreateFileW.restype = ctypes.c_void_p

        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.restype = ctypes.c_int

        k32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        k32.CreateEventW.restype = ctypes.c_void_p

        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.WaitForSingleObject.restype = ctypes.c_uint32

        k32.WriteFile.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.POINTER(self.OVERLAPPED)
        ]
        k32.WriteFile.restype = ctypes.c_int

        k32.ReadFile.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.POINTER(self.OVERLAPPED)
        ]
        k32.ReadFile.restype = ctypes.c_int

        k32.GetOverlappedResult.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(self.OVERLAPPED),
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_int
        ]
        k32.GetOverlappedResult.restype = ctypes.c_int

        k32.CancelIo.argtypes = [ctypes.c_void_p]
        k32.CancelIo.restype = ctypes.c_int

        hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(ctypes.c_byte * 16)]
        hid.HidD_GetHidGuid.restype = None

        hid.HidD_GetPreparsedData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        hid.HidD_GetPreparsedData.restype = ctypes.c_int

        hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        hid.HidD_FreePreparsedData.restype = ctypes.c_int

        hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(self.HIDP_CAPS)]
        hid.HidP_GetCaps.restype = ctypes.c_int32

        setup.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(ctypes.c_byte * 16), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_uint32
        ]
        setup.SetupDiGetClassDevsW.restype = ctypes.c_void_p

        setup.SetupDiEnumDeviceInterfaces.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_byte * 16), ctypes.c_uint32,
            ctypes.POINTER(self.SP_DEVICE_INTERFACE_DATA)
        ]
        setup.SetupDiEnumDeviceInterfaces.restype = ctypes.c_int

        setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(self.SP_DEVICE_INTERFACE_DATA),
            ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p
        ]
        setup.SetupDiGetDeviceInterfaceDetailW.restype = ctypes.c_int

        setup.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        setup.SetupDiDestroyDeviceInfoList.restype = ctypes.c_int

    @staticmethod
    def _guid_from_bytes(guid_bytes):
        guid = (ctypes.c_byte * 16)()
        ctypes.memmove(ctypes.byref(guid), guid_bytes, 16)
        return guid

    def find_lighting_interface(self):
        guid = (ctypes.c_byte * 16)()
        self.hid.HidD_GetHidGuid(ctypes.byref(guid))

        device_set = self.setupapi.SetupDiGetClassDevsW(
            ctypes.byref(guid), None, None,
            self.DIGCF_PRESENT | self.DIGCF_DEVICEINTERFACE
        )
        if device_set == self.INVALID_HANDLE_VALUE or not device_set:
            error = ctypes.get_last_error()
            raise RuntimeError(f"Cannot enumerate HID devices. Windows error {error}.")

        try:
            index = 0
            while True:
                interface_data = self.SP_DEVICE_INTERFACE_DATA()
                interface_data.cbSize = ctypes.sizeof(self.SP_DEVICE_INTERFACE_DATA)

                ok = self.setupapi.SetupDiEnumDeviceInterfaces(
                    device_set, None, ctypes.byref(guid), index,
                    ctypes.byref(interface_data)
                )
                if not ok:
                    break

                required = ctypes.c_uint32(0)
                self.setupapi.SetupDiGetDeviceInterfaceDetailW(
                    device_set, ctypes.byref(interface_data), None, 0,
                    ctypes.byref(required), None
                )
                if required.value == 0:
                    index += 1
                    continue

                detail = ctypes.create_string_buffer(required.value)
                cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                ctypes.memmove(detail, ctypes.byref(ctypes.c_uint32(cb_size)), 4)

                ok = self.setupapi.SetupDiGetDeviceInterfaceDetailW(
                    device_set, ctypes.byref(interface_data), detail,
                    required.value, ctypes.byref(required), None
                )
                if not ok:
                    index += 1
                    continue

                path = ctypes.wstring_at(ctypes.addressof(detail) + 4)
                if "vid_05ac&pid_024f" not in path.lower():
                    index += 1
                    continue

                handle = self.kernel32.CreateFileW(
                    path,
                    self.GENERIC_READ | self.GENERIC_WRITE,
                    self.FILE_SHARE_READ | self.FILE_SHARE_WRITE,
                    None,
                    self.OPEN_EXISTING,
                    0,
                    None,
                )
                if not handle or handle == self.INVALID_HANDLE_VALUE:
                    index += 1
                    continue

                try:
                    preparsed = ctypes.c_void_p()
                    if not self.hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
                        index += 1
                        continue
                    try:
                        caps = self.HIDP_CAPS()
                        status = self.hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
                        if status >= 0 and caps.OutputReportByteLength == 33 and caps.InputReportByteLength == 33:
                            return path
                    finally:
                        self.hid.HidD_FreePreparsedData(preparsed)
                finally:
                    self.kernel32.CloseHandle(handle)

                index += 1
        finally:
            self.setupapi.SetupDiDestroyDeviceInfoList(device_set)

        return None

    def _open_overlapped(self, path):
        handle = self.kernel32.CreateFileW(
            path,
            self.GENERIC_READ | self.GENERIC_WRITE,
            self.FILE_SHARE_READ | self.FILE_SHARE_WRITE,
            None,
            self.OPEN_EXISTING,
            self.FILE_FLAG_OVERLAPPED,
            None,
        )
        if not handle or handle == self.INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            raise RuntimeError(
                f"The Galaxy 70 lighting HID interface could not be opened. Windows error {error}."
            )
        return handle

    def _write_then_read(self, handle, report, read_size=33, timeout_ms=300):
        write_event = self.kernel32.CreateEventW(None, True, False, None)
        read_event = self.kernel32.CreateEventW(None, True, False, None)
        if not write_event or not read_event:
            if write_event:
                self.kernel32.CloseHandle(write_event)
            if read_event:
                self.kernel32.CloseHandle(read_event)
            raise RuntimeError("Could not create Windows HID events.")

        try:
            write_buffer = ctypes.create_string_buffer(report)
            ov_write = self.OVERLAPPED()
            ov_write.hEvent = write_event

            ok = self.kernel32.WriteFile(
                handle, write_buffer, len(report), None, ctypes.byref(ov_write)
            )
            if not ok:
                error = ctypes.get_last_error()
                if error != self.ERROR_IO_PENDING:
                    raise RuntimeError(f"WriteFile failed. Windows error {error}.")
                wait_result = self.kernel32.WaitForSingleObject(write_event, timeout_ms)
                if wait_result == self.WAIT_TIMEOUT:
                    self.kernel32.CancelIo(handle)
                    raise RuntimeError("WriteFile timed out.")
                if wait_result != self.WAIT_OBJECT_0:
                    self.kernel32.CancelIo(handle)
                    raise RuntimeError(f"WriteFile wait failed: {wait_result}.")

                written = ctypes.c_uint32(0)
                if not self.kernel32.GetOverlappedResult(
                    handle, ctypes.byref(ov_write), ctypes.byref(written), False
                ):
                    error = ctypes.get_last_error()
                    raise RuntimeError(f"WriteFile overlapped result failed. Windows error {error}.")

            read_buffer = ctypes.create_string_buffer(read_size)
            ov_read = self.OVERLAPPED()
            ov_read.hEvent = read_event

            ok = self.kernel32.ReadFile(
                handle, read_buffer, read_size, None, ctypes.byref(ov_read)
            )
            if not ok:
                error = ctypes.get_last_error()
                if error != self.ERROR_IO_PENDING:
                    return None
                wait_result = self.kernel32.WaitForSingleObject(read_event, timeout_ms)
                if wait_result == self.WAIT_TIMEOUT:
                    self.kernel32.CancelIo(handle)
                    return None
                if wait_result != self.WAIT_OBJECT_0:
                    return None

                read = ctypes.c_uint32(0)
                if not self.kernel32.GetOverlappedResult(
                    handle, ctypes.byref(ov_read), ctypes.byref(read), False
                ):
                    return None

            return bytes(read_buffer.raw[:read_size])
        finally:
            self.kernel32.CloseHandle(write_event)
            self.kernel32.CloseHandle(read_event)

    def apply_rgb_map(self, color_map):
        path = self.find_lighting_interface()
        if not path:
            raise RuntimeError(
                "The Galaxy 70 lighting interface (VID_05AC&PID_024F, 33-byte HID collection) "
                "was not found. Make sure the 2.4 GHz receiver is connected."
            )

        handle = self._open_overlapped(path)
        try:
            sequence = _build_command_sequence(color_map)
            for frame in sequence:
                report = bytes([0]) + frame
                self._write_then_read(handle, report, 33, 300)
                time_sleep = 0.005
                # Keep parity with the working PS1 script without importing an
                # additional module just for a five-millisecond pause.
                import time
                time.sleep(time_sleep)
        finally:
            self.kernel32.CloseHandle(handle)


def build_live_color_map(app):
    """Collect the final RGB shown by the virtual keyboard and map to HID slots."""
    color_map = {}
    for key_code in KEYBOARD_LAYOUT:
        color_data = app.get_key_effective_color(key_code)
        if color_data is None:
            continue
        _, (r, g, b), _ = color_data
        color_map[KEY_CODE_TO_SLOT[key_code]] = (r, g, b)

    if set(color_map) - set(ACTIVE_KEY_INDICES):
        raise RuntimeError("Internal key mapping error: unsupported lighting slot.")
    return color_map


class PhotoshopColorPicker(tk.Frame):
    """Кастомная палитра цветов в стиле Photoshop (Квадрат SV + Вертикальная полоса Hue)."""
    def __init__(self, parent, on_color_change_callback):
        super().__init__(parent, bg="#25252b")
        self.on_color_change = on_color_change_callback

        self.hue = 0.0        # 0.0 - 1.0
        self.sat = 1.0        # 0.0 - 1.0
        self.val = 1.0        # 0.0 - 1.0

        # Квадрат Палитры (Saturation x Value)
        self.sv_size = 140
        self.sv_canvas = tk.Canvas(self, width=self.sv_size, height=self.sv_size, highlightthickness=1, highlightbackground="#444")
        self.sv_canvas.grid(row=0, column=0, padx=(0, 8), pady=5)
        self.sv_canvas.bind("<Button-1>", self.on_sv_click)
        self.sv_canvas.bind("<B1-Motion>", self.on_sv_click)

        # Полоса Оттенка (Hue Slider)
        self.hue_width = 18
        self.hue_canvas = tk.Canvas(self, width=self.hue_width, height=self.sv_size, highlightthickness=1, highlightbackground="#444")
        self.hue_canvas.grid(row=0, column=1, pady=5)
        self.hue_canvas.bind("<Button-1>", self.on_hue_click)
        self.hue_canvas.bind("<B1-Motion>", self.on_hue_click)

        self.draw_hue_bar()
        self.draw_sv_square()

    def draw_hue_bar(self):
        self.hue_canvas.delete("all")
        for y in range(self.sv_size):
            h = 1.0 - (y / self.sv_size)
            r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, 1.0, 1.0)]
            self.hue_canvas.create_line(0, y, self.hue_width, y, fill=f"#{r:02x}{g:02x}{b:02x}")

    def draw_sv_square(self):
        self.sv_canvas.delete("all")
        step = 3
        for x in range(0, self.sv_size, step):
            s = x / self.sv_size
            for y in range(0, self.sv_size, step):
                v = 1.0 - (y / self.sv_size)
                r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(self.hue, s, v)]
                self.sv_canvas.create_rectangle(x, y, x + step, y + step, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

        cur_x = self.sat * self.sv_size
        cur_y = (1.0 - self.val) * self.sv_size
        self.sv_canvas.create_oval(cur_x - 4, cur_y - 4, cur_x + 4, cur_y + 4, outline="white", width=2)

    def draw_hue_marker(self):
        self.hue_canvas.delete("marker")
        cur_y = (1.0 - self.hue) * self.sv_size
        self.hue_canvas.create_line(0, cur_y, self.hue_width, cur_y, fill="white", width=2, tags="marker")

    def on_sv_click(self, event):
        x = max(0, min(self.sv_size, event.x))
        y = max(0, min(self.sv_size, event.y))
        self.sat = x / self.sv_size
        self.val = 1.0 - (y / self.sv_size)
        self.draw_sv_square()
        self.notify_change()

    def on_hue_click(self, event):
        y = max(0, min(self.sv_size, event.y))
        self.hue = 1.0 - (y / self.sv_size)
        self.draw_hue_bar()
        self.draw_hue_marker()
        self.draw_sv_square()
        self.notify_change()

    def set_color_from_rgb(self, r, g, b):
        self.hue, self.sat, self.val = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        self.draw_hue_bar()
        self.draw_hue_marker()
        self.draw_sv_square()

    def get_rgb(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        return int(r * 255), int(g * 255), int(b * 255)

    def get_hex(self):
        r, g, b = self.get_rgb()
        return f"#{r:02x}{g:02x}{b:02x}"

    def notify_change(self):
        if self.on_color_change:
            self.on_color_change(self.get_hex())


class RGBSliderPanel(tk.Frame):
    """Три слайдера R/G/B с полями для точного ввода значений.

    Числовое поле каждого канала закреплено в правом верхнем углу
    над соответствующим слайдером и поддерживает ручной ввод значения
    (0-255) с клавиатуры (Enter или потеря фокуса применяют значение).
    """

    CHANNELS = (("R", "#ff6b6b"), ("G", "#6bff8e"), ("B", "#6ba8ff"))

    def __init__(self, parent, on_change_callback, length=220):
        super().__init__(parent, bg="#25252b")
        self.on_change = on_change_callback
        self._suspend_events = False

        self.vars = {}      # channel -> tk.IntVar (slider value)
        self.entries = {}   # channel -> tk.Entry (numeric text)
        self.scales = {}    # channel -> tk.Scale

        for label_text, color in self.CHANNELS:
            row = tk.Frame(self, bg="#25252b")
            row.pack(fill=tk.X, pady=(4, 0))

            top = tk.Frame(row, bg="#25252b")
            top.pack(fill=tk.X)

            tk.Label(
                top, text=label_text, font=("Segoe UI", 9, "bold"),
                bg="#25252b", fg=color, width=2, anchor="w"
            ).pack(side=tk.LEFT)

            entry = tk.Entry(
                top, width=4, font=("Consolas", 9), bg="#1e1e24", fg="#ffffff",
                insertbackground="white", relief=tk.FLAT, justify="right"
            )
            entry.insert(0, "0")
            entry.pack(side=tk.RIGHT)
            entry.bind("<Return>", lambda e, ch=label_text: self._on_entry_apply(ch))
            entry.bind("<FocusOut>", lambda e, ch=label_text: self._on_entry_apply(ch))
            self.entries[label_text] = entry

            var = tk.IntVar(value=0)
            scale = tk.Scale(
                row, from_=0, to=255, orient=tk.HORIZONTAL, variable=var,
                bg="#25252b", fg="#ffffff", troughcolor="#1e1e24",
                highlightthickness=0, showvalue=False, length=length,
                command=lambda val, ch=label_text: self._on_scale_change(ch, val)
            )
            scale.pack(fill=tk.X, pady=(0, 2))

            self.vars[label_text] = var
            self.scales[label_text] = scale

    def _on_scale_change(self, channel, value):
        if self._suspend_events:
            return
        value = int(float(value))
        entry = self.entries[channel]
        entry.delete(0, tk.END)
        entry.insert(0, str(value))
        self._fire_change()

    def _on_entry_apply(self, channel):
        entry = self.entries[channel]
        text = entry.get().strip()
        try:
            value = int(text)
        except ValueError:
            value = self.vars[channel].get()
        value = max(0, min(255, value))

        entry.delete(0, tk.END)
        entry.insert(0, str(value))

        self._suspend_events = True
        self.vars[channel].set(value)
        self._suspend_events = False

        self._fire_change()

    def _fire_change(self):
        if self.on_change:
            self.on_change(*self.get_rgb())

    def get_rgb(self):
        return (self.vars["R"].get(), self.vars["G"].get(), self.vars["B"].get())

    def set_rgb(self, r, g, b):
        """Обновляет слайдеры и поля без вызова callback изменения."""
        self._suspend_events = True
        for channel, value in zip(("R", "G", "B"), (r, g, b)):
            value = max(0, min(255, int(value)))
            self.vars[channel].set(value)
            entry = self.entries[channel]
            entry.delete(0, tk.END)
            entry.insert(0, str(value))
        self._suspend_events = False


def rgb_to_oklab(r, g, b):
    """Convert sRGB (0..255) to OKLab."""
    r, g, b = [x / 255.0 for x in (r, g, b)]

    def to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = to_linear(r), to_linear(g), to_linear(b)

    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = math.copysign(abs(l) ** (1.0 / 3.0), l)
    m_ = math.copysign(abs(m) ** (1.0 / 3.0), m)
    s_ = math.copysign(abs(s) ** (1.0 / 3.0), s)

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(L, a, b):
    """Convert OKLab to sRGB (0..255)."""
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3

    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def to_srgb(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055

    return tuple(int(round(to_srgb(c) * 255)) for c in (r, g, b))


def interpolate_rgb(c1, c2, t):
    return tuple(int(round(a + t * (b - a))) for a, b in zip(c1, c2))


def interpolate_hsv(c1, c2, t):
    """HSV interpolation with shortest Hue path."""
    h1, s1, v1 = colorsys.rgb_to_hsv(*(x / 255.0 for x in c1))
    h2, s2, v2 = colorsys.rgb_to_hsv(*(x / 255.0 for x in c2))

    if s1 < 1e-6 and s2 >= 1e-6:
        h1 = h2
    elif s2 < 1e-6 and s1 >= 1e-6:
        h2 = h1

    dh = h2 - h1
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0

    h = (h1 + t * dh) % 1.0
    s = s1 + t * (s2 - s1)
    v = v1 + t * (v2 - v1)

    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return tuple(int(round(x * 255)) for x in (r, g, b))


def interpolate_oklab(c1, c2, t):
    lab1 = rgb_to_oklab(*c1)
    lab2 = rgb_to_oklab(*c2)
    lab = tuple(a + t * (b - a) for a, b in zip(lab1, lab2))
    return oklab_to_rgb(*lab)


def interpolate_gradient_color(c1, c2, t, method):
    if method in ("HSV — насыщенный", "HSV — Saturated"):
        return interpolate_hsv(c1, c2, t)
    if method in ("OKLab — естественный", "OKLab — Natural"):
        return interpolate_oklab(c1, c2, t)
    return interpolate_rgb(c1, c2, t)


LANG = {
    "ru": {
        "title": "Galaxy 70 RGB Customizer v1.2",
        "import_xml": "Импорт XML",
        "export_xml": "Экспорт XML",
        "save_project": "Сохранить проект",
        "open_project": "Открыть проект",
        "profile_not_loaded": "Профиль: не загружен",
        "selection_hint": "",
        "selected": "{n}",
        "loaded_keys": "{n}",
        "project_saved_short": "Проект сохранён: {name}",
        "project_opened_short": "{name} | {n}",
        "manual_tab": "Ручной цвет",
        "gradient_tab": "Градиент",
        "cc_tab": "Цветокоррекция",
        "color_palette": "Палитра цвета",
        "ok": "ОК",
        "paint_selected": "Закрасить выделенные",
        "reset_manual": "Сбросить ручные цвета",
        "enable_gradient": "Включить градиент",
        "gradient_mode": "Режим градиента:",
        "horizontal": "Горизонтально",
        "vertical": "Вертикально",
        "radial": "Радиально",
        "blend_method": "Метод смешивания:",
        "rgb_classic": "RGB — классический",
        "hsv_saturated": "HSV — насыщенный",
        "oklab_natural": "OKLab — естественный",
        "gradient_contrast": "Контраст градиента:",
        "invert_gradient": "Инвертировать направление",
        "start": "Начало:",
        "end": "Конец:",
        "enable_hsv": "Включить фильтр HSV",
        "hue": "Оттенок:",
        "saturation": "Насыщенность:",
        "brightness": "Яркость:",
        "reset_filters": "Сбросить фильтры",
        "error": "Ошибка",
        "warning": "Предупреждение",
        "success": "Успех",
        "invalid_hex": "Неверный формат HEX (ожидается #RRGGBB)",
        "project_without_xml": "Проект без XML",
        "xml_not_imported": "XML-профиль ещё не импортирован.\n\nСохранить проект только с текущими настройками?",
        "project_file_type": "Galaxy 70 Project",
        "all_files": "Все файлы",
        "project_filename": "Keyboard_Project.eglx",
        "project_saved": "Проект сохранён:\n{path}\n\nВсе параметры, цвета, выделение и фильтры сохранены.",
        "save_project_error": "Не удалось сохранить проект:\n{error}",
        "not_project": "Это не файл проекта Galaxy 70 Editor.",
        "unsupported_version": "Неподдерживаемая версия проекта: {version}",
        "open_project_error": "Не удалось открыть проект:\n{error}",
        "xml_unknown": "Неизвестно",
        "xml_read_error": "Не удалось прочитать файл:\n{error}",
        "import_first": "Сначала импортируйте XML-файл!",
        "xml_saved": "Конфигурация сохранена:\n{path}",
        "xml_saved_short": "Конфигурация сохранена: {path}",
        "xml_export_error": "Не удалось экспортировать файл:\n{error}",
        "custom_profile": "Custom Light",
        "profile": "Профиль: {name}",
        "apply_rgb": "Apply RGB",
        "apply_rgb_sending": "Отправка RGB на клавиатуру…",
        "apply_rgb_success": "Подсветка применена к клавиатуре.",
        "apply_rgb_error": "Не удалось применить подсветку:\n{error}",
        "presets_tab": "Пресеты",
        "save_preset": "Сохранить пресет",
        "preset_name_title": "Новый пресет",
        "preset_name_prompt": "Введите название пресета:",
        "preset_empty_name": "Название пресета не может быть пустым.",
        "preset_exists_overwrite": "Пресет с названием «{name}» уже существует.\nПерезаписать его?",
        "preset_saved": "Пресет «{name}» сохранён.",
        "preset_save_error": "Не удалось сохранить пресет:\n{error}",
        "preset_apply_error": "Не удалось применить пресет:\n{error}",
        "preset_delete_confirm": "Удалить пресет «{name}»?",
        "preset_delete_error": "Не удалось удалить пресет:\n{error}",
        "no_presets": "Пока нет сохранённых пресетов",
        "preset_applied": "Пресет «{name}» применён.",
        "settings_title": "Настройки",
        "setting_run_at_startup": "Запускать при включении компьютера",
        "setting_start_minimized": "Запускать свёрнутой в трей",
        "setting_minimize_on_close": "При закрытии сворачивать в трей",
        "startup_unsupported": "Автозапуск поддерживается только в Windows-сборке.",
        "startup_error": "Не удалось изменить автозапуск:\n{error}",
        "tray_unavailable": "Для работы с системным треем не хватает библиотек.\nУстановите их командой: pip install pystray pillow",
        "tray_libs_missing_note": "Для сворачивания в трей нужны библиотеки pystray и Pillow (pip install pystray pillow).",
        "close": "Закрыть",
        "hotkeys_section_title": "Горячие клавиши переключения пресетов",
        "hotkey_next_label": "Пресет вперёд:",
        "hotkey_prev_label": "Пресет назад:",
        "hotkey_record": "Записать",
        "hotkey_not_set": "Не задано",
        "hotkey_press_now": "Нажмите клавиши…",
        "hotkey_note": "Fn на этой клавиатуре не видна Windows — комбинации с Fn (например Fn+=) неотличимы от обычного нажатия клавиши. Записывайте сочетания с Ctrl/Alt/Shift/Win — они распознаются корректно.",
        "advanced_collapsed": "Дополнительно  ▶",
        "advanced_expanded": "Дополнительно  ▼",
    },
    "en": {
        "title": "Galaxy 70 RGB Customizer v1.2",
        "import_xml": "Import XML",
        "export_xml": "Export XML",
        "save_project": "Save Project",
        "open_project": "Open Project",
        "profile_not_loaded": "Profile: not loaded",
        "selection_hint": "",
        "selected": "{n}",
        "loaded_keys": "{n}",
        "project_saved_short": "Project saved: {name}",
        "project_opened_short": "{name} | {n}",
        "manual_tab": "Manual Color",
        "gradient_tab": "Gradient",
        "cc_tab": "Color Correction",
        "color_palette": "Color Palette",
        "ok": "OK",
        "paint_selected": "Color Selected Keys",
        "reset_manual": "Reset Manual Colors",
        "enable_gradient": "Enable Gradient",
        "gradient_mode": "Gradient Mode:",
        "horizontal": "Horizontal",
        "vertical": "Vertical",
        "radial": "Radial",
        "blend_method": "Blend Method:",
        "rgb_classic": "RGB — Classic",
        "hsv_saturated": "HSV — Saturated",
        "oklab_natural": "OKLab — Natural",
        "gradient_contrast": "Gradient Contrast:",
        "invert_gradient": "Invert Direction",
        "start": "Start:",
        "end": "End:",
        "enable_hsv": "Enable HSV Filter",
        "hue": "Hue:",
        "saturation": "Saturation:",
        "brightness": "Brightness:",
        "reset_filters": "Reset Filters",
        "error": "Error",
        "warning": "Warning",
        "success": "Success",
        "invalid_hex": "Invalid HEX format (expected #RRGGBB)",
        "project_without_xml": "Project Without XML",
        "xml_not_imported": "XML profile has not been imported yet.\n\nSave the project with the current settings only?",
        "project_file_type": "Galaxy 70 Project",
        "all_files": "All files",
        "project_filename": "Keyboard_Project.eglx",
        "project_saved": "Project saved:\n{path}\n\nAll parameters, colors, selection and filters were saved.",
        "save_project_error": "Could not save project:\n{error}",
        "not_project": "This is not a Galaxy 70 Editor project file.",
        "unsupported_version": "Unsupported project version: {version}",
        "open_project_error": "Could not open project:\n{error}",
        "xml_unknown": "Unknown",
        "xml_read_error": "Could not read file:\n{error}",
        "import_first": "Import an XML file first!",
        "xml_saved": "Configuration saved:\n{path}",
        "xml_saved_short": "Configuration saved: {path}",
        "xml_export_error": "Could not export file:\n{error}",
        "custom_profile": "Custom Light",
        "profile": "Profile: {name}",
        "apply_rgb": "Apply RGB",
        "apply_rgb_sending": "Sending RGB to keyboard…",
        "apply_rgb_success": "RGB lighting applied to the keyboard.",
        "apply_rgb_error": "Could not apply RGB lighting:\n{error}",
        "presets_tab": "Presets",
        "save_preset": "Save Preset",
        "preset_name_title": "New Preset",
        "preset_name_prompt": "Enter preset name:",
        "preset_empty_name": "Preset name cannot be empty.",
        "preset_exists_overwrite": "A preset named \"{name}\" already exists.\nOverwrite it?",
        "preset_saved": "Preset \"{name}\" saved.",
        "preset_save_error": "Could not save preset:\n{error}",
        "preset_apply_error": "Could not apply preset:\n{error}",
        "preset_delete_confirm": "Delete preset \"{name}\"?",
        "preset_delete_error": "Could not delete preset:\n{error}",
        "no_presets": "No presets saved yet",
        "preset_applied": "Preset \"{name}\" applied.",
        "settings_title": "Settings",
        "setting_run_at_startup": "Run at Windows startup",
        "setting_start_minimized": "Start minimized to tray",
        "setting_minimize_on_close": "Minimize to tray on close",
        "startup_unsupported": "Run-at-startup is only supported in the Windows build.",
        "startup_error": "Could not update startup setting:\n{error}",
        "tray_unavailable": "The system tray libraries are missing.\nInstall them with: pip install pystray pillow",
        "tray_libs_missing_note": "Minimizing to tray requires the pystray and Pillow libraries (pip install pystray pillow).",
        "close": "Close",
        "hotkeys_section_title": "Preset switching hotkeys",
        "hotkey_next_label": "Next preset:",
        "hotkey_prev_label": "Previous preset:",
        "hotkey_record": "Record",
        "hotkey_not_set": "Not set",
        "hotkey_press_now": "Press keys…",
        "hotkey_note": "Fn on this keyboard is invisible to Windows — Fn combos (e.g. Fn+=) are indistinguishable from the plain key. Record combos with Ctrl/Alt/Shift/Win instead — those are recognized correctly.",
        "advanced_collapsed": "Advanced  ▶",
        "advanced_expanded": "Advanced  ▼",
    }
}

GRAD_MODE_KEYS = {"horizontal": ("Горизонтально", "Horizontal"), "vertical": ("Вертикально", "Vertical"), "radial": ("Радиально", "Radial")}
GRAD_METHOD_KEYS = {"rgb": ("RGB — классический", "RGB — Classic"), "hsv": ("HSV — насыщенный", "HSV — Saturated"), "oklab": ("OKLab — естественный", "OKLab — Natural")}


class KeyboardVisualizerApp:
    def __init__(self, root):
        self.root = root
        self.lang = "en"
        self.root.title(LANG[self.lang]["title"])
        self.root.configure(bg="#1e1e24")
        self.root.geometry("1220x625")
        self.root.resizable(True, True)

        # Предварительная инициализация переменных состояний
        self.grad_active_var = tk.BooleanVar(value=False)
        self.grad_invert_var = tk.BooleanVar(value=False)
        self.grad_contrast = 0
        self.cc_active_var = tk.BooleanVar(value=False)

        self.base_colors = {}       # {key_code: (hex_val, (r,g,b), raw_val)}
        self.manual_overrides = {} # {key_code: (hex_val, (r,g,b), raw_val)}
        self.selected_keys = set()
        self.base_selected_keys = set()
        self.xml_tree = None
        self.profile_name = None

        # Данные градиента
        self.grad_start_rgb = (255, 255, 255)
        self.grad_end_rgb = (0, 0, 0)
        self.active_grad_target = "start" # "start" или "end"
        self.active_tab = "manual"
        self.current_project_path = None

        self.drag_start = None
        self.selection_rect_id = None

        # Панель пресетов
        self.presets_panel_visible = False
        self.preset_widgets = []  # список Frame-строк с кнопками пресетов (для очистки)

        # Настройки приложения (автозапуск / трей)
        self.settings = load_app_settings()
        self.tray_icon = None
        self._settings_win = None

        # Глобальные хоткеи переключения пресетов
        self._last_applied_preset_path = None
        self._hotkey_capture_target = None  # "next" | "prev" | None
        self._hotkey_capture_widgets = None  # (label_widget, record_button) активной записи
        self.hotkey_manager = HotkeyManager(self._on_global_key_event)

        self.setup_ui()

        # Горячие клавиши проекта
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-o>", lambda e: self.open_project())

        # Закрытие окна: либо сворачиваем в трей, либо выходим — в зависимости от настройки.
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_request)

        # Хук клавиатуры должен работать и когда окно свёрнуто/скрыто в трей,
        # поэтому запускаем его сразу при старте, а не только пока открыт диалог настроек.
        self.hotkey_manager.start()

        # Если включено "Запускать свёрнутой в трей" — сразу прячем окно и
        # показываем иконку в трее вместо обычного показа окна.
        if self.settings.get("start_minimized") and TRAY_LIBS_AVAILABLE:
            self.root.after(0, self._start_minimized_to_tray)

    def tr(self, key, **kwargs):
        text = LANG[self.lang][key]
        return text.format(**kwargs) if kwargs else text

    def create_default_xml_tree(self):
        """Создает дефолтное XML-дерево с правильным корневым тегом userlight."""
        root = ET.Element("userlight")
        ET.SubElement(root, "lightinfo", name=self.profile_name or self.tr("custom_profile"))
        keyinfo = ET.SubElement(root, "keyinfo")
        for code in KEYBOARD_LAYOUT.keys():
            ET.SubElement(keyinfo, "item", key_code=str(code), key_rgb="0")
        return ET.ElementTree(root)

    def set_language(self, lang):
        if lang not in LANG or lang == self.lang:
            return

        grad_mode_key = self.grad_mode_key() if hasattr(self, "combo_grad_mode") else "horizontal"
        grad_method_key = self.grad_method_key() if hasattr(self, "combo_grad_method") else "hsv"

        self.lang = lang

        self.btn_ru.config(
            bg="#25252b" if self.lang == "ru" else "#1e1e24",
            fg="#ffffff" if self.lang == "ru" else "#888888"
        )
        self.btn_en.config(
            bg="#25252b" if self.lang == "en" else "#1e1e24",
            fg="#ffffff" if self.lang == "en" else "#888888"
        )

        self.root.title(self.tr("title"))

        text_to_key = {}
        for key in LANG["ru"]:
            ru_text = LANG["ru"][key]
            en_text = LANG["en"][key]
            if "{" not in ru_text and "{" not in en_text:
                text_to_key[ru_text] = key
                text_to_key[en_text] = key

        def update_widget_text(widget):
            try:
                current = widget.cget("text")
            except (tk.TclError, TypeError):
                current = None

            if current in text_to_key:
                key = text_to_key[current]
                try:
                    widget.config(text=LANG[lang][key])
                except tk.TclError:
                    pass

            try:
                for child in widget.winfo_children():
                    update_widget_text(child)
            except tk.TclError:
                pass

        update_widget_text(self.root)

        self.combo_grad_mode["values"] = [
            self.grad_mode_display("horizontal"),
            self.grad_mode_display("vertical"),
            self.grad_mode_display("radial"),
        ]
        self.combo_grad_mode.set(self.grad_mode_display(grad_mode_key))

        self.combo_grad_method["values"] = [
            self.grad_method_display("rgb"),
            self.grad_method_display("hsv"),
            self.grad_method_display("oklab"),
        ]
        self.combo_grad_method.set(self.grad_method_display(grad_method_key))

        if getattr(self, "profile_name", None):
            self.lbl_profile.config(text=self.tr("profile", name=self.profile_name))

        self.lbl_info.config(text=str(len(self.selected_keys)))
        self.render_keyboard()

    def grad_mode_key(self, display_value=None):
        value = self.combo_grad_mode.get() if display_value is None else display_value
        for key, values in GRAD_MODE_KEYS.items():
            if value in values:
                return key
        return "horizontal"

    def grad_method_key(self, display_value=None):
        value = self.combo_grad_method.get() if display_value is None else display_value
        for key, values in GRAD_METHOD_KEYS.items():
            if value in values:
                return key
        return "hsv"

    def grad_mode_display(self, key):
        return GRAD_MODE_KEYS.get(key, GRAD_MODE_KEYS["horizontal"])[0 if self.lang == "ru" else 1]

    def grad_method_display(self, key):
        return GRAD_METHOD_KEYS.get(key, GRAD_METHOD_KEYS["hsv"])[0 if self.lang == "ru" else 1]

    def setup_ui(self):
        top_frame = tk.Frame(self.root, bg="#1e1e24")
        top_frame.pack(fill=tk.X, padx=20, pady=10)

        self.btn_load = tk.Button(
            top_frame, text=self.tr("import_xml"), command=self.load_xml,
            font=("Segoe UI", 10, "bold"), bg="#007acc", fg="white",
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        self.btn_load.pack(side=tk.LEFT)

        self.btn_export = tk.Button(
            top_frame, text=self.tr("export_xml"), command=self.export_xml,
            font=("Segoe UI", 10, "bold"), bg="#28a745", fg="white",
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        self.btn_export.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_save_project = tk.Button(
            top_frame, text=self.tr("save_project"), command=self.save_project,
            font=("Segoe UI", 10, "bold"), bg="#6f42c1", fg="white",
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        self.btn_save_project.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_open_project = tk.Button(
            top_frame, text=self.tr("open_project"), command=self.open_project,
            font=("Segoe UI", 10, "bold"), bg="#495057", fg="white",
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        self.btn_open_project.pack(side=tk.LEFT, padx=(8, 0))

        # Кнопка настроек — крайняя правая кнопка окна (правее "Пресеты").
        self.btn_settings = tk.Button(
            top_frame, text="⚙", command=self.open_settings_dialog,
            font=("Segoe UI Symbol", 13, "bold"), bg="#343a40", fg="white",
            relief=tk.FLAT, width=2, cursor="hand2"
        )
        self.btn_settings.pack(side=tk.RIGHT, padx=(8, 0))

        # Кнопка переключения панели пресетов — сразу слева от кнопки настроек.
        self.btn_toggle_presets = tk.Button(
            top_frame, text=self.tr("presets_tab"), command=self.toggle_presets_panel,
            font=("Segoe UI", 10, "bold"), bg="#343a40", fg="white",
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        self.btn_toggle_presets.pack(side=tk.RIGHT)

        self.lbl_profile = tk.Label(
            top_frame, text=self.tr("profile_not_loaded"),
            font=("Segoe UI", 11), bg="#1e1e24", fg="#cccccc", padx=15
        )
        self.lbl_profile.pack(side=tk.LEFT)

        self.lbl_info = tk.Label(
            top_frame, text="0",
            font=("Segoe UI", 10), bg="#1e1e24", fg="#888888"
        )
        self.lbl_info.pack(side=tk.RIGHT)

        self.lang_frame = tk.Frame(top_frame, bg="#1e1e24")
        self.lang_frame.pack(side=tk.RIGHT, padx=(10, 0))
        self.btn_ru = tk.Button(
            self.lang_frame, text="RU", command=lambda: self.set_language("ru"),
            font=("Segoe UI", 8, "bold"), relief=tk.FLAT, padx=5, pady=2,
            cursor="hand2", bg="#25252b" if self.lang == "ru" else "#1e1e24",
            fg="#ffffff" if self.lang == "ru" else "#888888"
        )
        self.btn_ru.pack(side=tk.LEFT, padx=(0, 2))
        self.btn_en = tk.Button(
            self.lang_frame, text="EN", command=lambda: self.set_language("en"),
            font=("Segoe UI", 8, "bold"), relief=tk.FLAT, padx=5, pady=2,
            cursor="hand2", bg="#25252b" if self.lang == "en" else "#1e1e24",
            fg="#ffffff" if self.lang == "en" else "#888888"
        )
        self.btn_en.pack(side=tk.LEFT)

        main_container = tk.Frame(self.root, bg="#1e1e24")
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        self.main_container = main_container

        self.keyboard_area = tk.Frame(main_container, bg="#1e1e24")
        self.keyboard_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            self.keyboard_area, width=880, height=330,
            bg="#121214", highlightthickness=1, highlightbackground="#333338"
        )
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.btn_apply_rgb = tk.Button(
            self.keyboard_area,
            text=self.tr("apply_rgb"),
            command=self.apply_rgb_to_keyboard,
            font=("Segoe UI", 10, "bold"),
            bg="#28a745",
            fg="white",
            activebackground="#218838",
            activeforeground="white",
            relief=tk.FLAT,
            pady=7,
            cursor="hand2"
        )
        self.btn_apply_rgb.pack(fill=tk.X, pady=(10, 0))

        self.key_size = 45
        self.gap = 5
        self.margin = 15

        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        self.side_panel = tk.Frame(main_container, bg="#25252b", width=280, highlightthickness=1, highlightbackground="#333338")
        self.side_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(15, 0))
        self.side_panel.pack_propagate(False)

        tab_bar = tk.Frame(self.side_panel, bg="#1e1e24")
        tab_bar.pack(fill=tk.X)
        tab_bar.columnconfigure((0, 1, 2), weight=1)

        self.btn_tab_grad = tk.Button(
            tab_bar, text=self.tr("gradient_tab"), command=lambda: self.switch_tab("grad"),
            font=("Segoe UI", 8, "bold"), bg="#25252b", fg="#ffffff", relief=tk.FLAT, pady=6
        )
        self.btn_tab_grad.grid(row=0, column=0, sticky="ew")

        self.btn_tab_manual = tk.Button(
            tab_bar, text=self.tr("manual_tab"), command=lambda: self.switch_tab("manual"),
            font=("Segoe UI", 8, "bold"), bg="#1e1e24", fg="#888888", relief=tk.FLAT, pady=6
        )
        self.btn_tab_manual.grid(row=0, column=1, sticky="ew")

        self.btn_tab_cc = tk.Button(
            tab_bar, text=self.tr("cc_tab"), command=lambda: self.switch_tab("cc"),
            font=("Segoe UI", 8, "bold"), bg="#1e1e24", fg="#888888", relief=tk.FLAT, pady=6
        )
        self.btn_tab_cc.grid(row=0, column=2, sticky="ew")

        self.frame_manual = tk.Frame(self.side_panel, bg="#25252b")
        self.frame_grad = tk.Frame(self.side_panel, bg="#25252b")
        self.frame_cc = tk.Frame(self.side_panel, bg="#25252b")

        self.build_manual_tab()
        self.build_grad_tab()
        self.build_cc_tab()

        self.build_presets_panel()

        self.switch_tab(getattr(self, "active_tab", "manual"))
        self.render_keyboard()

    def build_presets_panel(self):
        """Создаёт (но не показывает) выдвижную панель пресетов справа от side_panel."""
        self.PRESETS_PANEL_WIDTH = 240
        self.PRESETS_PANEL_PADX = 15

        self.presets_panel = tk.Frame(
            self.main_container, bg="#25252b", width=self.PRESETS_PANEL_WIDTH,
            highlightthickness=1, highlightbackground="#333338"
        )
        self.presets_panel.pack_propagate(False)

        header = tk.Frame(self.presets_panel, bg="#1e1e24")
        header.pack(fill=tk.X)
        self.lbl_presets_title = tk.Label(
            header, text=self.tr("presets_tab"), font=("Segoe UI", 9, "bold"),
            bg="#1e1e24", fg="#ffffff"
        )
        self.lbl_presets_title.pack(side=tk.LEFT, padx=10, pady=6)

        self.btn_save_preset = tk.Button(
            self.presets_panel, text=self.tr("save_preset"), command=self.save_preset,
            font=("Segoe UI", 9, "bold"), bg="#6f42c1", fg="white",
            relief=tk.FLAT, pady=6, cursor="hand2"
        )
        self.btn_save_preset.pack(fill=tk.X, padx=10, pady=(10, 6))

        list_container = tk.Frame(self.presets_panel, bg="#25252b")
        list_container.pack(fill=tk.BOTH, expand=True, padx=(10, 0), pady=(0, 10))

        self.presets_canvas = tk.Canvas(list_container, bg="#25252b", highlightthickness=0)
        presets_scrollbar = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.presets_canvas.yview)
        self.presets_list_frame = tk.Frame(self.presets_canvas, bg="#25252b")

        self.presets_list_frame.bind(
            "<Configure>",
            lambda e: self.presets_canvas.configure(scrollregion=self.presets_canvas.bbox("all"))
        )
        self._presets_canvas_window = self.presets_canvas.create_window((0, 0), window=self.presets_list_frame, anchor="nw")
        self.presets_canvas.configure(yscrollcommand=presets_scrollbar.set)
        self.presets_canvas.bind(
            "<Configure>",
            lambda e: self.presets_canvas.itemconfig(self._presets_canvas_window, width=e.width)
        )

        self.presets_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        presets_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10))

        def _on_mousewheel(event):
            delta = int(-1 * (event.delta / 120)) if event.delta else (1 if event.num == 5 else -1)
            self.presets_canvas.yview_scroll(delta, "units")

        def _bind_wheel(_e):
            self.presets_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            self.presets_canvas.bind_all("<Button-4>", _on_mousewheel)
            self.presets_canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_wheel(_e):
            self.presets_canvas.unbind_all("<MouseWheel>")
            self.presets_canvas.unbind_all("<Button-4>")
            self.presets_canvas.unbind_all("<Button-5>")

        self.presets_canvas.bind("<Enter>", _bind_wheel)
        self.presets_canvas.bind("<Leave>", _unbind_wheel)

    def switch_tab(self, tab_name):
        self.active_tab = tab_name
        self.frame_manual.pack_forget()
        self.frame_grad.pack_forget()
        self.frame_cc.pack_forget()

        self.btn_tab_manual.config(bg="#1e1e24", fg="#888888")
        self.btn_tab_grad.config(bg="#1e1e24", fg="#888888")
        self.btn_tab_cc.config(bg="#1e1e24", fg="#888888")

        if tab_name == "manual":
            self.frame_manual.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
            self.btn_tab_manual.config(bg="#25252b", fg="#ffffff")
        elif tab_name == "grad":
            self.frame_grad.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
            self.btn_tab_grad.config(bg="#25252b", fg="#ffffff")
        else:
            self.frame_cc.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
            self.btn_tab_cc.config(bg="#25252b", fg="#ffffff")

    RGB_SPOILER_EXTRA_HEIGHT = 150

    def _build_rgb_spoiler(self, parent, on_change_callback):
        """Строит сворачиваемый блок "Дополнительно >" с RGB-слайдерами внутри.
        По умолчанию свёрнут (чтобы не занимать место); при раскрытии окно
        программы увеличивается по высоте на RGB_SPOILER_EXTRA_HEIGHT, чтобы
        слайдеры не обрезались и не приходилось растягивать окно вручную —
        при сворачивании окно уменьшается обратно."""
        state = {"expanded": False}

        header = tk.Frame(parent, bg="#25252b")
        header.pack(fill=tk.X, pady=(2, 0))

        btn_toggle = tk.Button(
            header, text=self.tr("advanced_collapsed"), font=("Segoe UI", 9),
            bg="#25252b", fg="#8a8a92", relief=tk.FLAT, anchor="w", padx=0,
            cursor="hand2", bd=0, activebackground="#25252b", activeforeground="#cccccc"
        )
        btn_toggle.pack(side=tk.LEFT)

        content = tk.Frame(parent, bg="#25252b")
        # Не паковится сразу — блок стартует свёрнутым.

        sliders = RGBSliderPanel(content, on_change_callback)
        sliders.pack(anchor="w", fill=tk.X, pady=(4, 4))

        def toggle():
            if state["expanded"]:
                content.pack_forget()
                state["expanded"] = False
                btn_toggle.config(text=self.tr("advanced_collapsed"))
                self._resize_window_by(delta_h=-self.RGB_SPOILER_EXTRA_HEIGHT)
            else:
                content.pack(fill=tk.X, after=header)
                state["expanded"] = True
                btn_toggle.config(text=self.tr("advanced_expanded"))
                self._resize_window_by(delta_h=self.RGB_SPOILER_EXTRA_HEIGHT)

        btn_toggle.config(command=toggle)

        return sliders

    def build_manual_tab(self):
        lbl_title = tk.Label(self.frame_manual, text=self.tr("color_palette"), font=("Segoe UI", 11, "bold"), bg="#25252b", fg="#ffffff")
        lbl_title.pack(anchor="w", pady=(0, 5))

        self.picker = PhotoshopColorPicker(self.frame_manual, self.on_picker_color_change)
        self.picker.pack(anchor="w", pady=5)

        self.rgb_sliders = self._build_rgb_spoiler(self.frame_manual, self.on_rgb_sliders_change)
        # Инициализируем слайдеры текущим цветом палитры (по умолчанию красный).
        self.rgb_sliders.set_rgb(*self.picker.get_rgb())

        hex_frame = tk.Frame(self.frame_manual, bg="#25252b")
        hex_frame.pack(fill=tk.X, pady=10)

        tk.Label(hex_frame, text="HEX:", font=("Segoe UI", 10, "bold"), bg="#25252b", fg="#cccccc").pack(side=tk.LEFT, padx=(0, 5))
        self.entry_hex = tk.Entry(hex_frame, font=("Consolas", 10), bg="#1e1e24", fg="#ffffff", insertbackground="white", relief=tk.FLAT, width=10)
        self.entry_hex.insert(0, "#FF0000")
        self.entry_hex.pack(side=tk.LEFT, padx=5)

        btn_apply_hex = tk.Button(
            hex_frame, text=self.tr("ok"), command=self.on_hex_entry_apply,
            font=("Segoe UI", 8, "bold"), bg="#3a3a42", fg="white", relief=tk.FLAT, padx=6
        )
        btn_apply_hex.pack(side=tk.LEFT)

        self.btn_apply_color = tk.Button(
            self.frame_manual, text=self.tr("paint_selected"), command=self.apply_color_to_selection,
            font=("Segoe UI", 9, "bold"), bg="#007acc", fg="white", relief=tk.FLAT, pady=6, cursor="hand2"
        )
        self.btn_apply_color.pack(fill=tk.X, pady=(10, 5))

        btn_reset_manual = tk.Button(
            self.frame_manual, text=self.tr("reset_manual"), command=self.reset_manual_colors,
            font=("Segoe UI", 8), bg="#3a3a42", fg="#cccccc", relief=tk.FLAT, pady=3
        )
        btn_reset_manual.pack(fill=tk.X, pady=2)

    def build_grad_tab(self):
        self.chk_grad = tk.Checkbutton(
            self.frame_grad, text=self.tr("enable_gradient"), variable=self.grad_active_var,
            command=self.toggle_grad_state, font=("Segoe UI", 10, "bold"),
            bg="#25252b", fg="#007acc", selectcolor="#1e1e24", activebackground="#25252b", cursor="hand2"
        )
        self.chk_grad.pack(anchor="w", pady=(0, 8))

        tk.Label(self.frame_grad, text=self.tr("gradient_mode"), font=("Segoe UI", 9), bg="#25252b", fg="#cccccc").pack(anchor="w")
        self.combo_grad_mode = ttk.Combobox(
            self.frame_grad, values=[self.tr("horizontal"), self.tr("vertical"), self.tr("radial")], state="readonly", font=("Segoe UI", 9)
        )
        self.combo_grad_mode.set(self.tr("horizontal"))
        self.combo_grad_mode.pack(fill=tk.X, pady=(2, 8))
        self.combo_grad_mode.bind("<<ComboboxSelected>>", lambda e: self.render_keyboard())

        tk.Label(
            self.frame_grad,
            text=self.tr("blend_method"),
            font=("Segoe UI", 9),
            bg="#25252b",
            fg="#cccccc"
        ).pack(anchor="w")

        self.combo_grad_method = ttk.Combobox(
            self.frame_grad,
            values=[
                self.tr("rgb_classic"),
                self.tr("hsv_saturated"),
                self.tr("oklab_natural")
            ],
            state="readonly",
            font=("Segoe UI", 9)
        )
        self.combo_grad_method.set(self.tr("hsv_saturated"))
        self.combo_grad_method.pack(fill=tk.X, pady=(2, 8))
        self.combo_grad_method.bind("<<ComboboxSelected>>", lambda e: self.render_keyboard())

        tk.Label(
            self.frame_grad,
            text=self.tr("gradient_contrast"),
            font=("Segoe UI", 9),
            bg="#25252b",
            fg="#cccccc"
        ).pack(anchor="w")

        self.scale_grad_contrast = tk.Scale(
            self.frame_grad,
            from_=-100,
            to=100,
            orient=tk.HORIZONTAL,
            command=self.on_gradient_contrast_change,
            bg="#25252b",
            fg="#ffffff",
            troughcolor="#1e1e24",
            highlightthickness=0,
            length=220,
            showvalue=True
        )
        self.scale_grad_contrast.set(0)
        self.scale_grad_contrast.pack(anchor="w", pady=(0, 8))

        self.chk_grad_inv = tk.Checkbutton(
            self.frame_grad, text=self.tr("invert_gradient"), variable=self.grad_invert_var,
            command=self.render_keyboard, font=("Segoe UI", 9),
            bg="#25252b", fg="#cccccc", selectcolor="#1e1e24", activebackground="#25252b", cursor="hand2"
        )
        self.chk_grad_inv.pack(anchor="w", pady=(0, 10))

        tk.Frame(self.frame_grad, bg="#333338", height=1).pack(fill=tk.X, pady=(0, 8))

        colors_container = tk.Frame(self.frame_grad, bg="#25252b")
        colors_container.pack(fill=tk.X, pady=(0, 5))

        row_start = tk.Frame(colors_container, bg="#25252b")
        row_start.pack(fill=tk.X, pady=2)
        tk.Label(row_start, text=self.tr("start"), font=("Segoe UI", 9, "bold"), bg="#25252b", fg="#ffffff").pack(side=tk.LEFT)
        self.cv_grad_start = tk.Canvas(row_start, width=22, height=22, bg="#25252b", highlightthickness=0, cursor="hand2")
        self.cv_grad_start.pack(side=tk.RIGHT)
        self.cv_grad_start.bind("<Button-1>", lambda e: self.select_grad_target("start"))

        row_end = tk.Frame(colors_container, bg="#25252b")
        row_end.pack(fill=tk.X, pady=2)
        tk.Label(row_end, text=self.tr("end"), font=("Segoe UI", 9, "bold"), bg="#25252b", fg="#ffffff").pack(side=tk.LEFT)
        self.cv_grad_end = tk.Canvas(row_end, width=22, height=22, bg="#25252b", highlightthickness=0, cursor="hand2")
        self.cv_grad_end.pack(side=tk.RIGHT)
        self.cv_grad_end.bind("<Button-1>", lambda e: self.select_grad_target("end"))

        self.grad_picker = PhotoshopColorPicker(self.frame_grad, self.on_grad_picker_color_change)
        self.grad_picker.pack(anchor="w", pady=(5, 2))

        self.grad_rgb_sliders = self._build_rgb_spoiler(self.frame_grad, self.on_grad_rgb_sliders_change)
        self.grad_rgb_sliders.set_rgb(*self.grad_picker.get_rgb())

        grad_hex_frame = tk.Frame(self.frame_grad, bg="#25252b")
        grad_hex_frame.pack(fill=tk.X, pady=5)

        tk.Label(grad_hex_frame, text="HEX:", font=("Segoe UI", 9, "bold"), bg="#25252b", fg="#cccccc").pack(side=tk.LEFT, padx=(0, 5))
        self.entry_grad_hex = tk.Entry(grad_hex_frame, font=("Consolas", 9), bg="#1e1e24", fg="#ffffff", insertbackground="white", relief=tk.FLAT, width=10)
        self.entry_grad_hex.pack(side=tk.LEFT, padx=5)

        btn_grad_apply_hex = tk.Button(
            grad_hex_frame, text=self.tr("ok"), command=self.on_grad_hex_apply,
            font=("Segoe UI", 8, "bold"), bg="#3a3a42", fg="white", relief=tk.FLAT, padx=6
        )
        btn_grad_apply_hex.pack(side=tk.LEFT)

        self.update_grad_circles()
        self.toggle_grad_state()

    def build_cc_tab(self):
        self.chk_cc = tk.Checkbutton(
            self.frame_cc, text=self.tr("enable_hsv"), variable=self.cc_active_var,
            command=self.toggle_cc_state, font=("Segoe UI", 10, "bold"),
            bg="#25252b", fg="#007acc", selectcolor="#1e1e24", activebackground="#25252b", cursor="hand2"
        )
        self.chk_cc.pack(anchor="w", pady=(0, 10))

        tk.Label(self.frame_cc, text=self.tr("hue"), font=("Segoe UI", 9), bg="#25252b", fg="#cccccc").pack(anchor="w")
        self.scale_hue = tk.Scale(self.frame_cc, from_=-180, to=180, orient=tk.HORIZONTAL, command=self.on_slider_change, bg="#25252b", fg="#ffffff", troughcolor="#1e1e24", highlightthickness=0, length=220)
        self.scale_hue.set(0)
        self.scale_hue.pack(anchor="w", pady=(0, 5))

        tk.Label(self.frame_cc, text=self.tr("saturation"), font=("Segoe UI", 9), bg="#25252b", fg="#cccccc").pack(anchor="w")
        self.scale_sat = tk.Scale(self.frame_cc, from_=-100, to=100, orient=tk.HORIZONTAL, command=self.on_slider_change, bg="#25252b", fg="#ffffff", troughcolor="#1e1e24", highlightthickness=0, length=220)
        self.scale_sat.set(0)
        self.scale_sat.pack(anchor="w", pady=(0, 5))

        tk.Label(self.frame_cc, text=self.tr("brightness"), font=("Segoe UI", 9), bg="#25252b", fg="#cccccc").pack(anchor="w")
        self.scale_val = tk.Scale(self.frame_cc, from_=-100, to=100, orient=tk.HORIZONTAL, command=self.on_slider_change, bg="#25252b", fg="#ffffff", troughcolor="#1e1e24", highlightthickness=0, length=220)
        self.scale_val.set(0)
        self.scale_val.pack(anchor="w", pady=(0, 10))

        btn_reset_cc = tk.Button(self.frame_cc, text=self.tr("reset_filters"), command=self.reset_cc_sliders, font=("Segoe UI", 8), bg="#3a3a42", fg="white", relief=tk.FLAT, pady=3)
        btn_reset_cc.pack(fill=tk.X, pady=2)

        self.toggle_cc_state()

    def on_gradient_contrast_change(self, value):
        self.grad_contrast = int(float(value))
        self.render_keyboard()

    def select_grad_target(self, target):
        self.active_grad_target = target
        self.update_grad_circles()
        rgb = self.grad_start_rgb if target == "start" else self.grad_end_rgb
        self.grad_picker.set_color_from_rgb(*rgb)
        if hasattr(self, "grad_rgb_sliders"):
            self.grad_rgb_sliders.set_rgb(*rgb)
        self.entry_grad_hex.delete(0, tk.END)
        self.entry_grad_hex.insert(0, f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")

    def update_grad_circles(self):
        self.cv_grad_start.delete("all")
        hex_s = f"#{self.grad_start_rgb[0]:02x}{self.grad_start_rgb[1]:02x}{self.grad_start_rgb[2]:02x}"
        out_s = "#007acc" if self.active_grad_target == "start" else "#555555"
        w_s = 2 if self.active_grad_target == "start" else 1
        self.cv_grad_start.create_oval(2, 2, 20, 20, fill=hex_s, outline=out_s, width=w_s)

        self.cv_grad_end.delete("all")
        hex_e = f"#{self.grad_end_rgb[0]:02x}{self.grad_end_rgb[1]:02x}{self.grad_end_rgb[2]:02x}"
        out_e = "#007acc" if self.active_grad_target == "end" else "#555555"
        w_e = 2 if self.active_grad_target == "end" else 1
        self.cv_grad_end.create_oval(2, 2, 20, 20, fill=hex_e, outline=out_e, width=w_e)

    def on_grad_picker_color_change(self, hex_code):
        r, g, b = self.grad_picker.get_rgb()
        if self.active_grad_target == "start":
            self.grad_start_rgb = (r, g, b)
        else:
            self.grad_end_rgb = (r, g, b)

        if hasattr(self, "grad_rgb_sliders"):
            self.grad_rgb_sliders.set_rgb(r, g, b)

        self.entry_grad_hex.delete(0, tk.END)
        self.entry_grad_hex.insert(0, hex_code.upper())
        self.update_grad_circles()
        if self.grad_active_var.get():
            self.render_keyboard()

    def on_grad_rgb_sliders_change(self, r, g, b):
        """Вызывается при изменении слайдеров R/G/B на вкладке градиента
        (перетаскиванием или вводом значения)."""
        self.grad_picker.set_color_from_rgb(r, g, b)
        if self.active_grad_target == "start":
            self.grad_start_rgb = (r, g, b)
        else:
            self.grad_end_rgb = (r, g, b)

        self.entry_grad_hex.delete(0, tk.END)
        self.entry_grad_hex.insert(0, self.grad_picker.get_hex().upper())
        self.update_grad_circles()
        if self.grad_active_var.get():
            self.render_keyboard()

    def on_grad_hex_apply(self):
        val = self.entry_grad_hex.get().strip()
        if not val.startswith("#"):
            val = "#" + val
        try:
            r = int(val[1:3], 16)
            g = int(val[3:5], 16)
            b = int(val[5:7], 16)
            self.grad_picker.set_color_from_rgb(r, g, b)
            if hasattr(self, "grad_rgb_sliders"):
                self.grad_rgb_sliders.set_rgb(r, g, b)
            if self.active_grad_target == "start":
                self.grad_start_rgb = (r, g, b)
            else:
                self.grad_end_rgb = (r, g, b)
            self.update_grad_circles()
            if self.grad_active_var.get():
                self.render_keyboard()
        except Exception:
            messagebox.showerror(self.tr("error"), self.tr("invalid_hex"))

    def toggle_grad_state(self):
        state = tk.NORMAL if self.grad_active_var.get() else tk.DISABLED
        self.combo_grad_mode.config(state="readonly" if self.grad_active_var.get() else tk.DISABLED)
        self.chk_grad_inv.config(state=state)
        self.select_grad_target(self.active_grad_target)
        self.render_keyboard()

    def on_canvas_press(self, event):
        self.drag_start = (event.x, event.y)
        self.base_selected_keys = set(self.selected_keys)
        self.process_selection(event)

    def on_canvas_drag(self, event):
        if self.drag_start:
            self.process_selection(event)

    def on_canvas_release(self, event):
        if not self.drag_start:
            return

        self.process_selection(event)
        self.drag_start = None

        if self.selection_rect_id:
            self.canvas.delete(self.selection_rect_id)
            self.selection_rect_id = None

        self.render_keyboard()

        if len(self.selected_keys) == 1:
            k_code = list(self.selected_keys)[0]
            col_data = self.get_key_effective_color(k_code)
            if col_data:
                hex_val, (r, g, b), _ = col_data
                self.picker.set_color_from_rgb(r, g, b)
                if hasattr(self, "rgb_sliders"):
                    self.rgb_sliders.set_rgb(r, g, b)
                self.update_hex_entry(hex_val)

        self.lbl_info.config(text=self.tr("selected", n=len(self.selected_keys)))

    def process_selection(self, event):
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y

        bx1, bx2 = min(x0, x1), max(x0, x1)
        by1, by2 = min(y0, y1), max(y0, y1)

        hit_keys = set()
        for key_code, (label, x_u, y_u, w_u) in KEYBOARD_LAYOUT.items():
            kx1 = self.margin + x_u * (self.key_size + self.gap)
            ky1 = self.margin + y_u * (self.key_size + self.gap)
            kx2 = kx1 + w_u * self.key_size + (w_u - 1) * self.gap
            ky2 = ky1 + self.key_size

            if not (kx2 < bx1 or kx1 > bx2 or ky2 < by1 or ky1 > by2):
                hit_keys.add(key_code)

        ctrl_pressed = bool(event.state & 0x0004)
        alt_pressed = bool(event.state & 0x0020 or event.state & 0x0008 or event.state & 0x0001)

        if alt_pressed:
            self.selected_keys = self.base_selected_keys - hit_keys
        elif ctrl_pressed:
            self.selected_keys = self.base_selected_keys | hit_keys
        else:
            self.selected_keys = set(hit_keys)

        self.render_keyboard()

        if self.selection_rect_id:
            self.canvas.delete(self.selection_rect_id)

        if bx2 - bx1 > 2 or by2 - by1 > 2:
            self.selection_rect_id = self.canvas.create_rectangle(
                x0, y0, x1, y1, outline="#007acc", dash=(2, 2), width=1.5
            )

    def on_picker_color_change(self, hex_code):
        self.update_hex_entry(hex_code)
        if hasattr(self, "rgb_sliders"):
            self.rgb_sliders.set_rgb(*self.picker.get_rgb())
        if self.selected_keys:
            self.apply_color_to_selection()

    def on_rgb_sliders_change(self, r, g, b):
        """Вызывается при изменении слайдеров R/G/B (перетаскиванием или вводом значения)."""
        self.picker.set_color_from_rgb(r, g, b)
        self.update_hex_entry(self.picker.get_hex())
        if self.selected_keys:
            self.apply_color_to_selection()

    def update_hex_entry(self, hex_code):
        self.entry_hex.delete(0, tk.END)
        self.entry_hex.insert(0, hex_code.upper())

    def on_hex_entry_apply(self):
        val = self.entry_hex.get().strip()
        if not val.startswith("#"):
            val = "#" + val
        try:
            r = int(val[1:3], 16)
            g = int(val[3:5], 16)
            b = int(val[5:7], 16)
            self.picker.set_color_from_rgb(r, g, b)
            if hasattr(self, "rgb_sliders"):
                self.rgb_sliders.set_rgb(r, g, b)
            self.apply_color_to_selection()
        except Exception:
            messagebox.showerror(self.tr("error"), self.tr("invalid_hex"))

    def apply_color_to_selection(self):
        if not self.selected_keys:
            return
        r, g, b = self.picker.get_rgb()
        hex_val = self.picker.get_hex()
        raw_colorref = rgb_to_colorref(r, g, b)

        for code in self.selected_keys:
            self.manual_overrides[code] = (hex_val, (r, g, b), raw_colorref)

        self.render_keyboard()

    def reset_manual_colors(self):
        self.manual_overrides.clear()
        self.render_keyboard()

    def get_key_effective_color(self, key_code):
        base = self.base_colors.get(key_code)

        if base:
            hex_val, (r, g, b), raw_val = base
        else:
            hex_val, (r, g, b), raw_val = "#2a2a30", (42, 42, 48), 3156522

        has_color = base is not None

        if self.grad_active_var.get():
            cx, cy = KEY_CENTERS.get(key_code, (0, 0))
            mode = self.grad_mode_key()

            if mode == "horizontal":
                t = (cx - MIN_X) / (MAX_X - MIN_X) if MAX_X != MIN_X else 0.0
            elif mode == "vertical":
                t = (cy - MIN_Y) / (MAX_Y - MIN_Y) if MAX_Y != MIN_Y else 0.0
            elif mode == "radial":
                dist = ((cx - MID_X) ** 2 + (cy - MID_Y) ** 2) ** 0.5
                t = dist / MAX_RAD if MAX_RAD != 0 else 0.0
            else:
                t = 0.0

            if self.grad_invert_var.get():
                t = 1.0 - t

            contrast = getattr(self, "grad_contrast", 0)
            contrast_factor = 1.0 + (contrast / 100.0)
            t = 0.5 + (t - 0.5) * contrast_factor
            t = max(0.0, min(1.0, t))

            c1 = self.grad_start_rgb
            c2 = self.grad_end_rgb
            method = self.combo_grad_method.get()

            r, g, b = interpolate_gradient_color(c1, c2, t, method)
            hex_val = f"#{r:02x}{g:02x}{b:02x}"
            raw_val = rgb_to_colorref(r, g, b)
            has_color = True

        if key_code in self.manual_overrides:
            hex_val, (r, g, b), raw_val = self.manual_overrides[key_code]
            has_color = True

        if self.cc_active_var.get():
            dh = self.scale_hue.get()
            ds = self.scale_sat.get()
            dv = self.scale_val.get()
            hex_val, (r, g, b), raw_val = self.adjust_hsv(r, g, b, dh, ds, dv)

        if not has_color:
            return None

        return hex_val, (r, g, b), raw_val

    def adjust_hsv(self, r, g, b, delta_h, delta_s, delta_v):
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        h_new = (h + delta_h / 360.0) % 1.0
        s_new = max(0.0, min(1.0, s + delta_s / 100.0))
        v_new = max(0.0, min(1.0, v + delta_v / 100.0))
        r_n, g_n, b_n = colorsys.hsv_to_rgb(h_new, s_new, v_new)
        r_i, g_i, b_i = int(round(r_n * 255)), int(round(g_n * 255)), int(round(b_n * 255))
        return f"#{r_i:02x}{g_i:02x}{b_i:02x}", (r_i, g_i, b_i), rgb_to_colorref(r_i, g_i, b_i)

    def render_keyboard(self):
        self.canvas.delete("all")

        for key_code, (label, x_u, y_u, w_u) in KEYBOARD_LAYOUT.items():
            x1 = self.margin + x_u * (self.key_size + self.gap)
            y1 = self.margin + y_u * (self.key_size + self.gap)
            x2 = x1 + w_u * self.key_size + (w_u - 1) * self.gap
            y2 = y1 + self.key_size

            color_data = self.get_key_effective_color(key_code)

            if color_data:
                hex_col, (r, g, b), _ = color_data
                text_col = get_text_color(r, g, b)
            else:
                hex_col = "#2a2a30"
                text_col = "#666666"

            is_selected = key_code in self.selected_keys
            border_color = "#ffffff" if is_selected else ("#000000" if color_data else "#3a3a42")
            border_width = 3 if is_selected else 1

            self.canvas.create_rectangle(
                x1, y1, x2, y2, fill=hex_col, outline=border_color, width=border_width
            )

            self.canvas.create_text(
                (x1 + x2) / 2, (y1 + y2) / 2, text=label, fill=text_col, font=("Segoe UI", 9, "bold")
            )

    def toggle_cc_state(self):
        state = tk.NORMAL if self.cc_active_var.get() else tk.DISABLED
        self.scale_hue.config(state=state)
        self.scale_sat.config(state=state)
        self.scale_val.config(state=state)
        self.render_keyboard()

    def on_slider_change(self, val=None):
        if self.cc_active_var.get():
            self.render_keyboard()

    def reset_cc_sliders(self):
        self.scale_hue.set(0)
        self.scale_sat.set(0)
        self.scale_val.set(0)
        self.render_keyboard()

    def _serialize_color_map(self, color_map):
        return {
            str(code): {
                "hex": data[0],
                "rgb": list(data[1]),
                "raw": data[2]
            }
            for code, data in color_map.items()
        }

    def _deserialize_color_map(self, data):
        result = {}
        for code_str, item in data.items():
            code = int(code_str)
            rgb = tuple(int(v) for v in item["rgb"])
            result[code] = (
                item["hex"],
                rgb,
                int(item["raw"])
            )
        return result

    def _get_picker_state(self, picker):
        return {
            "hue": picker.hue,
            "sat": picker.sat,
            "val": picker.val
        }

    def _set_picker_state(self, picker, state):
        picker.hue = float(state.get("hue", picker.hue))
        picker.sat = float(state.get("sat", picker.sat))
        picker.val = float(state.get("val", picker.val))
        picker.draw_hue_bar()
        picker.draw_hue_marker()
        picker.draw_sv_square()

    def apply_rgb_to_keyboard(self, preset_name=None):
        """Send the current virtual-keyboard RGB state directly to Galaxy 70.

        preset_name: если задано, значит подсветка отправляется в рамках
        применения пресета — используется только для текста статуса/уведомления.
        """
        try:
            color_map = build_live_color_map(self)
        except Exception as e:
            messagebox.showerror(self.tr("error"), str(e))
            return

        self.btn_apply_rgb.config(state=tk.DISABLED, text=self.tr("apply_rgb_sending"))
        self.lbl_info.config(text=self.tr("apply_rgb_sending"))

        def worker():
            try:
                Galaxy70HidTransport().apply_rgb_map(color_map)
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._finish_apply_rgb(False, str(exc), preset_name))
            else:
                self.root.after(0, lambda: self._finish_apply_rgb(True, None, preset_name))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_apply_rgb(self, success, error_text, preset_name=None):
        self.btn_apply_rgb.config(state=tk.NORMAL, text=self.tr("apply_rgb"))

        if success:
            if preset_name:
                self.lbl_info.config(text=self.tr("preset_applied", name=preset_name))
            else:
                self.lbl_info.config(text=self.tr("apply_rgb_success"))
        else:
            self.lbl_info.config(text=self.tr("error"))

    def _build_project_dict(self):
        """Собирает полный снимок текущего состояния программы (используется
        и для Save Project, и для сохранения пресетов)."""
        return {
            "format": "Galaxy70EditorProject",
            "version": 1,
            "window": {
                "geometry": self.root.geometry()
            },
            "profile": {
                "label": self.lbl_profile.cget("text"),
                "xml": (
                    ET.tostring(
                        self.xml_tree.getroot(),
                        encoding="unicode"
                    )
                    if self.xml_tree is not None else None
                )
            },
            "colors": {
                "base": self._serialize_color_map(self.base_colors),
                "manual_overrides": self._serialize_color_map(self.manual_overrides)
            },
            "selection": {
                "selected_keys": sorted(self.selected_keys),
                "base_selected_keys": sorted(self.base_selected_keys)
            },
            "gradient": {
                "active": bool(self.grad_active_var.get()),
                "invert": bool(self.grad_invert_var.get()),
                "contrast": int(self.grad_contrast),
                "mode": self.grad_mode_key(),
                "method": self.grad_method_key(),
                "start_rgb": list(self.grad_start_rgb),
                "end_rgb": list(self.grad_end_rgb),
                "active_target": self.active_grad_target,
                "picker": self._get_picker_state(self.grad_picker),
                "hex": self.entry_grad_hex.get()
            },
            "color_correction": {
                "active": bool(self.cc_active_var.get()),
                "hue": int(self.scale_hue.get()),
                "saturation": int(self.scale_sat.get()),
                "value": int(self.scale_val.get())
            },
            "manual_picker": {
                "picker": self._get_picker_state(self.picker),
                "hex": self.entry_hex.get()
            },
            "ui": {
                "active_tab": self.active_tab
            }
        }

    def _apply_project_dict(self, project, restore_geometry=True):
        """Восстанавливает состояние программы из словаря проекта (используется
        и Open Project, и применением пресетов). Бросает исключение при ошибке —
        обработка и текст сообщения остаются на вызывающей стороне."""
        if project.get("format") != "Galaxy70EditorProject":
            raise ValueError(self.tr("not_project"))

        version = int(project.get("version", 1))
        if version != 1:
            raise ValueError(
                self.tr("unsupported_version", version=version)
            )

        profile = project.get("profile", {})
        xml_text = profile.get("xml")

        if xml_text:
            root_elem = ET.fromstring(xml_text)
            self.xml_tree = ET.ElementTree(root_elem)
        else:
            self.xml_tree = None

        colors = project.get("colors", {})
        self.base_colors = self._deserialize_color_map(
            colors.get("base", {})
        )
        self.manual_overrides = self._deserialize_color_map(
            colors.get("manual_overrides", {})
        )

        selection = project.get("selection", {})
        self.selected_keys = set(
            int(v) for v in selection.get("selected_keys", [])
        )
        self.base_selected_keys = set(
            int(v) for v in selection.get("base_selected_keys", [])
        )

        gradient = project.get("gradient", {})
        self.grad_active_var.set(bool(gradient.get("active", False)))
        self.grad_invert_var.set(bool(gradient.get("invert", False)))
        self.grad_contrast = int(gradient.get("contrast", 0))

        self.grad_start_rgb = tuple(
            int(v) for v in gradient.get("start_rgb", [255, 255, 255])
        )
        self.grad_end_rgb = tuple(
            int(v) for v in gradient.get("end_rgb", [0, 0, 0])
        )
        self.active_grad_target = gradient.get(
            "active_target", "start"
        )

        grad_mode_raw = gradient.get("mode", "horizontal")
        grad_method_raw = gradient.get("method", "hsv")

        grad_mode = grad_mode_raw if grad_mode_raw in GRAD_MODE_KEYS else next(
            (key for key, values in GRAD_MODE_KEYS.items() if grad_mode_raw in values), "horizontal"
        )
        grad_method = grad_method_raw if grad_method_raw in GRAD_METHOD_KEYS else next(
            (key for key, values in GRAD_METHOD_KEYS.items() if grad_method_raw in values), "hsv"
        )

        self.combo_grad_mode.set(self.grad_mode_display(grad_mode))
        self.combo_grad_method.set(self.grad_method_display(grad_method))
        self.scale_grad_contrast.set(self.grad_contrast)

        grad_picker_state = gradient.get("picker")
        if grad_picker_state:
            self._set_picker_state(
                self.grad_picker, grad_picker_state
            )

        grad_hex = gradient.get("hex", "")
        self.entry_grad_hex.delete(0, tk.END)
        self.entry_grad_hex.insert(0, grad_hex)

        if hasattr(self, "grad_rgb_sliders"):
            self.grad_rgb_sliders.set_rgb(*self.grad_picker.get_rgb())

        cc = project.get("color_correction", {})
        cc_active = bool(cc.get("active", False))
        self.cc_active_var.set(cc_active)
        self.toggle_cc_state()

        try:
            hue = max(-180, min(180, int(cc.get("hue", 0))))
        except (TypeError, ValueError):
            hue = 0
        try:
            saturation = max(-100, min(100, int(cc.get("saturation", 0))))
        except (TypeError, ValueError):
            saturation = 0
        try:
            value = max(-100, min(100, int(cc.get("value", 0))))
        except (TypeError, ValueError):
            value = 0

        self.scale_hue.set(hue)
        self.scale_sat.set(saturation)
        self.scale_val.set(value)

        self.toggle_cc_state()

        manual_picker = project.get("manual_picker", {})
        picker_state = manual_picker.get("picker")
        if picker_state:
            self._set_picker_state(
                self.picker, picker_state
            )

        manual_hex = manual_picker.get("hex", "")
        self.entry_hex.delete(0, tk.END)
        self.entry_hex.insert(0, manual_hex)

        if hasattr(self, "rgb_sliders"):
            self.rgb_sliders.set_rgb(*self.picker.get_rgb())

        profile_label = profile.get("label", self.tr("profile_not_loaded"))
        self.profile_name = None
        for prefix in (LANG["ru"]["profile"].split("{name}")[0], LANG["en"]["profile"].split("{name}")[0]):
            if profile_label.startswith(prefix):
                self.profile_name = profile_label[len(prefix):]
                break
        if self.profile_name is None and profile_label not in (LANG["ru"]["profile_not_loaded"], LANG["en"]["profile_not_loaded"]):
            self.profile_name = profile_label

        self.lbl_profile.config(
            text=self.tr("profile", name=self.profile_name) if self.profile_name else self.tr("profile_not_loaded"),
            fg="#ffffff"
        )

        ui = project.get("ui", {})
        active_tab = ui.get("active_tab", "manual")
        if active_tab not in {"manual", "grad", "cc"}:
            active_tab = "manual"

        if restore_geometry:
            geometry = project.get("window", {}).get("geometry")
            if geometry:
                try:
                    self.root.geometry(geometry)
                except tk.TclError:
                    pass

        self.update_grad_circles()
        self.select_grad_target(self.active_grad_target)
        self.switch_tab(active_tab)
        self.toggle_grad_state()
        self.toggle_cc_state()
        self.render_keyboard()

    def save_project(self):
        if not self.xml_tree:
            answer = messagebox.askyesno(
                self.tr("project_without_xml"),
                self.tr("xml_not_imported")
            )
            if not answer:
                return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".eglx",
            filetypes=[
                (self.tr("project_file_type"), "*.eglx"),
                (self.tr("all_files"), "*.*")
            ],
            initialfile=self.tr("project_filename")
        )
        if not file_path:
            return

        try:
            project = self._build_project_dict()

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(project, f, ensure_ascii=False, indent=2)

            self.current_project_path = file_path
            self.lbl_info.config(text=self.tr("project_saved_short", name=os.path.basename(file_path)))
            messagebox.showinfo(
                self.tr("success"),
                self.tr("project_saved", path=file_path)
            )

        except Exception as e:
            messagebox.showerror(
                self.tr("error"),
                self.tr("save_project_error", error=e)
            )

    def open_project(self):
        file_path = filedialog.askopenfilename(
            filetypes=[
                (self.tr("project_file_type"), "*.eglx"),
                (self.tr("all_files"), "*.*")
            ]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                project = json.load(f)

            self._apply_project_dict(project, restore_geometry=True)
            self.current_project_path = file_path

            self.lbl_info.config(
                text=(
                    self.tr("project_opened_short", name=os.path.basename(file_path), n=len(self.selected_keys))
                )
            )

        except Exception as e:
            messagebox.showerror(
                self.tr("error"),
                self.tr("open_project_error", error=e)
            )

    # ---------------------------------------------------------------
    # Пресеты подсветки
    # ---------------------------------------------------------------

    def toggle_presets_panel(self):
        if self.presets_panel_visible:
            self.presets_panel.pack_forget()
            self.presets_panel_visible = False
            self._resize_window_by(delta_w=-(self.PRESETS_PANEL_WIDTH + self.PRESETS_PANEL_PADX))
        else:
            self.presets_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(self.PRESETS_PANEL_PADX, 0))
            self.presets_panel_visible = True
            self.refresh_presets_list()
            self._resize_window_by(delta_w=(self.PRESETS_PANEL_WIDTH + self.PRESETS_PANEL_PADX))

    def _resize_window_by(self, delta_w=0, delta_h=0):
        """Расширяет/сужает окно программы на заданную дельту по ширине и/или
        высоте, сохраняя его текущую позицию на экране. Используется и
        панелью пресетов (по ширине), и спойлерами RGB-слайдеров (по высоте) —
        чтобы новый контент не обрезался, а окно не приходилось растягивать вручную."""
        self.root.update_idletasks()
        match = re.match(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", self.root.geometry())
        if not match:
            return

        width, height, x, y = match.groups()
        new_width = max(700, int(width) + delta_w)
        new_height = max(500, int(height) + delta_h)
        try:
            self.root.geometry(f"{new_width}x{new_height}{x}{y}")
        except tk.TclError:
            pass

    def _list_preset_files(self):
        """Возвращает список (display_name, file_path), отсортированный по имени."""
        presets_dir = get_presets_dir()
        items = []
        try:
            filenames = os.listdir(presets_dir)
        except OSError:
            filenames = []

        for filename in filenames:
            if not filename.lower().endswith(".eglx"):
                continue
            file_path = os.path.join(presets_dir, filename)
            display_name = os.path.splitext(filename)[0]
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                display_name = data.get("preset_name", display_name)
            except Exception:
                pass
            items.append((display_name, file_path))

        items.sort(key=lambda pair: pair[0].lower())
        return items

    def refresh_presets_list(self):
        """Перестраивает список кнопок пресетов внутри панели."""
        for widget in self.preset_widgets:
            widget.destroy()
        self.preset_widgets = []

        presets = self._list_preset_files()

        if not presets:
            lbl_empty = tk.Label(
                self.presets_list_frame, text=self.tr("no_presets"),
                font=("Segoe UI", 8), bg="#25252b", fg="#777777",
                wraplength=190, justify="left"
            )
            lbl_empty.pack(fill=tk.X, pady=8)
            self.preset_widgets.append(lbl_empty)
            return

        for display_name, file_path in presets:
            row = tk.Frame(self.presets_list_frame, bg="#25252b")
            row.pack(fill=tk.X, pady=2)

            btn_preset = tk.Button(
                row, text=display_name, anchor="w",
                command=lambda p=file_path: self.apply_preset(p),
                font=("Segoe UI", 9), bg="#1e1e24", fg="#ffffff",
                relief=tk.FLAT, padx=8, pady=5, cursor="hand2"
            )
            btn_preset.pack(side=tk.LEFT, fill=tk.X, expand=True)

            btn_delete = tk.Button(
                row, text="✕",
                command=lambda p=file_path, n=display_name: self.delete_preset(p, n),
                font=("Segoe UI", 8, "bold"), bg="#1e1e24", fg="#aa5555",
                relief=tk.FLAT, padx=6, pady=5, cursor="hand2"
            )
            btn_delete.pack(side=tk.RIGHT, padx=(4, 0))

            self.preset_widgets.append(row)

    def save_preset(self):
        name = simpledialog.askstring(
            self.tr("preset_name_title"),
            self.tr("preset_name_prompt"),
            parent=self.root
        )
        if name is None:
            return

        name = name.strip()
        if not name:
            messagebox.showerror(self.tr("error"), self.tr("preset_empty_name"))
            return

        try:
            presets_dir = get_presets_dir()
            safe_name = sanitize_filename(name)
            file_path = os.path.join(presets_dir, f"{safe_name}.eglx")

            if os.path.exists(file_path):
                overwrite = messagebox.askyesno(
                    self.tr("warning"),
                    self.tr("preset_exists_overwrite", name=name)
                )
                if not overwrite:
                    return

            project = self._build_project_dict()
            project["preset_name"] = name

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(project, f, ensure_ascii=False, indent=2)

            if self.presets_panel_visible:
                self.refresh_presets_list()

            self.lbl_info.config(text=self.tr("preset_saved", name=name))

        except Exception as e:
            messagebox.showerror(
                self.tr("error"),
                self.tr("preset_save_error", error=e)
            )

    def apply_preset(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                project = json.load(f)

            preset_name = project.get("preset_name", os.path.splitext(os.path.basename(file_path))[0])

            # Восстанавливаем градиенты/цветокоррекцию/ручные цвета так же,
            # как это делает Open Project, но не трогаем геометрию окна.
            self._apply_project_dict(project, restore_geometry=False)

            # Запоминаем, какой пресет применён последним — нужно для
            # циклического переключения по хоткеям (cycle_preset).
            self._last_applied_preset_path = file_path

            # Отправляем итоговую подсветку на клавиатуру — по той же логике,
            # что и кнопка Apply RGB. Статус/уведомление сформируются с именем пресета.
            self.apply_rgb_to_keyboard(preset_name=preset_name)

        except Exception as e:
            messagebox.showerror(
                self.tr("error"),
                self.tr("preset_apply_error", error=e)
            )

    def cycle_preset(self, direction=1):
        """Переключает подсветку клавиатуры на следующий (direction=1) или
        предыдущий (direction=-1) пресет по списку — в том же порядке, что и
        в панели пресетов/трее. Используется хоткеями Fn+=/Fn+- (или другими,
        назначенными в настройках)."""
        presets = self._list_preset_files()
        if not presets:
            return

        paths = [p for _, p in presets]
        current = self._last_applied_preset_path

        if current in paths:
            idx = (paths.index(current) + direction) % len(paths)
        else:
            idx = 0 if direction > 0 else -1

        self.apply_preset(paths[idx])

    # --- Глобальные хоткеи -----------------------------------------------

    def _on_global_key_event(self, vk, scan, extended, mods):
        """Вызывается из потока WinAPI-хука — сразу передаём обработку в
        основной поток Tkinter, трогать виджеты из чужого потока нельзя."""
        try:
            self.root.after(0, self._handle_global_key_event, vk, scan, extended, mods)
        except Exception:
            pass

    def _handle_global_key_event(self, vk, scan, extended, mods):
        # Если сейчас открыт диалог настроек и идёт запись новой комбинации —
        # перехватываем это нажатие как записываемый хоткей и не даём ему
        # сработать как обычному переключателю пресетов.
        if self._hotkey_capture_target is not None:
            self._finish_hotkey_capture(vk, scan, extended, mods)
            return

        next_binding = self.settings.get("hotkey_next_preset")
        prev_binding = self.settings.get("hotkey_prev_preset")

        if hotkey_bindings_equal(next_binding, vk, scan, extended, mods):
            self.cycle_preset(1)
        elif hotkey_bindings_equal(prev_binding, vk, scan, extended, mods):
            self.cycle_preset(-1)

    def _finish_hotkey_capture(self, vk, scan, extended, mods):
        """Завершает запись хоткея в диалоге настроек: сохраняет привязку и
        обновляет соответствующие виджеты (если диалог всё ещё открыт)."""
        target = self._hotkey_capture_target
        self._hotkey_capture_target = None
        widgets = self._hotkey_capture_widgets
        self._hotkey_capture_widgets = None

        if target is None:
            return

        setting_key = "hotkey_next_preset" if target == "next" else "hotkey_prev_preset"
        binding = {
            "vk": vk, "scan": scan, "ext": bool(extended),
            "ctrl": bool(mods.get("ctrl")), "alt": bool(mods.get("alt")),
            "shift": bool(mods.get("shift")), "win": bool(mods.get("win")),
        }
        self.settings[setting_key] = binding
        save_app_settings(self.settings)

        if widgets is not None:
            label_var, btn_record = widgets
            try:
                label_var.set(hotkey_binding_to_label(binding))
                btn_record.config(state=tk.NORMAL)
            except tk.TclError:
                pass  # диалог уже закрыт

    def delete_preset(self, file_path, display_name):
        confirm = messagebox.askyesno(
            self.tr("warning"),
            self.tr("preset_delete_confirm", name=display_name)
        )
        if not confirm:
            return
        try:
            os.remove(file_path)
            self.refresh_presets_list()
        except Exception as e:
            messagebox.showerror(
                self.tr("error"),
                self.tr("preset_delete_error", error=e)
            )

    # ---------------------------------------------------------------
    # Настройки приложения (автозапуск / трей)
    # ---------------------------------------------------------------

    def open_settings_dialog(self):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return

        win = tk.Toplevel(self.root)
        win.title(self.tr("settings_title"))
        win.configure(bg="#25252b")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self._settings_win = win

        container = tk.Frame(win, bg="#25252b", padx=18, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container, text=self.tr("settings_title"), font=("Segoe UI", 11, "bold"),
            bg="#25252b", fg="#ffffff"
        ).pack(anchor="w", pady=(0, 12))

        var_startup = tk.BooleanVar(value=is_run_at_startup())
        var_start_min = tk.BooleanVar(value=bool(self.settings.get("start_minimized", False)))
        var_close_min = tk.BooleanVar(value=bool(self.settings.get("minimize_on_close", False)))

        chk_style = dict(
            bg="#25252b", fg="#ffffff", activebackground="#25252b", activeforeground="#ffffff",
            selectcolor="#1e1e24", font=("Segoe UI", 10), anchor="w", justify="left",
            highlightthickness=0
        )

        def on_toggle_startup():
            if winreg is None:
                messagebox.showwarning(self.tr("warning"), self.tr("startup_unsupported"))
                var_startup.set(False)
                return
            try:
                set_run_at_startup(var_startup.get())
            except Exception as e:
                messagebox.showerror(self.tr("error"), self.tr("startup_error", error=e))
                var_startup.set(is_run_at_startup())

        def on_toggle_start_min():
            if var_start_min.get() and not TRAY_LIBS_AVAILABLE:
                messagebox.showwarning(self.tr("warning"), self.tr("tray_unavailable"))
                var_start_min.set(False)
                return
            self.settings["start_minimized"] = bool(var_start_min.get())
            save_app_settings(self.settings)

        def on_toggle_close_min():
            if var_close_min.get() and not TRAY_LIBS_AVAILABLE:
                messagebox.showwarning(self.tr("warning"), self.tr("tray_unavailable"))
                var_close_min.set(False)
                return
            self.settings["minimize_on_close"] = bool(var_close_min.get())
            save_app_settings(self.settings)

        tk.Checkbutton(
            container, text=self.tr("setting_run_at_startup"), variable=var_startup,
            command=on_toggle_startup, **chk_style
        ).pack(fill=tk.X, pady=4)

        tk.Checkbutton(
            container, text=self.tr("setting_start_minimized"), variable=var_start_min,
            command=on_toggle_start_min, **chk_style
        ).pack(fill=tk.X, pady=4)

        tk.Checkbutton(
            container, text=self.tr("setting_minimize_on_close"), variable=var_close_min,
            command=on_toggle_close_min, **chk_style
        ).pack(fill=tk.X, pady=4)

        if not TRAY_LIBS_AVAILABLE:
            tk.Label(
                container, text=self.tr("tray_libs_missing_note"), font=("Segoe UI", 8),
                bg="#25252b", fg="#c9a24b", wraplength=280, justify="left"
            ).pack(fill=tk.X, pady=(10, 0))

        # --- Горячие клавиши переключения пресетов ---------------------

        tk.Frame(container, bg="#3a3a42", height=1).pack(fill=tk.X, pady=(14, 10))

        tk.Label(
            container, text=self.tr("hotkeys_section_title"), font=("Segoe UI", 10, "bold"),
            bg="#25252b", fg="#ffffff"
        ).pack(anchor="w", pady=(0, 8))

        self._hotkey_row_refs = {}

        def build_hotkey_row(setting_key, label_text, target):
            row = tk.Frame(container, bg="#25252b")
            row.pack(fill=tk.X, pady=4)

            tk.Label(
                row, text=label_text, font=("Segoe UI", 9), bg="#25252b", fg="#cccccc",
                width=14, anchor="w"
            ).pack(side=tk.LEFT)

            current_binding = self.settings.get(setting_key)
            label_var = tk.StringVar(
                value=hotkey_binding_to_label(current_binding) or self.tr("hotkey_not_set")
            )
            tk.Label(
                row, textvariable=label_var, font=("Segoe UI", 9, "bold"), bg="#1e1e24",
                fg="#ffffff", anchor="w", padx=8, pady=4, width=15
            ).pack(side=tk.LEFT, padx=(6, 6))

            btn_record = tk.Button(
                row, text=self.tr("hotkey_record"), font=("Segoe UI", 8, "bold"),
                bg="#495057", fg="white", relief=tk.FLAT, padx=8, pady=3, cursor="hand2"
            )
            btn_record.pack(side=tk.LEFT, padx=(0, 4))

            btn_clear = tk.Button(
                row, text="✕", font=("Segoe UI", 8, "bold"),
                bg="#1e1e24", fg="#aa5555", relief=tk.FLAT, padx=6, pady=3, cursor="hand2"
            )
            btn_clear.pack(side=tk.LEFT)

            def start_capture():
                if self._hotkey_capture_target is not None:
                    return
                self._hotkey_capture_target = target
                self._hotkey_capture_widgets = (label_var, btn_record)
                label_var.set(self.tr("hotkey_press_now"))
                btn_record.config(state=tk.DISABLED)

            def clear_binding():
                self.settings[setting_key] = None
                save_app_settings(self.settings)
                label_var.set(self.tr("hotkey_not_set"))

            btn_record.config(command=start_capture)
            btn_clear.config(command=clear_binding)

            self._hotkey_row_refs[target] = (setting_key, label_var, btn_record)

        build_hotkey_row("hotkey_next_preset", self.tr("hotkey_next_label"), "next")
        build_hotkey_row("hotkey_prev_preset", self.tr("hotkey_prev_label"), "prev")

        tk.Label(
            container, text=self.tr("hotkey_note"), font=("Segoe UI", 8),
            bg="#25252b", fg="#888888", wraplength=280, justify="left"
        ).pack(fill=tk.X, pady=(8, 0))

        def on_settings_close():
            # Если диалог закрывают прямо во время записи хоткея — сбрасываем режим записи.
            self._hotkey_capture_target = None
            self._hotkey_capture_widgets = None
            win.destroy()

        tk.Button(
            container, text=self.tr("close"), command=on_settings_close,
            font=("Segoe UI", 9, "bold"), bg="#495057", fg="white",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2"
        ).pack(anchor="e", pady=(14, 0))

        win.protocol("WM_DELETE_WINDOW", on_settings_close)

        self._center_toplevel_on_root(win)

    def _center_toplevel_on_root(self, win):
        """Центрирует всплывающее окно относительно главного окна программы."""
        win.update_idletasks()
        win_w = win.winfo_reqwidth()
        win_h = win.winfo_reqheight()

        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()

        x = root_x + (root_w - win_w) // 2
        y = root_y + (root_h - win_h) // 2

        x = max(0, x)
        y = max(0, y)

        win.geometry(f"+{x}+{y}")

    # --- Системный трей -------------------------------------------------

    def _build_tray_image(self):
        """Иконка для трея — берётся из того же icon.ico, что и иконка окна
        (resource_path гарантирует, что после сборки в .exe через PyInstaller
        с флагом --add-data файл будет извлечён из самого exe, а не должен
        лежать рядом отдельным файлом).
        """
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            try:
                img = Image.open(icon_path)
                img.load()
                return img.convert("RGBA")
            except Exception:
                pass

        # Фолбэк на случай, если icon.ico не найден/повреждён — рисуем
        # простую заглушку, чтобы трей всё равно не остался без иконки.
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([4, 4, size - 4, size - 4], radius=14, fill=(111, 66, 193, 255))
        text = "G7"
        try:
            bbox = draw.textbbox((0, 0), text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), text, fill="white")
        except Exception:
            draw.text((14, 22), text, fill="white")
        return img

    def _build_tray_menu(self):
        """Собирает меню трея: сверху — пресеты (в том же порядке, что и в
        панели программы), затем разделитель, затем Open/Exit."""
        items = []

        for display_name, file_path in self._list_preset_files():
            items.append(
                pystray.MenuItem(display_name, self._make_tray_preset_handler(file_path))
            )

        if items:
            items.append(pystray.Menu.SEPARATOR)

        items.append(
            pystray.MenuItem(
                "Open Galaxy 70 Editor" if self.lang == "en" else "Открыть Galaxy 70 Editor",
                self._tray_restore, default=True
            )
        )
        items.append(
            pystray.MenuItem("Exit" if self.lang == "en" else "Выход", self._tray_exit)
        )

        return pystray.Menu(*items)

    def _make_tray_preset_handler(self, file_path):
        """Возвращает обработчик клика по пункту-пресету в трее.

        Клик приходит из потока pystray, поэтому применение пресета
        (взаимодействие с Tkinter/HID) переносится в основной поток через root.after —
        сама логика применения (_apply_project_dict + apply_rgb_to_keyboard)
        идентична выбору пресета внутри программы и кнопке Apply RGB.
        """
        def handler(icon=None, item=None):
            self.root.after(0, lambda: self.apply_preset(file_path))
        return handler

    def show_tray_icon(self):
        if not TRAY_LIBS_AVAILABLE or self.tray_icon is not None:
            return
        image = self._build_tray_image()
        menu = self._build_tray_menu()
        self.tray_icon = pystray.Icon("Galaxy70Editor", image, self.tr("title"), menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_tray_icon(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

    def _tray_restore(self, icon=None, item=None):
        self.root.after(0, self._restore_from_tray)

    def _restore_from_tray(self):
        self.hide_tray_icon()
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _tray_exit(self, icon=None, item=None):
        self.root.after(0, self._exit_app)

    def _exit_app(self):
        self.hide_tray_icon()
        self.hotkey_manager.stop()
        self.root.destroy()

    def _start_minimized_to_tray(self):
        self.root.withdraw()
        self.show_tray_icon()

    def on_close_request(self):
        """Обработчик закрытия окна (крестик). Сворачивает в трей, если это
        включено в настройках и нужные библиотеки установлены, иначе закрывает программу."""
        if self.settings.get("minimize_on_close") and TRAY_LIBS_AVAILABLE:
            self.root.withdraw()
            self.show_tray_icon()
        else:
            self.hotkey_manager.stop()
            self.root.destroy()

    def load_xml(self):
        file_path = filedialog.askopenfilename(filetypes=[("XML files" if self.lang == "en" else "XML-файлы", "*.xml"), (self.tr("all_files"), "*.*")])
        if not file_path:
            return
        try:
            self.xml_tree = ET.parse(file_path)
            root_elem = self.xml_tree.getroot()
            lightinfo = root_elem.find("lightinfo")
            prof_name = lightinfo.attrib.get("name", self.tr("custom_profile")) if lightinfo is not None else self.tr("xml_unknown")
            self.profile_name = prof_name
            self.lbl_profile.config(text=self.tr("profile", name=prof_name), fg="#ffffff")

            self.base_colors.clear()
            self.manual_overrides.clear()
            keyinfo = root_elem.find("keyinfo")
            if keyinfo is not None:
                for item in keyinfo.findall("item"):
                    code = int(item.attrib["key_code"])
                    raw_rgb = int(item.attrib["key_rgb"])
                    hex_val, rgb_tuple = colorref_to_hex_and_rgb(raw_rgb)
                    self.base_colors[code] = (hex_val, rgb_tuple, raw_rgb)

            self.render_keyboard()
            self.lbl_info.config(text=self.tr("loaded_keys", n=len(self.base_colors)))
        except Exception as e:
            messagebox.showerror(self.tr("error"), self.tr("xml_read_error", error=e))

    def export_xml(self):
        if not self.xml_tree:
            self.xml_tree = self.create_default_xml_tree()

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xml", 
            filetypes=[("XML files" if self.lang == "en" else "XML-файлы", "*.xml")], 
            initialfile="Custom_Keyboard_Light.xml"
        )
        if not file_path:
            return
        try:
            root_elem = self.xml_tree.getroot()
            root_elem.tag = "userlight"

            # Синхронизация блока lightinfo
            lightinfo = root_elem.find("lightinfo")
            if lightinfo is None:
                lightinfo = ET.Element("lightinfo")
                root_elem.insert(0, lightinfo)
            prof_name = self.profile_name if self.profile_name else self.tr("custom_profile")
            lightinfo.attrib["name"] = prof_name

            # Синхронизация блока keyinfo
            keyinfo = root_elem.find("keyinfo")
            if keyinfo is None:
                keyinfo = ET.SubElement(root_elem, "keyinfo")

            existing_codes = set()
            for item in keyinfo.findall("item"):
                if "key_code" in item.attrib:
                    code = int(item.attrib["key_code"])
                    existing_codes.add(code)
                    col_data = self.get_key_effective_color(code)
                    if col_data:
                        _, _, colorref_val = col_data
                        item.attrib["key_rgb"] = str(colorref_val)

            # Добавляем клавиши, отсутствовавшие в исходном файле
            for code in KEYBOARD_LAYOUT.keys():
                if code not in existing_codes:
                    col_data = self.get_key_effective_color(code)
                    colorref_val = col_data[2] if col_data else 0
                    ET.SubElement(keyinfo, "item", key_code=str(code), key_rgb=str(colorref_val))

            # Построчное формирование XML по точному шаблону родной утилиты
            profile_name_attr = lightinfo.attrib.get("name", "Custom Light").replace("&", "&amp;").replace('"', "&quot;")
            lines = [
                "<?xml version='1.0' encoding='UTF-8'?>",
                "<userlight>",
                f'<lightinfo name="{profile_name_attr}" />',
                "<keyinfo>"
            ]

            for item in keyinfo.findall("item"):
                k_code = item.attrib.get("key_code", "")
                k_rgb = item.attrib.get("key_rgb", "0")
                lines.append(f'<item key_code="{k_code}" key_rgb="{k_rgb}" />')

            lines.append("</keyinfo>")
            lines.append("</userlight>")
            lines.append("")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            self.lbl_info.config(text=self.tr("xml_saved_short", path=os.path.basename(file_path)))
        except Exception as e:
            messagebox.showerror(self.tr("error"), self.tr("xml_export_error", error=e))


if __name__ == "__main__":
    # Регистрация AppUserModelID для отображения иконки в Windows
    try:
        myappid = "galaxy70.customizer.gui.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    root = tk.Tk()

    # icon.ico используется и для иконки окна/панели задач, и для иконки в трее
    # (см. _build_tray_image). Через resource_path() он ищется:
    #   - рядом со скриптом при обычном запуске `python eglx70.py`;
    #   - внутри временной папки _MEIPASS при запуске собранного .exe —
    #     то есть файл должен быть встроен в сам exe при сборке PyInstaller,
    #     чтобы после компиляции не нужно было носить icon.ico отдельным файлом:
    #
    #     pyinstaller --onefile --windowed --icon=icon.ico ^
    #                 --add-data "icon.ico;." eglx70.py
    #
    #   (на macOS/Linux разделитель в --add-data — двоеточие: "icon.ico:.")
    icon_file = resource_path("icon.ico")
    if os.path.exists(icon_file):
        try:
            root.iconbitmap(default=icon_file)
        except Exception:
            pass

    app = KeyboardVisualizerApp(root)
    root.mainloop()
