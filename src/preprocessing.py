"""Image processing functions shared by preview and future detection code."""

import cv2


def brighten_frame(frame, strength):
    """Add brightness to a BGR frame without changing its original pixels."""
    strength = max(0, min(100, strength))
    # Map the slider's strength to a pixel offset from 0 to 80.
    offset = round(strength * 0.8)
    return cv2.add(frame, (offset, offset, offset, 0))
