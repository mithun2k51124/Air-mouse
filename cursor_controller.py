# -------------------------------------------------------------
#  AirMouse  -  cursor_controller.py
#
#  Pipeline:
#    1. Camera px  -> screen px  (linear mapping with margin zone)
#    2. Aim Assist Filter        (Dynamic Tremor Dampener over icons & buttons)
#    3. One Euro Filter          (Adaptive velocity low-pass filter)
#    4. 1000Hz Background Engine (Sub-millisecond glide interpolation)
#    5. Windows High-DPI Output  (Per-Monitor v2 1:1 hardware events)
# -------------------------------------------------------------

import math
import ctypes
import threading
import time
import pyautogui
import config

# Configure PyAutoGUI for instant zero-overhead execution
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# -- Win32 mouse control & DPI Awareness -----------------------
_user32 = ctypes.windll.user32
_winmm  = ctypes.windll.winmm

# Enable Per-Monitor v2 DPI Awareness so coordinates match physical screen pixels (e.g. 2880x1800)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        _user32.SetProcessDPIAware()
    except Exception:
        pass

_MOUSEEVENTF_LEFTDOWN  = 0x0002
_MOUSEEVENTF_LEFTUP    = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP   = 0x0010
_MOUSEEVENTF_WHEEL     = 0x0800   # vertical scroll wheel
_WHEEL_DELTA           = 120      # one standard scroll click

# Virtual key codes for Win+D (minimize all windows)
_VK_LWIN         = 0x5B
_VK_D            = 0x44
_KEYEVENTF_KEYUP = 0x0002

def _move(x: int, y: int):
    """Fastest possible cursor move - direct Win32 SetCursorPos."""
    _user32.SetCursorPos(x, y)

def _mouse_down():
    _user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

def _mouse_up():
    _user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def _scroll(clicks: int):
    """Scroll the wheel. Positive = up, negative = down."""
    _user32.mouse_event(_MOUSEEVENTF_WHEEL, 0, 0,
                        ctypes.c_int(clicks * _WHEEL_DELTA).value, 0)

def _minimize_all():
    """Send Win+D to minimize all windows (show desktop)."""
    _user32.keybd_event(_VK_LWIN, 0, 0, 0)
    _user32.keybd_event(_VK_D,    0, 0, 0)
    _user32.keybd_event(_VK_D,    0, _KEYEVENTF_KEYUP, 0)
    _user32.keybd_event(_VK_LWIN, 0, _KEYEVENTF_KEYUP, 0)

def _screen_size():
    return (_user32.GetSystemMetrics(0),   # SM_CXSCREEN
            _user32.GetSystemMetrics(1))   # SM_CYSCREEN


# -- Aim Assist & Dynamic Tremor Dampener ----------------------
class AimAssistFilter:
    """
    Stabilizes hand tremor when hovering near buttons or clickable items,
    while unlocking full 1:1 speed during fast navigation sweeps.
    """
    def __init__(self):
        self._prev_x = None
        self._prev_y = None
        self._out_x  = None
        self._out_y  = None

    def filter(self, x: float, y: float, dt: float = 0.033):
        if self._out_x is None:
            self._prev_x, self._prev_y = x, y
            self._out_x,  self._out_y  = x, y
            return x, y

        dx = x - self._prev_x
        dy = y - self._prev_y
        self._prev_x, self._prev_y = x, y

        speed = math.hypot(dx, dy) / max(dt, 1e-4)

        # Micro-tremor stabilization (hovering / precision aiming):
        if speed < 30.0:
            # Heavy stabilizing dampener: keeps cursor locked on icons/buttons
            alpha = 0.06 + 0.14 * (speed / 30.0)
        elif speed < 120.0:
            # Smooth precision aiming
            t = (speed - 30.0) / 90.0
            alpha = 0.20 + 0.65 * t
        else:
            # Fast movement: instant 1:1 tracking
            alpha = 0.95

        self._out_x += (x - self._out_x) * alpha
        self._out_y += (y - self._out_y) * alpha
        return self._out_x, self._out_y


# -- One Euro Filter -------------------------------------------
class _LowPassFilter:
    def __init__(self, cutoff_hz: float, rate: float):
        self._rate   = rate
        self._alpha  = self._calc(cutoff_hz, rate)
        self._prev   = None

    @staticmethod
    def _calc(cutoff: float, rate: float) -> float:
        te  = 1.0 / rate
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def filter(self, x: float, cutoff_hz: float = None) -> float:
        if cutoff_hz is not None:
            self._alpha = self._calc(cutoff_hz, self._rate)
        if self._prev is None:
            self._prev = x
            return x
        y = self._alpha * x + (1.0 - self._alpha) * self._prev
        self._prev = y
        return y


class OneEuroFilter:
    """Adaptive 1-D low-pass filter. One instance per axis."""

    def __init__(self, rate: float = 30.0):
        self._rate   = rate
        self._x_filt = _LowPassFilter(config.OEF_MIN_CUTOFF, rate)
        self._d_filt = _LowPassFilter(config.OEF_D_CUTOFF,   rate)
        self._prev   = None

    def filter(self, x: float) -> float:
        dx      = 0.0 if self._prev is None else (x - self._prev) * self._rate
        dx_hat  = self._d_filt.filter(dx)
        cutoff  = config.OEF_MIN_CUTOFF + config.OEF_BETA * abs(dx_hat)
        x_hat   = self._x_filt.filter(x, cutoff_hz=cutoff)
        self._prev = x_hat
        return x_hat


# -- CursorController -----------------------------------------

class CursorController:
    """
    High-Performance 1000Hz Asynchronous Cursor Engine with Aim Assist.
    """

    def __init__(self, frame_w: int, frame_h: int, rate: float = 30.0):
        self._screen_w, self._screen_h = _screen_size()
        self._frame_w  = frame_w
        self._frame_h  = frame_h

        # Active zone (inner region of camera frame)
        mx = config.FRAME_MARGIN_X
        my = config.FRAME_MARGIN_Y
        self._zx1 = frame_w * mx
        self._zy1 = frame_h * my
        self._zx2 = frame_w * (1.0 - mx)
        self._zy2 = frame_h * (1.0 - my)
        self._zw  = self._zx2 - self._zx1
        self._zh  = self._zy2 - self._zy1

        # Filters
        self._aim_assist = AimAssistFilter()
        self._oef_x      = OneEuroFilter(rate)
        self._oef_y      = OneEuroFilter(rate)

        # Smooth position state
        init_x = float(self._screen_w // 2)
        init_y = float(self._screen_h // 2)

        self._target_x = init_x
        self._target_y = init_y
        self._cur_x    = init_x
        self._cur_y    = init_y
        self._last_sent_x = int(init_x)
        self._last_sent_y = int(init_y)

        self._lock = threading.Lock()
        self._dragging = False
        self._clicking = False
        self._running  = True

        # Enable 1ms timer resolution in Windows
        _winmm.timeBeginPeriod(1)

        # Start 1000Hz asynchronous micro-stepping thread
        self._worker = threading.Thread(target=self._interpolation_loop, daemon=True)
        self._worker.start()

    def _interpolation_loop(self):
        """Asynchronous high-frequency cursor interpolation thread (~1000Hz)."""
        last_t = time.perf_counter()

        while self._running:
            now = time.perf_counter()
            dt = now - last_t
            last_t = now

            if dt > 0.05:  # clamp extreme pauses
                dt = 0.05

            with self._lock:
                if self._clicking:
                    time.sleep(0.001)
                    continue
                tx = self._target_x
                ty = self._target_y

            # Smooth exponential decay toward target position
            k = config.CURSOR_RESPONSIVENESS
            alpha = 1.0 - math.exp(-k * dt)

            self._cur_x += (tx - self._cur_x) * alpha
            self._cur_y += (ty - self._cur_y) * alpha

            # Commit to Windows cursor if sub-pixel movement crossed pixel boundary
            ix = int(round(self._cur_x))
            iy = int(round(self._cur_y))

            if ix != self._last_sent_x or iy != self._last_sent_y:
                self._last_sent_x = ix
                self._last_sent_y = iy
                _move(ix, iy)

            time.sleep(0.001)

    # -- Public API --------------------------------------------

    def move(self, cam_x: int, cam_y: int,
             pinch_dist: float = 1.0, dragging: bool = False):
        """
        cam_x, cam_y - INDEX_TIP pixel position in camera frame.
        pinch_dist   - normalised thumb-index distance.
        dragging     - True while drag is active (bypass cursor lock).
        """
        # 1. Cursor lock during tight pinch
        if pinch_dist < config.CURSOR_LOCK_THRESHOLD and not dragging:
            return

        # 2. Map to screen space
        raw_x, raw_y = self._cam_to_screen(cam_x, cam_y)

        # 3. Aim Assist Tremor Dampener (kills shaking near icons/buttons)
        ax, ay = self._aim_assist.filter(raw_x, raw_y)

        # 4. One Euro Filter (Adaptive velocity smoothing)
        sx = self._oef_x.filter(ax)
        sy = self._oef_y.filter(ay)

        # 5. Per-frame speed cap
        cap = config.DRAG_MAX_CURSOR_SPEED_PX if dragging \
              else config.MAX_CURSOR_SPEED_PX
        with self._lock:
            dx, dy = sx - self._target_x, sy - self._target_y
            spd = math.hypot(dx, dy)
            if spd > cap and spd > 1e-5:
                f  = cap / spd
                sx = self._target_x + dx * f
                sy = self._target_y + dy * f

            # Update target for the 1000Hz background thread
            self._target_x = sx
            self._target_y = sy

    def left_click(self):
        ix = int(round(self._cur_x))
        iy = int(round(self._cur_y))
        with self._lock:
            self._target_x = float(ix)
            self._target_y = float(iy)
            self._cur_x    = float(ix)
            self._cur_y    = float(iy)
            self._clicking = True
        try:
            _move(ix, iy)
            pyautogui.click(x=ix, y=iy)
        finally:
            with self._lock:
                self._clicking = False

    def double_click(self):
        """Perform a standard double-click locked at the exact current cursor coordinate."""
        ix = int(round(self._cur_x))
        iy = int(round(self._cur_y))

        # Freeze 1000Hz thread for duration so no hand drift cancels the double click
        with self._lock:
            self._target_x = float(ix)
            self._target_y = float(iy)
            self._cur_x    = float(ix)
            self._cur_y    = float(iy)
            self._clicking = True

        try:
            _move(ix, iy)
            pyautogui.doubleClick(x=ix, y=iy, interval=0.06)
        finally:
            with self._lock:
                self._clicking = False

    def right_click(self):
        ix = int(round(self._cur_x))
        iy = int(round(self._cur_y))
        with self._lock:
            self._target_x = float(ix)
            self._target_y = float(iy)
            self._cur_x    = float(ix)
            self._cur_y    = float(iy)
            self._clicking = True
        try:
            _move(ix, iy)
            pyautogui.rightClick(x=ix, y=iy)
        finally:
            with self._lock:
                self._clicking = False

    def drag_start(self):
        _mouse_down()
        self._dragging = True

    def drag_end(self):
        _mouse_up()
        self._dragging = False

    def scroll(self, clicks: int):
        """Scroll the mouse wheel.  Positive = up, negative = down."""
        _scroll(clicks)

    def minimize_all(self):
        """Send Win+D to minimize all open windows (show desktop only)."""
        _minimize_all()

    def stop(self):
        """Stop the 1000Hz background thread and restore timer resolution."""
        self._running = False
        if self._worker.is_alive():
            self._worker.join(timeout=0.1)
        _winmm.timeEndPeriod(1)

    @property
    def smooth_pos(self):
        return int(round(self._cur_x)), int(round(self._cur_y))

    @property
    def is_dragging(self):
        return self._dragging

    # -- Private -----------------------------------------------

    def _cam_to_screen(self, cam_x: int, cam_y: int):
        nx = (cam_x - self._zx1) / self._zw
        ny = (cam_y - self._zy1) / self._zh
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))
        return nx * self._screen_w, ny * self._screen_h
