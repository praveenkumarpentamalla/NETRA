"""
Project NETRA — Privacy Masker
Applies citizen-defined privacy zone polygons at pixel level.
CRITICAL: Masking happens BEFORE any frame is processed, stored, or transmitted.
Mask edits propagate within 60 seconds of citizen update.
"""

import logging
from typing import Dict, List
import numpy as np
import cv2

logger = logging.getLogger(__name__)


class PrivacyMasker:
    """
    Pixel-level privacy zone enforcement.
    Zones are polygons drawn by the citizen over a still frame.
    Any area inside a polygon is permanently blacked out.
    """

    def __init__(self, settings=None):
        # camera_id → list of polygon arrays (pixel coordinates)
        self._masks: Dict[str, np.ndarray] = {}
        self._polygons: Dict[str, List[List[dict]]] = {}

    def update_zones(self, cam_id: str, zones: List[dict]) -> None:
        """
        Update privacy zones for a camera.
        Called when citizen edits zones; must take effect within 60s.
        """
        if not zones:
            self._masks.pop(cam_id, None)
            self._polygons.pop(cam_id, None)
            logger.info(f"[{cam_id}] Privacy zones cleared")
            return

        self._polygons[cam_id] = [z['pixel_polygon'] for z in zones if z.get('is_active', True)]
        # Pre-compile masks — will be sized on first frame
        self._masks.pop(cam_id, None)  # force recompile on next frame
        logger.info(f"[{cam_id}] Privacy zones updated: {len(self._polygons[cam_id])} zones")

    def apply_masks(self, cam_id: str, frame: np.ndarray) -> np.ndarray:
        """
        Apply all privacy zones to a frame.
        Masked pixels are set to pure black (0, 0, 0).
        Returns masked frame.
        """
        if cam_id not in self._polygons or not self._polygons[cam_id]:
            return frame

        h, w = frame.shape[:2]
        mask_key = f"{cam_id}_{w}x{h}"

        # Build or retrieve compiled mask for this resolution
        if mask_key not in self._masks:
            self._masks[mask_key] = self._compile_mask(cam_id, h, w)

        compiled_mask = self._masks[mask_key]
        if compiled_mask is None:
            return frame

        # Apply mask: zero out pixels in privacy zones
        result = frame.copy()
        result[compiled_mask == 0] = 0
        return result

    def _compile_mask(self, cam_id: str, h: int, w: int) -> np.ndarray:
        """
        Compile all polygon zones into a single binary mask.
        1 = visible, 0 = masked/blacked-out.
        """
        zones = self._polygons.get(cam_id, [])
        if not zones:
            return None

        mask = np.ones((h, w), dtype=np.uint8)

        for polygon_points in zones:
            if not polygon_points:
                continue
            try:
                pts = np.array(
                    [[int(p['x']), int(p['y'])] for p in polygon_points],
                    dtype=np.int32,
                )
                if len(pts) < 3:
                    continue
                # Clip coordinates to frame bounds
                pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
                pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
                cv2.fillPoly(mask, [pts], 0)  # 0 = masked
            except Exception as e:
                logger.error(f"[{cam_id}] Privacy zone compile error: {e}")

        logger.debug(f"[{cam_id}] Compiled mask {w}x{h}: {mask.sum()} visible pixels")
        return mask

    def has_zones(self, cam_id: str) -> bool:
        return bool(self._polygons.get(cam_id))

    def get_zone_coverage_pct(self, cam_id: str, frame_w: int, frame_h: int) -> float:
        """Return percentage of frame area that is privacy-masked."""
        mask_key = f"{cam_id}_{frame_w}x{frame_h}"
        if mask_key not in self._masks:
            self._compile_mask(cam_id, frame_h, frame_w)
        compiled = self._masks.get(mask_key)
        if compiled is None:
            return 0.0
        total = frame_w * frame_h
        masked = total - int(compiled.sum())
        return round(masked / total * 100, 2)
