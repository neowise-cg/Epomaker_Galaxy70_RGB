# ⌨️ Epomaker Galaxy 70 RGB Customizer

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Platform" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" />
</p>

A Python (Tkinter) GUI utility for visual customization and generation of RGB lighting profiles for **Epomaker Galaxy 70** keyboards (supporting XML configuration formats from official Epomaker Driver).

---

## 🌟 Key Features

- **🎨 Photoshop-Style Custom Color Picker:** Intuitive color selection featuring a Saturation/Value box and a Hue slider.
- **🌈 Advanced Gradients:**
  - **Directions:** *Horizontal*, *Vertical*, *Radial*.
  - **Blending Algorithms:**
    - `Classic RGB` — Standard linear blending.
    - `Saturated HSV` — Vivid, rich transitions across the color wheel.
    - `Natural OKLab` — Physically accurate blending in the OKLab color space without brightness drops or muddy tones.
  - Gradient contrast adjustment and direction inversion.
- **🎛 HSV Color Correction:** Global adjustment of Hue, Saturation, and Brightness.
- **🖱 Convenient Multi-Selection:**
  - Box selection (Marquee Select).
  - Add keys to selection (`Ctrl` + Left Mouse Drag/Click).
  - Remove keys from selection (`Shift` + Left Mouse Drag/Click).
- **💡 Live RGB Apply:** Send the currently displayed lighting configuration directly from the virtual keyboard to the connected physical **Epomaker Galaxy 70** using the **`Apply RGB`** button, allowing you to preview your custom lighting on the real keyboard without exporting an XML file first.
- **💾 Custom Project Format (`.eglx`):** Save your current work state, selected keys, filters, and gradient settings to continue later.
- **📄 XML Import & Export:** Full compatibility with official keyboard lighting profiles.
- **🌐 Dual-Language Interface:** On-the-fly UI language switching (`RU` / `EN`).
- **⭐ Preset System:** Slide-out panel for quick-saving and loading lighting presets:
  - Save, load, and delete presets as separate `.eglxp` files in a local `presets/` folder.
  - Toggle the panel from a button in the top bar; the window resizes on open/close.
  - Presets are also listed directly in the system tray menu for one-click switching without opening the app window.
- **⚙️ Settings Dialog:** New settings window with:
  - **Run at Windows startup** — adds/removes the app from the Windows Registry `Run` key.
  - **Start minimized to tray** — launch the app straight into the background.
  - **Minimize to tray on close** — closing the window sends the app to the tray instead of quitting.
- **🔔 System Tray Integration:** Runs quietly in the tray, a preset quick-switch menu, and restore/exit controls
- **⌨️ Global Hotkeys:** Assign global keyboard shortcuts (working even when the app isn't focused) to trigger actions, with an easy "record by pressing" capture UI in Settings. Supports `Ctrl` / `Alt` / `Shift` / `Win` modifier combinations.

---

## 📸 Screenshot

<img width="1211" height="647" alt="image" src="https://github.com/user-attachments/assets/0b6e7fca-e61f-4e95-8237-0ab52e37421a" />




---

## 🚀 Download & Run (For Users)

The easiest way is to download the pre-compiled `.exe` file:

1. Go to the **[Releases](../../releases)** section on GitHub.
2. Download `Galaxy_70_Customizer.exe`
3. Run the executable 

---

## 🛠 Running from Source / Development

### Requirements:
- Python 3.8 or higher.
- Standard `tkinter` library (included by default in Python for Windows).
- Optional, for full functionality: `pystray` and `Pillow` (system tray icon & menu). If these aren't installed, the app falls back gracefully and the tray/minimize features are simply disabled.

### How to Run:
```bash
python eglx70.py
