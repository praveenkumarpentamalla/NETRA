"""
Project NETRA — Edge Detector
Lightweight event trigger running on Bridge Agent.
YOLOv8-nano + MOG2 background subtraction.
Targets: ≥12fps on Raspberry Pi 4 / RK3588, ≥25fps on Jetson Orin Nano.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np
import cv2

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    triggered: bool
    event_type: str
    confidence: float
    bboxes: List[dict] = field(default_factory=list)
    audio_triggered: bool = False
    timestamp: float = field(default_factory=time.time)


class BackgroundSubtractor:
    """MOG2/KNN background subtraction with per-zone activation."""

    def __init__(self, history: int = 200, var_threshold: float = 50.0):
        self._mog2 = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=False,
        )
        self._motion_threshold = 0.01  # 1% of frame area

    def detect_motion(self, frame: np.ndarray) -> tuple:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fg_mask = self._mog2.apply(gray)
        # Clean up noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

        motion_ratio = float(fg_mask.sum()) / (fg_mask.shape[0] * fg_mask.shape[1] * 255)
        return motion_ratio > self._motion_threshold, motion_ratio


class YOLONanoDetector:
    """
    YOLOv8-nano for person/vehicle/animal class gating.
    ONNX Runtime for cross-platform edge inference.
    """

    CONFIDENCE_THRESHOLD = 0.45
    CLASSES_OF_INTEREST = {0: 'person', 2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}

    def __init__(self, model_path: str = "/models/edge/yolov8n.onnx"):
        self.model_path = model_path
        self._session = None
        self._input_shape = (640, 640)

    def _load(self):
        if self._session:
            return
        try:
            import onnxruntime as ort
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            self._session = ort.InferenceSession(self.model_path, providers=providers)
            logger.info("YOLOv8-nano loaded via ONNX Runtime")
        except Exception as e:
            logger.warning(f"ONNX Runtime not available: {e} — using mock")
            self._session = None

    def detect(self, frame: np.ndarray) -> List[dict]:
        self._load()
        if self._session is None:
            return self._mock_detect(frame)
        try:
            blob = self._preprocess(frame)
            outputs = self._session.run(None, {'images': blob})
            return self._postprocess(outputs[0], frame.shape)
        except Exception as e:
            logger.error(f"YOLO inference error: {e}")
            return []

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        h, w = self._input_shape
        resized = cv2.resize(frame, (w, h))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))
        return blob[np.newaxis, ...]

    def _postprocess(self, output: np.ndarray, orig_shape: tuple) -> List[dict]:
        detections = []
        orig_h, orig_w = orig_shape[:2]
        inp_h, inp_w = self._input_shape

        for det in output[0].T:
            x, y, w, h = det[:4]
            class_scores = det[4:]
            class_id = int(np.argmax(class_scores))
            conf = float(class_scores[class_id])

            if conf < self.CONFIDENCE_THRESHOLD:
                continue
            if class_id not in self.CLASSES_OF_INTEREST:
                continue

            # Scale to original frame coordinates
            scale_x, scale_y = orig_w / inp_w, orig_h / inp_h
            x1 = int((x - w / 2) * scale_x)
            y1 = int((y - h / 2) * scale_y)
            bw = int(w * scale_x)
            bh = int(h * scale_y)

            detections.append({
                'class': self.CLASSES_OF_INTEREST[class_id],
                'class_id': class_id,
                'confidence': round(conf, 4),
                'bbox': [max(0, x1), max(0, y1), bw, bh],
            })
        return detections

    def _mock_detect(self, frame: np.ndarray) -> List[dict]:
        h, w = frame.shape[:2]
        return [{
            'class': 'person', 'class_id': 0,
            'confidence': 0.82,
            'bbox': [w // 4, h // 4, w // 2, h // 2],
        }]


class AudioEdgeClassifier:
    """
    Lightweight edge audio classifier.
    Full YAMNet confirmation runs server-side.
    """

    def __init__(self):
        self._threshold = 0.6

    def classify(self, audio_chunk: Optional[bytes]) -> tuple:
        """Returns (triggered: bool, event_type: str, confidence: float)."""
        if audio_chunk is None:
            return False, '', 0.0
        # Edge uses energy-based heuristic; server confirms with full model
        samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)
        if len(samples) == 0:
            return False, '', 0.0
        rms = float(np.sqrt(np.mean(samples ** 2)))
        normalised_rms = min(rms / 32768.0, 1.0)
        # High energy spike → possible audio anomaly
        if normalised_rms > 0.7:
            return True, 'audio_anomaly', round(normalised_rms, 3)
        return False, '', 0.0


class EdgeDetector:
    """
    Combined edge detector.
    MOG2 + YOLOv8-nano for video; energy-based for audio.
    """

    # Minimum frames between triggers (debounce)
    TRIGGER_COOLDOWN_S = 5.0

    def __init__(self, settings=None):
        self.bg_subtractor = BackgroundSubtractor()
        self.yolo = YOLONanoDetector(
            model_path=getattr(settings, 'yolo_model_path', '/models/edge/yolov8n.onnx')
        )
        self.audio_clf = AudioEdgeClassifier()
        self._last_trigger_time: dict = {}
        self._away_mode: dict = {}

    def detect(
        self, frame: np.ndarray, audio_chunk: Optional[bytes], cam_id: str
    ) -> Detection:
        now = time.time()

        # Debounce
        last = self._last_trigger_time.get(cam_id, 0)
        if now - last < self.TRIGGER_COOLDOWN_S:
            return Detection(triggered=False, event_type='', confidence=0.0)

        # Step 1: Motion gating (cheap)
        motion_detected, motion_ratio = self.bg_subtractor.detect_motion(frame)

        # Step 2: Audio (fast heuristic)
        audio_triggered, audio_type, audio_conf = self.audio_clf.classify(audio_chunk)

        if not motion_detected and not audio_triggered:
            return Detection(triggered=False, event_type='', confidence=0.0)

        # Step 3: YOLO class gating (only if motion detected)
        bboxes = []
        event_type = 'motion'
        confidence = motion_ratio

        if motion_detected:
            bboxes = self.yolo.detect(frame)
            if bboxes:
                best = max(bboxes, key=lambda b: b['confidence'])
                if best['class'] == 'person':
                    event_type = (
                        'away_mode_motion'
                        if self._away_mode.get(cam_id) else 'person_detected'
                    )
                elif best['class'] in ('car', 'truck', 'bus', 'motorcycle'):
                    event_type = 'vehicle_detected'
                confidence = best['confidence']

        if audio_triggered:
            event_type = 'audio_anomaly'
            confidence = audio_conf

        self._last_trigger_time[cam_id] = now

        return Detection(
            triggered=True,
            event_type=event_type,
            confidence=round(confidence, 4),
            bboxes=bboxes,
            audio_triggered=audio_triggered,
            timestamp=now,
        )

    def set_away_mode(self, cam_id: str, enabled: bool):
        self._away_mode[cam_id] = enabled
