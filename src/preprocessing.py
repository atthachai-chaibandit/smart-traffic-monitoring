"""Image processing functions shared by preview and future detection code."""

import cv2
import numpy as np


def brighten_frame(frame, strength):
    """Add brightness to a BGR frame without changing its original pixels."""
    strength = max(0, min(100, strength))
    # Map the slider's strength to a pixel offset from 0 to 80.
    offset = round(strength * 0.8)
    return cv2.add(frame, (offset, offset, offset, 0))


def mask_outside_roi(frame, points):
    """Keep the polygon's pixels and make the surrounding area black."""
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    polygon = np.asarray(points, dtype=np.int32)
    cv2.fillPoly(mask, [polygon], 255)
    return cv2.bitwise_and(frame, frame, mask=mask)
