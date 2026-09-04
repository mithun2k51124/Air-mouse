# -------------------------------------------------------------
#  AirMouse  -  debug_overlay.py
#
#  Draws a clean HUD onto the debug window so you can see
#  exactly what the app is detecting in real time.
# -------------------------------------------------------------

import cv2
import config

# Colours (BGR)
WHITE  = (255, 255, 255)
BLACK  = (0,   0,   0)
GREEN  = (0,   220, 80)
ORANGE = (0,   165, 255)
RED    = (50,  50,  230)
CYAN   = (255, 220, 0)
GREY   = (160, 160, 160)


def draw(frame, state: dict):
    """
    state keys:
      hand_found   bool
      left_dist    float
      right_dist   float
      events       list[str]
      screen_pos   (int, int)
      dragging     bool
      index_tip    (int, int) | None
      thumb_tip    (int, int) | None
      middle_tip   (int, int) | None
      fps          float
    """
    h, w = frame.shape[:2]

    # -- Active zone rectangle ---------------------------------
    mx = config.FRAME_MARGIN_X
    my = config.FRAME_MARGIN_Y
    z_x1 = int(w * mx);     z_y1 = int(h * my)
    z_x2 = int(w * (1-mx)); z_y2 = int(h * (1-my))
    cv2.rectangle(frame, (z_x1, z_y1), (z_x2, z_y2), GREY, 1)

    if not state.get("hand_found"):
        _text(frame, "No hand detected", w//2, h//2,
              color=ORANGE, center=True, scale=1.0)
        _draw_fps(frame, state.get("fps", 0))
        return

    # -- Fingertip dots + knuckle dot -------------------------
    for tip_key, color in [("index_tip", GREEN),
                            ("thumb_tip", ORANGE),
                            ("middle_tip", CYAN)]:
        pt = state.get(tip_key)
        if pt:
            cv2.circle(frame, pt, 8, color, -1)
            cv2.circle(frame, pt, 10, WHITE, 1)

    # INDEX_MCP knuckle - the actual cursor-control point
    mcp = state.get("index_mcp")
    if mcp:
        # Draw as a distinct yellow square so it's easy to spot
        YELLOW = (0, 230, 255)
        sz = 8
        cv2.rectangle(frame,
                      (mcp[0] - sz, mcp[1] - sz),
                      (mcp[0] + sz, mcp[1] + sz),
                      YELLOW, -1)
        cv2.rectangle(frame,
                      (mcp[0] - sz - 1, mcp[1] - sz - 1),
                      (mcp[0] + sz + 1, mcp[1] + sz + 1),
                      WHITE, 1)
        _text(frame, "CURSOR", mcp[0] + sz + 4, mcp[1] + 5,
              color=YELLOW, scale=0.45)

    # -- Pinch lines -------------------------------------------
    idx = state.get("index_tip")
    thm = state.get("thumb_tip")
    mid = state.get("middle_tip")

    ld = state.get("left_dist", 1.0)
    rd = state.get("right_dist", 1.0)

    if idx and thm:
        lc = GREEN if ld < config.PINCH_THRESHOLD else GREY
        cv2.line(frame, thm, idx, lc, 2)

    if mid and thm and rd < config.DOUBLE_CLICK_THRESHOLD * 1.5:
        mc = CYAN if rd < config.DOUBLE_CLICK_THRESHOLD else GREY
        cv2.line(frame, thm, mid, mc, 2)

    # -- Status panel (top-left) -------------------------------
    panel_lines = [
        f"Hand   : {state.get('detected_hand', '?')} (Active: {config.ACTIVE_HAND})",
        f"LeftP  : {ld:.2f}  {'PINCH' if ld < config.PINCH_THRESHOLD else ''}",
        f"RightP : {rd:.2f}  {'PINCH' if rd < config.RIGHT_CLICK_THRESHOLD else ''}",
        f"Screen : {state.get('screen_pos', ('?','?'))}",
        f"Drag   : {'ON' if state.get('dragging') else 'off'}",
        f"Scroll : {'ON' if state.get('scrolling') else 'off'}",
        f"Double : {'ON' if state.get('triple_pinch') else 'off'}",
    ]
    _panel(frame, panel_lines, x=10, y=10)

    # -- Event flash -------------------------------------------
    events = state.get("events", [])
    if events:
        def _fmt_evt(e):
            if isinstance(e, tuple) and len(e) == 2 and e[0] == "scroll":
                d = "UP" if e[1] > 0 else "DOWN"
                return f"SCROLL {d} ({abs(e[1])})"
            if isinstance(e, str):
                return e.upper().replace("_", " ")
            return str(e).upper()

        label = " + ".join(_fmt_evt(e) for e in events)
        color = GREEN
        lower = label.lower()
        if "double" in lower:
            color = CYAN
        elif "right" in lower:
            color = RED
        elif "drag" in lower:
            color = ORANGE
        elif "scroll" in lower:
            color = CYAN
        _text(frame, label, w//2, h - 40, color=color, center=True, scale=1.1, thickness=2)

    # -- Mode banners ------------------------------------------
    if state.get("dragging"):
        cv2.rectangle(frame, (0, 0), (w, h), ORANGE, 3)
        _text(frame, "DRAG MODE", w - 10, 30, color=ORANGE,
              scale=0.7, thickness=2, right_align=True)
    elif state.get("scrolling"):
        cv2.rectangle(frame, (0, 0), (w, h), CYAN, 3)
        _text(frame, "SCROLL MODE", w - 10, 30, color=CYAN,
              scale=0.7, thickness=2, right_align=True)

    _draw_fps(frame, state.get("fps", 0))


# -- Helpers ---------------------------------------------------

def _text(frame, text, x, y, color=WHITE, scale=0.6, thickness=1,
          center=False, right_align=False):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    if center:
        x -= tw // 2
    elif right_align:
        x -= tw
    # Drop shadow
    cv2.putText(frame, text, (x+1, y+1), font, scale, BLACK, thickness+1, cv2.LINE_AA)
    cv2.putText(frame, text, (x,   y),   font, scale, color,  thickness,   cv2.LINE_AA)


def _panel(frame, lines, x, y, line_h=22):
    for i, line in enumerate(lines):
        _text(frame, line, x, y + i * line_h, color=WHITE, scale=0.55)


def _draw_fps(frame, fps):
    h = frame.shape[0]
    _text(frame, f"FPS {fps:.1f}", 10, h - 10, color=GREY, scale=0.5)
