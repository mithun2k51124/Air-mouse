# -------------------------------------------------------------
#  AirMouse  -  hand_tracker.py
#
#  Thin wrapper around MediaPipe Hands.
#  Returns clean landmark data so the rest of the app never
#  needs to import mediapipe directly.
# -------------------------------------------------------------

import math
import mediapipe as mp
import config
# MediaPipe landmark indices we care about
WRIST         = 0
THUMB_TIP     = 4
INDEX_TIP     = 8
INDEX_MCP     = 5   # index finger knuckle (base joint)
MIDDLE_TIP    = 12
RING_TIP      = 16
PINKY_TIP     = 20


class HandTracker:
    """
    Wraps MediaPipe Hands and exposes helper methods for
    extracting landmark positions and computing pinch distances.
    """

    def __init__(self):
        self._mp_hands = mp.solutions.hands
        self._mp_draw  = mp.solutions.drawing_utils
        self._mp_style = mp.solutions.drawing_styles

        self.hands = self._mp_hands.Hands(
            static_image_mode        = False,
            max_num_hands            = config.MAX_HANDS,
            min_detection_confidence = config.DETECTION_CONFIDENCE,
            min_tracking_confidence  = config.TRACKING_CONFIDENCE,
        )
        # Last detected landmarks (list of NormalizedLandmark)
        self.landmarks  = None
        self.handedness = None   # "Left" or "Right" (MediaPipe camera-coords)

    # -- Public API --------------------------------------------

    def process(self, rgb_frame):
        """
        Feed one RGB frame into MediaPipe.
        Updates self.landmarks and self.handedness; returns (found, results).

        self.handedness is "Left" or "Right" in *camera* coordinates.
        Because FLIP_HORIZONTAL=True the image is mirrored, so:
          MediaPipe "Left"  -> user's RIGHT hand on screen
          MediaPipe "Right" -> user's LEFT  hand on screen
        """
        results = self.hands.process(rgb_frame)
        if results.multi_hand_landmarks:
            # We only track the first hand (MAX_HANDS = 1)
            self.landmarks = results.multi_hand_landmarks[0].landmark
            # Extract handedness label
            if results.multi_handedness:
                self.handedness = (
                    results.multi_handedness[0]
                           .classification[0]
                           .label          # "Left" or "Right"
                )
            else:
                self.handedness = None
            return True, results
        self.landmarks  = None
        self.handedness = None
        return False, results

    def get_tip(self, landmark_id, frame_w, frame_h):
        """
        Return pixel (x, y) of a landmark within the frame.
        Coordinates are clamped to frame bounds.
        """
        if self.landmarks is None:
            return None
        lm = self.landmarks[landmark_id]
        x  = int(lm.x * frame_w)
        y  = int(lm.y * frame_h)
        return (x, y)

    def pinch_distance(self, id_a, id_b):
        """
        Scale-invariant and angle-invariant 3D pinch distance.
        Uses 3D Euclidean distance (x, y, z) normalized by the user's
        palm size (distance from wrist to index knuckle base).

        This guarantees identical pinch thresholds whether the hand
        is close to the camera, far away, tilted, or facing directly
        at the camera lens.
        """
        if self.landmarks is None:
            return float("inf")
        la = self.landmarks[id_a]
        lb = self.landmarks[id_b]

        # 3D Euclidean distance between target landmarks
        d_3d = math.sqrt((la.x - lb.x)**2 + (la.y - lb.y)**2 + (la.z - lb.z)**2)

        # 3D Palm scale (wrist to index knuckle base) for depth/perspective invariance
        lw = self.landmarks[WRIST]
        lm = self.landmarks[INDEX_MCP]
        palm = math.sqrt((lw.x - lm.x)**2 + (lw.y - lm.y)**2 + (lw.z - lm.z)**2)

        if palm < 1e-4:
            return d_3d

        return d_3d / palm

    def draw_landmarks(self, bgr_frame, results):
        """Draw the hand skeleton onto the frame (debug view)."""
        if results.multi_hand_landmarks:
            for hand_lm in results.multi_hand_landmarks:
                self._mp_draw.draw_landmarks(
                    bgr_frame,
                    hand_lm,
                    self._mp_hands.HAND_CONNECTIONS,
                    self._mp_style.get_default_hand_landmarks_style(),
                    self._mp_style.get_default_hand_connections_style(),
                )

    def close(self):
        self.hands.close()
