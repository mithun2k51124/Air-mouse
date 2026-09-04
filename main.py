#!/usr/bin/env python3
# -------------------------------------------------------------
#  AirMouse  -  main.py
#
#  Entry point.  Runs the main capture-process-act loop.
#
#  GESTURE CONTROL:
#    👍 Thumbs Up  (held ~0.33 s) -> START mouse control
#    👎 Thumbs Down(held ~0.33 s) -> QUIT the application
#
#  Architecture:
#
#    -------------     RGB frame     --------------
#   |  OpenCV cam | -------------   | HandTracker  |  (MediaPipe)
#   +-------------                  +------ -------
#                                          | landmarks + handedness
#                               ----------- ------------------------
#                              v           v                         v
#                        index_mcp   pinch dists              handedness filter
#                        (cursor)   (INDEX_TIP)                (right-hand only)
#                              |           |
#                              v           v
#                      CursorController  GestureDetector
#                   (OEF + clamp + move)  (state machine)
#                              |           |
#                              +--- events
#                                     |
#                    click / drag / scroll / fist / move
#
#  KEY DESIGN: cursor position is driven by INDEX_MCP (knuckle
#  base, landmark 5), NOT the fingertip.  The knuckle is:
#   * 2-3x more stable than the tip (less tremor amplification)
#   * Barely moves during a pinch (no cursor drift on click)
#   Pinch detection still uses INDEX_TIP <-> THUMB_TIP distance.
#
#  HANDEDNESS: MediaPipe reports handedness in camera (unflipped)
#  coordinates.  Because FLIP_HORIZONTAL=True the labels are
#  mirrored - MediaPipe "Left" = user's right hand on screen.
#  Only the configured ACTIVE_HAND (default "Right") is processed.
#
#  SCROLL: thumb <-> ring-finger pinch + vertical hand movement.
#  Natural scroll: hand up -> page scrolls up.
#
#  FIST: all fingertips near wrist -> Win+D (minimize all, once).
# -------------------------------------------------------------

import sys
import time
import cv2

import config
from hand_tracker     import (HandTracker, INDEX_TIP, INDEX_MCP,
                               THUMB_TIP, MIDDLE_TIP, RING_TIP,
                               WRIST, PINKY_TIP)
from gesture_detector import GestureDetector
from cursor_controller import CursorController
from debug_overlay    import draw as draw_overlay


# ── App states ────────────────────────────────────────────────
STATE_WAITING  = "waiting"   # Show splash, wait for 👍
STATE_RUNNING  = "running"   # Normal mouse-control mode


# ── Splash / overlay helpers ───────────────────────────────────

def _splash_text(frame, text, x, y, color=(255, 255, 255),
                 scale=0.7, thickness=1, center=False, right_align=False):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    if center:
        x -= tw // 2
    elif right_align:
        x -= tw
    cv2.putText(frame, text, (x + 1, y + 1), font, scale,
                (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), font, scale,
                color, thickness, cv2.LINE_AA)


def _draw_arc(frame, cx, cy, radius, progress, color, label="Hold..."):
    """Draw a circular progress arc (clockwise from top)."""
    cv2.circle(frame, (cx, cy), radius, (50, 50, 50), 3)
    if progress > 0.0:
        angle = int(360 * progress)
        cv2.ellipse(frame, (cx, cy), (radius, radius),
                    -90, 0, angle, color, 4, cv2.LINE_AA)
    if label and progress > 0.0:
        _splash_text(frame, label, cx, cy + radius + 16,
                     color=color, scale=0.45, center=True)


def _draw_splash(frame, detector, hand_found):
    """Full-frame WAITING overlay: dark tint + 👍 instruction + progress arc."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (15, 15, 30), -1)
    cv2.addWeighted(overlay, 0.58, frame, 0.42, 0, frame)

    # Title
    _splash_text(frame, "AirMouse", w // 2, h // 5,
                 color=(120, 220, 255), scale=1.6, thickness=3, center=True)

    # Instruction
    _splash_text(frame, "Show  THUMBS UP  to start",
                 w // 2, h // 5 + 48,
                 color=(200, 200, 200), scale=0.70, center=True)
    _splash_text(frame, "Show  THUMBS DOWN  to quit anytime",
                 w // 2, h // 5 + 72,
                 color=(140, 140, 180), scale=0.55, center=True)

    # Big thumb emoji as text
    _splash_text(frame, "THUMBS UP", w // 2, h // 2 - 10,
                 color=(80, 220, 120), scale=1.1, thickness=2, center=True)

    # Progress arc
    progress = detector.thumbs_up_progress
    _draw_arc(frame, w // 2, h // 2 + 55, 36,
              progress, (80, 220, 120), label="Hold...")

    if not hand_found:
        _splash_text(frame, "No hand detected - show your hand!",
                     w // 2, h - 28,
                     color=(80, 80, 200), scale=0.58, center=True)


def _draw_quit_hint(frame, detector):
    """Small 👎 progress hint in the bottom-right corner during RUNNING state."""
    h, w = frame.shape[:2]
    progress = detector.thumbs_down_progress
    if progress > 0.0:
        _draw_arc(frame, w - 44, h - 44, 28,
                  progress, (60, 60, 220), label="")
        _splash_text(frame, "QUIT", w - 44, h - 44,
                     color=(60, 60, 220), scale=0.5, thickness=1, center=True)
    else:
        _splash_text(frame, "Thumbs Down = Quit", w - 8, h - 10,
                     color=(70, 70, 130), scale=0.42,
                     center=False, right_align=True)


def _user_hand(mp_label: str) -> str:
    """
    Return the user's real hand from MediaPipe's handedness label.

    The frame is flipped (FLIP_HORIZONTAL=True) BEFORE being passed to
    MediaPipe, so MediaPipe already sees the mirrored image and returns
    the anatomically correct hand label directly:
      MediaPipe "Right" -> user's RIGHT hand
      MediaPipe "Left"  -> user's LEFT  hand
    No inversion needed.
    """
    return mp_label   # pass through as-is


def main():
    # -- Camera setup -----------------------------------------
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[AirMouse] ERROR: Cannot open camera {config.CAMERA_INDEX}")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)

    ret, sample = cap.read()
    if not ret:
        print("[AirMouse] ERROR: Cannot read from camera.")
        sys.exit(1)
    frame_h, frame_w = sample.shape[:2]
    print(f"[AirMouse] Camera: {frame_w}x{frame_h}")

    # -- Module init -------------------------------------------
    tracker    = HandTracker()
    detector   = GestureDetector()
    cursor     = CursorController(frame_w, frame_h)

    print("[AirMouse] WAITING - show THUMBS UP  to START mouse control.")
    print("[AirMouse]           show THUMBS DOWN anytime to QUIT.")
    print(f"[AirMouse] Active hand: {config.ACTIVE_HAND}")
    if config.SHOW_DEBUG_WINDOW:
        print("[AirMouse] Debug window open - press Q or ESC as keyboard fallback.")

    # -- Debug window ------------------------------------------
    if config.SHOW_DEBUG_WINDOW:
        cv2.namedWindow(config.DEBUG_WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(config.DEBUG_WINDOW_NAME,
                         config.DEBUG_WINDOW_W, config.DEBUG_WINDOW_H)
        cv2.moveWindow(config.DEBUG_WINDOW_NAME,
                       config.DEBUG_WINDOW_X, config.DEBUG_WINDOW_Y)

    # -- FPS counter -------------------------------------------
    fps       = 0.0
    fps_alpha = 0.1
    t_prev    = time.perf_counter()

    # -- App state: start WAITING for 👍 -----------------------
    app_state = STATE_WAITING

    # -- Main loop ---------------------------------------------
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[AirMouse] Frame grab failed - retrying...")
            continue

        if config.FLIP_HORIZONTAL:
            frame = cv2.flip(frame, 1)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # -- Hand tracking (runs in every state) ---------------
        hand_found, mp_results = tracker.process(rgb)

        # Raw landmarks for control-gesture detection
        raw_lm = tracker.landmarks   # NormalizedLandmark list or None

        # Control gesture (👍 / 👎) checked in every state
        ctrl = detector.update_control_gesture(raw_lm)

        # ── WAITING state: show splash, wait for 👍 ──────────
        if app_state == STATE_WAITING:
            if ctrl == "thumbs_up":
                print("[AirMouse] THUMBS UP detected - STARTING mouse control!")
                app_state = STATE_RUNNING
                detector.__init__()   # reset so thumb-up doesn't bleed into clicks

            if config.SHOW_DEBUG_WINDOW:
                tracker.draw_landmarks(frame, mp_results)
                _draw_splash(frame, detector, hand_found)
                t_now  = time.perf_counter()
                fps    = fps_alpha * (1.0 / max(t_now - t_prev, 1e-6)) + (1 - fps_alpha) * fps
                t_prev = t_now
                cv2.imshow(config.DEBUG_WINDOW_NAME, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    print("[AirMouse] Quit via keyboard.")
                    break
            continue   # skip all mouse-control work

        # ── RUNNING state: normal mouse control ───────────────
        if ctrl == "thumbs_down":
            print("[AirMouse] THUMBS DOWN detected - QUITTING!")
            break

        events     = []
        left_dist  = 1.0
        right_dist = 1.0
        ring_dist  = 1.0
        index_tip  = None
        index_mcp  = None   # knuckle - drives cursor
        thumb_tip  = None
        middle_tip = None
        ring_tip   = None
        detected_hand = None

        if hand_found:
            # Handedness filter
            mp_label      = tracker.handedness
            detected_hand = _user_hand(mp_label)

            if (config.ACTIVE_HAND != "Both"
                    and detected_hand != config.ACTIVE_HAND):
                hand_found = False

        if hand_found:
            index_tip  = tracker.get_tip(INDEX_TIP,  frame_w, frame_h)
            index_mcp  = tracker.get_tip(INDEX_MCP,  frame_w, frame_h)
            thumb_tip  = tracker.get_tip(THUMB_TIP,  frame_w, frame_h)
            middle_tip = tracker.get_tip(MIDDLE_TIP, frame_w, frame_h)
            ring_tip   = tracker.get_tip(RING_TIP,   frame_w, frame_h)
            wrist_px   = tracker.get_tip(WRIST,      frame_w, frame_h)  # noqa: F841

            #  left_dist:  thumb <-> index  -> LEFT CLICK / DRAG
            #  right_dist: thumb <-> middle -> RIGHT CLICK
            #  ring_dist:  thumb <-> ring   -> SCROLL
            left_dist  = tracker.pinch_distance(THUMB_TIP, INDEX_TIP)
            right_dist = tracker.pinch_distance(THUMB_TIP, MIDDLE_TIP)
            ring_dist  = tracker.pinch_distance(THUMB_TIP, RING_TIP)
            im_dist    = tracker.pinch_distance(INDEX_TIP, MIDDLE_TIP)

            ring_y_px = ring_tip[1] if ring_tip else None

            events = detector.update(
                pinch_dist = left_dist,
                right_dist = right_dist,
                ring_dist  = ring_dist,
                ring_y_px  = ring_y_px,
                im_dist    = im_dist,
            )

            for evt in events:
                if   evt == "left_click":    cursor.left_click()
                elif evt == "double_click":
                    print("[AirMouse] 3-Finger Pinch - Double Click!")
                    cursor.double_click()
                elif evt == "right_click":   cursor.right_click()
                elif evt == "drag_start":    cursor.drag_start()
                elif evt == "drag_end":      cursor.drag_end()
                elif (isinstance(evt, tuple)
                        and len(evt) == 2
                        and evt[0] == "scroll"):
                    cursor.scroll(evt[1])

            if index_tip and not detector.is_scrolling:
                cursor.move(*index_tip,
                            pinch_dist=left_dist,
                            dragging=cursor.is_dragging)

        # -- Debug window --------------------------------------
        if config.SHOW_DEBUG_WINDOW:
            tracker.draw_landmarks(frame, mp_results)

            t_now  = time.perf_counter()
            fps    = fps_alpha * (1.0 / max(t_now - t_prev, 1e-6)) + (1 - fps_alpha) * fps
            t_prev = t_now

            draw_overlay(frame, {
                "hand_found":    hand_found,
                "left_dist":     left_dist,
                "right_dist":    right_dist,
                "events":        events,
                "screen_pos":    cursor.smooth_pos,
                "dragging":      cursor.is_dragging,
                "scrolling":     detector.is_scrolling,
                "triple_pinch":  detector.is_triple_pinching,
                "index_tip":     index_tip,
                "index_mcp":     index_mcp,
                "thumb_tip":     thumb_tip,
                "middle_tip":    middle_tip,
                "fps":           fps,
                "detected_hand": detected_hand,
            })

            # 👎 quit-progress hint in bottom-right
            _draw_quit_hint(frame, detector)

            cv2.imshow(config.DEBUG_WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                print("[AirMouse] Quit via keyboard.")
                break

    # -- Cleanup -----------------------------------------------
    if cursor.is_dragging:
        cursor.drag_end()

    cursor.stop()
    tracker.close()
    cap.release()
    cv2.destroyAllWindows()
    print("[AirMouse] Stopped cleanly.")


if __name__ == "__main__":
    main()
