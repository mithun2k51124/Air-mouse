# AirMouse - gesture_detector.py
#
# Stateful gesture detector.
# Receives raw 3D palm-normalized pinch distances every frame and emits events:
#   "left_click"   - 2-finger pinch (thumb + index) quick tap & release
#   "right_click"  - 2-finger pinch (thumb + middle) quick tap & release
#   "double_click" - 3-finger pinch (thumb + index + middle pinched together)
#   "drag_start"   - 2-finger pinch hold (thumb + index)
#   "drag_end"     - Release after drag
#   ("scroll", delta) - Thumb + ring pinch + vertical movement
#
# Control gestures (detected via detect_control_gesture):
#   "thumbs_up"   - 👍  Thumb pointing UP,   other fingers curled -> START
#   "thumbs_down" - 👎  Thumb pointing DOWN, other fingers curled -> QUIT

import math
import config

# How many consecutive frames the thumb gesture must be held before firing
CONTROL_GESTURE_HOLD_FRAMES = 20   # ~0.33 s at 60 fps

# Landmark indices (mirrors hand_tracker.py constants to avoid circular import)
_WRIST      = 0
_THUMB_TIP  = 4
_THUMB_MCP  = 2
_INDEX_TIP  = 8
_INDEX_MCP  = 5
_MIDDLE_TIP = 12
_MIDDLE_MCP = 9
_RING_TIP   = 16
_RING_MCP   = 13
_PINKY_TIP  = 20
_PINKY_MCP  = 17


class GestureDetector:
    """
    Frame-by-frame gesture state machine.

    Gestures:
      - Left Click:   Single pinch with thumb + index finger (Middle finger open).
      - Right Click:  Single pinch with thumb + middle finger (Index finger open).
      - Double Click: 3-finger pinch with thumb + index + middle fingers together.
      - Drag:         Hold pinch (thumb + index) for >= DRAG_HOLD_FRAMES.
      - Scroll:       Pinch thumb + ring finger and move hand vertically.
    """

    def __init__(self):
        # 2-Finger Pinch state (Thumb + Index: Left Click / Drag)
        self._left_pinch_frames    = 0
        self._left_release_frames  = 0
        self._dragging             = False
        self._drag_activated       = False

        # 2-Finger Pinch state (Thumb + Middle: Right Click)
        self._right_pinch_frames   = 0
        self._right_release_frames = 0

        # 3-Finger Pinch state (Thumb + Index + Middle: Double Click)
        self._triple_pinch_frames  = 0
        self._triple_release_frames= 0
        self._triple_fired         = False
        self._triple_active        = False

        # Post-triple cooldown to lock out accidental single clicks on release
        self._cooldown_frames      = 0

        # Scroll state (Thumb + Ring)
        self._sc_pinch_frames      = 0
        self._sc_active            = False
        self._sc_prev_y            = None
        self._sc_accumulator       = 0.0

        # Control gesture hold counters (thumbs up / down debounce)
        self._thumbs_up_frames   = 0
        self._thumbs_down_frames = 0

    # Public API

    def update(self, pinch_dist, right_dist=1.0, ring_dist=1.0,
               ring_y_px=None, im_dist=None, **kwargs):
        """
        Args:
            pinch_dist: thumb-index distance (Left Click / Drag)
            right_dist: thumb-middle distance (Right Click)
            ring_dist:  thumb-ring distance (Scroll activation)
            ring_y_px:  ring fingertip Y in camera pixels (scroll delta)
            im_dist:    index-middle distance (confirms 3 fingers together)

        Returns:
            List of zero or more event strings or tuples:
            "left_click", "right_click", "double_click", "drag_start", "drag_end",
            ("scroll", delta_clicks) where positive=up and negative=down
        """
        events = []

        if self._cooldown_frames > 0:
            self._cooldown_frames -= 1

        d_ti = pinch_dist   # thumb <-> index
        d_tm = right_dist   # thumb <-> middle
        d_tr = ring_dist    # thumb <-> ring
        d_im = im_dist if im_dist is not None else 1.0  # index <-> middle

        thresh_3_enter = config.DOUBLE_CLICK_THRESHOLD          # ~0.35
        thresh_3_exit  = config.DOUBLE_CLICK_THRESHOLD * 1.30   # ~0.45

        # ------------------------------------------------------
        # 1. Track 3-Finger Pinch State (Double Click)
        # ------------------------------------------------------
        is_triple_contact = (d_ti < thresh_3_enter
                             and d_tm < thresh_3_enter
                             and (im_dist is None or d_im < thresh_3_enter * 1.3))

        if not self._triple_active:
            if is_triple_contact:
                self._triple_active = True
                self._triple_pinch_frames = 1
                self._triple_release_frames = 0
        else:
            if d_ti > thresh_3_exit or d_tm > thresh_3_exit:
                self._triple_release_frames += 1
                if self._triple_release_frames >= config.CLICK_COOLDOWN_FRAMES:
                    self._triple_active = False
                    self._triple_fired = False
                    self._triple_pinch_frames = 0
            else:
                self._triple_pinch_frames += 1
                self._triple_release_frames = 0

        # Trigger Double Click strictly once per 3-finger pinch
        if self._triple_active:
            self._left_pinch_frames  = 0
            self._right_pinch_frames = 0

            if (self._triple_pinch_frames >= config.CLICK_DEBOUNCE_FRAMES
                    and not self._triple_fired):
                self._triple_fired    = True
                self._cooldown_frames = config.DOUBLE_CLICK_COOLDOWN_FRAMES
                events.append("double_click")

        # ------------------------------------------------------
        # 2. Track 2-Finger Pinch: Thumb + Index (Left Click / Drag)
        #    Requires Middle finger to be CLEARLY OPEN (d_tm > 0.38)
        # ------------------------------------------------------
        is_left_pinch = (d_ti < config.PINCH_THRESHOLD
                         and d_tm > thresh_3_enter * 1.08
                         and not self._triple_active
                         and self._cooldown_frames == 0)

        if is_left_pinch:
            self._left_pinch_frames += 1
            self._left_release_frames = 0

            # Drag activation (long hold)
            if (self._left_pinch_frames >= config.DRAG_HOLD_FRAMES
                    and not self._drag_activated):
                self._drag_activated = True
                self._dragging       = True
                events.append("drag_start")

        else:
            prev_left_frames = self._left_pinch_frames
            self._left_pinch_frames = 0
            self._left_release_frames += 1

            # Release after drag
            if self._dragging and self._left_release_frames >= config.CLICK_DEBOUNCE_FRAMES:
                self._dragging       = False
                self._drag_activated = False
                events.append("drag_end")

            # Release after quick single pinch -> Left Click
            elif (prev_left_frames >= config.CLICK_DEBOUNCE_FRAMES
                  and not self._drag_activated
                  and not self._triple_active
                  and not self._triple_fired
                  and self._cooldown_frames == 0):
                events.append("left_click")

        # ------------------------------------------------------
        # 3. Track 2-Finger Pinch: Thumb + Middle (Right Click)
        #    Requires Index finger to be CLEARLY OPEN (d_ti > 0.38)
        # ------------------------------------------------------
        is_right_pinch = (d_tm < config.RIGHT_CLICK_THRESHOLD
                          and d_ti > thresh_3_enter * 1.08
                          and not self._triple_active
                          and not self._dragging
                          and self._cooldown_frames == 0)

        if is_right_pinch:
            self._right_pinch_frames += 1
            self._right_release_frames = 0
        else:
            prev_right_frames = self._right_pinch_frames
            self._right_pinch_frames = 0
            self._right_release_frames += 1

            # Release after quick right pinch -> Right Click
            if (prev_right_frames >= config.CLICK_DEBOUNCE_FRAMES
                    and not self._triple_active
                    and not self._triple_fired
                    and self._cooldown_frames == 0):
                events.append("right_click")

        # ------------------------------------------------------
        # 4. Scroll Handler (Thumb + Ring)
        # ------------------------------------------------------
        events += self._handle_scroll(d_tr, ring_y_px)

        return events

    @property
    def is_dragging(self):
        return self._dragging

    @property
    def is_scrolling(self):
        return self._sc_active

    @property
    def is_triple_pinching(self):
        return self._triple_active

    # ------------------------------------------------------------------
    # Control gesture detection  (👍 Start / 👎 Quit)
    # ------------------------------------------------------------------

    def update_control_gesture(self, landmarks):
        """
        Call every frame with the raw MediaPipe NormalizedLandmark list
        (or None if no hand).  Returns:
          "thumbs_up"   - held for CONTROL_GESTURE_HOLD_FRAMES consecutive frames
          "thumbs_down" - held for CONTROL_GESTURE_HOLD_FRAMES consecutive frames
          None          - no control gesture detected yet
        """
        up   = self._is_thumbs_up(landmarks)
        down = self._is_thumbs_down(landmarks)

        if up:
            self._thumbs_up_frames  += 1
            self._thumbs_down_frames = 0
        elif down:
            self._thumbs_down_frames += 1
            self._thumbs_up_frames   = 0
        else:
            self._thumbs_up_frames   = 0
            self._thumbs_down_frames = 0

        if self._thumbs_up_frames == CONTROL_GESTURE_HOLD_FRAMES:
            self._thumbs_up_frames = 0   # reset so it fires exactly once per hold
            return "thumbs_up"
        if self._thumbs_down_frames == CONTROL_GESTURE_HOLD_FRAMES:
            self._thumbs_down_frames = 0
            return "thumbs_down"
        return None

    @property
    def thumbs_up_progress(self):
        """0.0 – 1.0 fill for the on-screen progress ring."""
        return min(self._thumbs_up_frames / CONTROL_GESTURE_HOLD_FRAMES, 1.0)

    @property
    def thumbs_down_progress(self):
        """0.0 – 1.0 fill for the on-screen progress ring."""
        return min(self._thumbs_down_frames / CONTROL_GESTURE_HOLD_FRAMES, 1.0)

    # ------------------------------------------------------------------
    # Private static helpers for thumb gestures
    # ------------------------------------------------------------------

    @staticmethod
    def _fingers_curled(lm):
        """
        Returns True when index, middle, ring and pinky are all curled
        (fingertip Y > its MCP Y in normalized coordinates, meaning the
        tip is *below* the knuckle in the image = finger is bent down).
        We use a small tolerance so a relaxed-but-not-perfectly-closed
        fist still counts.
        """
        pairs = [
            (_INDEX_TIP,  _INDEX_MCP),
            (_MIDDLE_TIP, _MIDDLE_MCP),
            (_RING_TIP,   _RING_MCP),
            (_PINKY_TIP,  _PINKY_MCP),
        ]
        for tip_id, mcp_id in pairs:
            # In image space Y increases downward, so a curled finger
            # has tip.y > mcp.y (tip is lower on screen than the knuckle).
            if lm[tip_id].y < lm[mcp_id].y - 0.02:   # 0.02 tolerance
                return False
        return True

    @staticmethod
    def _is_thumbs_up(lm):
        """
        👍: thumb tip is clearly ABOVE the wrist (tip.y << wrist.y),
        AND all other fingers are curled.
        """
        if lm is None:
            return False
        # Thumb must point upward: tip well above wrist
        thumb_above = (lm[_WRIST].y - lm[_THUMB_TIP].y) > 0.20
        # Thumb tip must also be above the thumb MCP (thumb is extended, not tucked)
        thumb_extended = lm[_THUMB_TIP].y < lm[_THUMB_MCP].y
        return thumb_above and thumb_extended and GestureDetector._fingers_curled(lm)

    @staticmethod
    def _is_thumbs_down(lm):
        """
        👎: thumb tip is clearly BELOW the wrist (tip.y >> wrist.y),
        AND all other fingers are curled.
        """
        if lm is None:
            return False
        # Thumb must point downward: tip well below wrist
        thumb_below = (lm[_THUMB_TIP].y - lm[_WRIST].y) > 0.15
        # Thumb tip must also be below the thumb MCP
        thumb_extended_down = lm[_THUMB_TIP].y > lm[_THUMB_MCP].y
        return thumb_below and thumb_extended_down and GestureDetector._fingers_curled(lm)

    # Private helpers

    def _handle_scroll(self, dist, ring_y_px):
        """
        Scroll logic.
        Thumb + ring pinch activates scroll mode.
        Vertical movement of the ring tip drives the scroll wheel.
        Natural scroll: hand moves UP -> page scrolls UP (positive delta).
        Sub-click movements are accumulated so slow gestures still scroll.
        """
        events = []

        if dist is None or ring_y_px is None:
            self._sc_active       = False
            self._sc_pinch_frames = 0
            self._sc_prev_y       = None
            self._sc_accumulator  = 0.0
            return events

        pinching = dist < config.SCROLL_THRESHOLD

        if pinching:
            self._sc_pinch_frames += 1

            if self._sc_pinch_frames >= config.SCROLL_DEBOUNCE_FRAMES:
                self._sc_active = True

                if self._sc_prev_y is not None:
                    delta_px = self._sc_prev_y - ring_y_px   # positive = hand moved up
                    dead_zone = config.SCROLL_DEAD_ZONE_PX

                    if abs(delta_px) >= dead_zone:
                        self._sc_accumulator += (
                            delta_px * config.SCROLL_SENSITIVITY / 100.0
                        )
                        clicks = int(self._sc_accumulator)
                        if clicks != 0:
                            self._sc_accumulator -= clicks
                            events.append(("scroll", clicks))

                self._sc_prev_y = ring_y_px

        else:
            self._sc_active       = False
            self._sc_pinch_frames = 0
            self._sc_prev_y       = None
            self._sc_accumulator  = 0.0

        return events
