#!/usr/bin/env python3
# -------------------------------------------------------------
#  AirMouse  -  build_exe.py
#
#  Run this script to package AirMouse into a standalone .exe
#  (Windows) or binary (macOS/Linux) using PyInstaller.
#
#  Usage:
#      python build_exe.py
#
#  Output:
#      dist/AirMouse/AirMouse.exe   (Windows)
#      dist/AirMouse/AirMouse       (Linux/macOS)
# -------------------------------------------------------------

import subprocess
import sys
import os


def build():
    # Make sure PyInstaller is available
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # MediaPipe needs its data files bundled manually
    import mediapipe as mp
    mp_path = os.path.dirname(mp.__file__)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "main.py",
        "--name",        "AirMouse",
        "--onedir",                        # folder bundle (faster startup than --onefile)
        "--noconsole",                     # no terminal window on Windows
        "--add-data",   f"{mp_path}{os.pathsep}mediapipe",  # bundle mediapipe data
        "--hidden-import", "mediapipe",
        "--hidden-import", "cv2",
        "--hidden-import", "pyautogui",
        "--hidden-import", "pynput",
        "--collect-all", "mediapipe",      # grabs all mediapipe sub-packages & models
        "--collect-all", "cv2",
        "--clean",                         # wipe previous build artefacts
    ]

    print("\n[build] Running PyInstaller...\n")
    print(" ".join(cmd))
    print()
    subprocess.check_call(cmd)

    print("\n" + "="*60)
    print(" Build complete!")
    print(f" Executable: dist{os.sep}AirMouse{os.sep}AirMouse")
    print("="*60)
    print("\n To share with a friend:")
    print("   * Zip the entire  dist/AirMouse/  folder")
    print("   * They just unzip and double-click AirMouse.exe")
    print("   * No Python, no pip, no setup required.\n")


if __name__ == "__main__":
    build()
