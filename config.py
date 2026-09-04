# -------------------------------------------------------------
#  AirMouse  -  config.py
#  All tunable constants live here - change them freely.
# -------------------------------------------------------------

# -- Camera ---------------------------------------------------
CAMERA_INDEX      = 0        # 0 = default webcam
CAMERA_WIDTH      = 640      # capture resolution width
CAMERA_HEIGHT     = 480      # capture resolution height
CAMERA_FPS        = 60       # request 60 fps (halves latency if supported)
FLIP_HORIZONTAL   = True     # mirror so movement feels natural

# -- Hand tracking (MediaPipe) ---------------------------------
MAX_HANDS              = 1
DETECTION_CONFIDENCE   = 0.50     # responsive hand tracking
TRACKING_CONFIDENCE    = 0.50     # holds tracking through fast/angled moves

# -- Screen mapping --------------------------------------------
# Larger margin = smaller hand sweep covers the full screen.
FRAME_MARGIN_X = 0.20
FRAME_MARGIN_Y = 0.20

# -- One Euro Filter & 1000Hz Cursor Engine --------------------
# OEF_MIN_CUTOFF - smoothing floor at zero speed (kills micro-jitter/tremor).
# OEF_BETA       - speed coefficient: filter becomes instant on fast sweeps.
OEF_MIN_CUTOFF = 1.2
OEF_BETA       = 0.90
OEF_D_CUTOFF   = 1.0

# Asynchronous 1000Hz micro-stepping engine
SMOOTH_POLLING_RATE_HZ = 1000   # thread tick frequency
CURSOR_RESPONSIVENESS  = 85.0   # crisp, instant follow speed (no rubber-band lag)

# Dead-zone (pixels).  0 = completely fluid micro-movement.
DEAD_ZONE_PX = 0

# Max cursor speed cap (pixels/frame). High value prevents artificial speed limits.
MAX_CURSOR_SPEED_PX      = 800   # normal movement cap
DRAG_MAX_CURSOR_SPEED_PX = 800   # drag cap

# -- Cursor lock during pinch ----------------------------------
# When thumb-index distance falls below this the cursor freezes
# so the closing fingertip cannot drag the cursor during a click.
CURSOR_LOCK_THRESHOLD = 0.30   # palm-normalized ratio

# -- Gesture thresholds (Palm-Normalized 3D Ratios) -----------
PINCH_THRESHOLD              = 0.26   # thumb <-> index (Left Click / Drag)
RIGHT_CLICK_THRESHOLD        = 0.26   # thumb <-> middle (Right Click)
DOUBLE_CLICK_THRESHOLD       = 0.36   # thumb + index + middle all 3 pinched (Double Click)

# Frames pinch must be held before registered (debounce).
CLICK_DEBOUNCE_FRAMES        = 2

# Frames pinch must be released before next action is allowed.
CLICK_COOLDOWN_FRAMES        = 3

# Cooldown frames between consecutive double clicks
DOUBLE_CLICK_COOLDOWN_FRAMES = 15

# Frames pinch must be held continuously to become a drag.
DRAG_HOLD_FRAMES             = 16

# -- Debug overlay ---------------------------------------------
SHOW_DEBUG_WINDOW = True
DEBUG_WINDOW_NAME = "AirMouse - Debug (press Q to quit)"
DEBUG_WINDOW_X    = 10
DEBUG_WINDOW_Y    = 10
DEBUG_WINDOW_W    = 480
DEBUG_WINDOW_H    = 360

# -- Handedness ------------------------------------------------
ACTIVE_HAND = "Right"   # "Right" | "Left" | "Both"

# -- Scroll gesture --------------------------------------------
SCROLL_THRESHOLD       = 0.28   # palm-normalized ratio
SCROLL_DEBOUNCE_FRAMES = 3       # frames held before scroll activates
SCROLL_SENSITIVITY     = 10      # scroll wheel clicks per 100 px of hand travel
SCROLL_DEAD_ZONE_PX    = 8       # minimum vertical movement (px) before scrolling
