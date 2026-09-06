import xml.etree.ElementTree as ET
import colorsys
import math
import json
import os
import sys
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def resource_path(relative_path):
    """Возвращает абсолютный путь к ресурсу. 
    Работает как при обычном запуске, так и внутри скомпилированного .exe (PyInstaller).
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


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
        "title": "Galaxy 70 Customizer",
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
        "xml_export_error": "Не удалось экспортировать файл:\n{error}",
        "custom_profile": "Custom",
        "profile": "Профиль: {name}",
    },
    "en": {
        "title": "Galaxy 70 Customizer",
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
        "xml_export_error": "Could not export file:\n{error}",
        "custom_profile": "Custom",
        "profile": "Profile: {name}",
    }
}

GRAD_MODE_KEYS = {"horizontal": ("Горизонтально", "Horizontal"), "vertical": ("Вертикально", "Vertical"), "radial": ("Радиально", "Radial")}
GRAD_METHOD_KEYS = {"rgb": ("RGB — классический", "RGB — Classic"), "hsv": ("HSV — насыщенный", "HSV — Saturated"), "oklab": ("OKLab — естественный", "OKLab — Natural")}


class KeyboardVisualizerApp:
    def __init__(self, root):
        self.root = root
        self.lang = "ru"
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

        self.setup_ui()

        # Горячие клавиши проекта.
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-o>", lambda e: self.open_project())

    def tr(self, key, **kwargs):
        text = LANG[self.lang][key]
        return text.format(**kwargs) if kwargs else text

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

        self.canvas = tk.Canvas(
            main_container, width=880, height=330,
            bg="#121214", highlightthickness=1, highlightbackground="#333338"
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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

        self.switch_tab(getattr(self, "active_tab", "manual"))
        self.render_keyboard()

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

    def build_manual_tab(self):
        lbl_title = tk.Label(self.frame_manual, text=self.tr("color_palette"), font=("Segoe UI", 11, "bold"), bg="#25252b", fg="#ffffff")
        lbl_title.pack(anchor="w", pady=(0, 5))

        self.picker = PhotoshopColorPicker(self.frame_manual, self.on_picker_color_change)
        self.picker.pack(anchor="w", pady=5)

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

        self.entry_grad_hex.delete(0, tk.END)
        self.entry_grad_hex.insert(0, hex_code.upper())
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
            project = {
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

            self.current_project_path = file_path

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
            messagebox.showwarning(self.tr("warning"), self.tr("import_first"))
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML files" if self.lang == "en" else "XML-файлы", "*.xml")], initialfile="Custom_Keyboard_Light.xml")
        if not file_path:
            return
        try:
            root_elem = self.xml_tree.getroot()
            keyinfo = root_elem.find("keyinfo")
            if keyinfo is not None:
                for item in keyinfo.findall("item"):
                    code = int(item.attrib["key_code"])
                    col_data = self.get_key_effective_color(code)
                    if col_data:
                        _, _, colorref_val = col_data
                        item.attrib["key_rgb"] = str(colorref_val)

            self.xml_tree.write(file_path, encoding="UTF-8", xml_declaration=True)
            messagebox.showinfo(self.tr("success"), self.tr("xml_saved", path=file_path))
        except Exception as e:
            messagebox.showerror(self.tr("error"), self.tr("xml_export_error", error=e))


if __name__ == "__main__":
    # Явная регистрация уникального AppUserModelID для Windows (для иконки на панели задач)
    try:
        myappid = "galaxy70.customizer.gui.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    root = tk.Tk()

    # Установка иконки для окна и всех диалоговых окон процесса
    icon_file = resource_path("icon.ico")
    if os.path.exists(icon_file):
        try:
            root.iconbitmap(default=icon_file)
        except Exception:
            pass

    app = KeyboardVisualizerApp(root)
    root.mainloop()