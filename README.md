# 🖱️ AirMouse - AI Vision Hand-Controlled Mouse

Control your PC with hand gestures through your webcam — no physical mouse needed. Features a **1000Hz gaming-grade cursor engine**, **Adaptive Aim-Assist tremor dampener**, and **3D palm-normalized gesture recognition**.

---

## 🖐️ Gesture Reference

| Action | Finger Gesture | Description |
| :--- | :--- | :--- |
| **Move Cursor** | **Index Fingertip** | Point and move smoothly across the screen. |
| **Left Click** | **Thumb + Index** *(only)* | Quick pinch & release (Middle finger open). |
| **Right Click** | **Thumb + Middle** *(only)* | Quick pinch & release (Index finger open). |
| **Double Click** | **Thumb + Index + Middle** *(all 3)* | Pinch all 3 fingers together (opens desktop apps/folders). |
| **Click & Drag** | **Hold Thumb + Index** | Pinch thumb + index and hold (>300 ms) to drag; release to drop. |
| **Scroll** | **Thumb + Ring** | Pinch thumb + ring together and move hand up/down. |

---

## 🚀 Quick Start (Running from Source)

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Launch
Double-click `run.bat` or run:
```powershell
python main.py
```

---

## 📦 How to Share with Friends

### Option 1: Standalone Windows App (.exe) — *Recommended for Non-Programmers*
Your friends won't need to install Python or any libraries.

1. Build the standalone executable package:
   ```powershell
   .venv\Scripts\python.exe build_exe.py
   ```
2. Once complete, you will see a `dist/AirMouse/` folder.
3. **Right-click `dist/AirMouse` → Send to → Compressed (zipped) folder**.
4. Send the `.zip` file to your friends! They just unzip and double-click **`AirMouse.exe`** to run.

---

### Option 2: Share Source Code (GitHub / Zip) — *Best for Developers*
1. Zip the project folder (excluding `.venv` and `__pycache__`).
2. Share the zip or upload to GitHub.
3. Your friend just unzips, runs `pip install -r requirements.txt`, and double-clicks `run.bat`.
