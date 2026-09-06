import subprocess
import sys

def build_exe():
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller не найден. Установка...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    import PyInstaller.__main__

    print("Запуск компиляции в .exe с вшитой иконкой...")
    
    PyInstaller.__main__.run([
        'eglx70.py',
        '--onefile',                   # Все в один .exe
        '--noconsole',                 # Без черного окна консоли
        '--name=Galaxy 70 Customizer',   # Имя итогового файла
        '--icon=icon.ico',         # Вшивает иконку в сам .exe файл (для Проводника)
        '--add-data=icon.ico;.',    # Вшивает иконку внутрь .exe (для окна Tkinter)
        '--clean',
    ])

    print("\nСборка завершена! Готовый файл: dist/Galaxy70Customizer.exe")

if __name__ == "__main__":
    build_exe()