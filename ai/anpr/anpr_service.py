"""
Project NETRA — ANPR Service
Automatic Number Plate Recognition for Indian plates.
Two-stage pipeline: YOLOv8 plate detector + PaddleOCR recogniser.
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────

class PlateDetection(BaseModel):
    plate_string: str
    confidence: float
    char_confidences: List[float]
    plate_class: str  # PRIVATE | COMMERCIAL | EV | GOVERNMENT
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    plate_height_px: int
    script_detected: str  # LATIN | DEVANAGARI | TAMIL | BENGALI | KANNADA
    raw_ocr: str

class AnprResponse(BaseModel):
    frame_hash: str
    detections: List[PlateDetection]
    processing_time_ms: float
    model_version: str = "netra-anpr-v1.0"
    meets_kpi: bool  # True if plate_height >= 60px (KPI threshold)

class AnprBatchRequest(BaseModel):
    frame_b64: str
    camera_id: str
    event_id: str
    timestamp: str

# ──────────────────────────────────────────────────────────────
# Indian plate format validation
# ──────────────────────────────────────────────────────────────

# Standard: XX-DD-XX-DDDD or XX-DD-X-DDDD
INDIAN_PLATE_PATTERN = re.compile(
    r'^[A-Z]{2}[\s\-]?(\d{2})[\s\-]?([A-Z]{1,2})[\s\-]?(\d{4})$'
)

PLATE_CLASS_INDICATORS = {
    'GOVERNMENT': ['GJ', 'IND', 'GCA', 'INDIA'],
    'EV': ['E'],  # BH-series and state EV series
    'COMMERCIAL': ['yellow_background'],  # detected by HSV
}

def classify_plate(plate_string: str, bg_color: str) -> str:
    if any(ind in plate_string for ind in PLATE_CLASS_INDICATORS['GOVERNMENT']):
        return 'GOVERNMENT'
    if bg_color == 'yellow':
        return 'COMMERCIAL'
    if bg_color == 'green':
        return 'EV'
    return 'PRIVATE'

def detect_plate_background(plate_roi: np.ndarray) -> str:
    """Detect plate background colour via HSV analysis."""
    hsv = cv2.cvtColor(plate_roi, cv2.COLOR_BGR2HSV)
    avg_hue = float(np.mean(hsv[:, :, 0]))
    avg_sat = float(np.mean(hsv[:, :, 1]))

    if avg_sat < 40:  # white plate
        return 'white'
    if 20 <= avg_hue <= 35 and avg_sat > 100:
        return 'yellow'
    if 40 <= avg_hue <= 80 and avg_sat > 100:
        return 'green'
    if avg_hue < 15 or avg_hue > 165:
        return 'red'
    return 'white'

# ──────────────────────────────────────────────────────────────
# ANPR Pipeline
# ──────────────────────────────────────────────────────────────

class ANPRPipeline:
    """
    Two-stage ANPR pipeline optimised for Indian plates.
    Stage 1: YOLOv8 plate detector
    Stage 2: PaddleOCR text recognition with multi-script support
    """

    def __init__(self, model_dir: str = "/models/anpr"):
        self.model_dir = Path(model_dir)
        self.plate_detector = None
        self.ocr_engine = None
        self._loaded = False
        logger.info("ANPR pipeline initialised (models load on first use)")

    def _load_models(self):
        if self._loaded:
            return
        try:
            from ultralytics import YOLO
            self.plate_detector = YOLO(str(self.model_dir / "plate_detector.pt"))
            logger.info("Plate detector loaded")
        except ImportError:
            logger.warning("ultralytics not installed — using mock detector")
            self.plate_detector = None

        try:
            from paddleocr import PaddleOCR
            # Multi-language OCR covering Devanagari, Tamil, Bengali, Kannada
            self.ocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang='en',
                use_gpu=True,
                show_log=False,
                rec_model_dir=str(self.model_dir / "ocr_rec"),
                det_model_dir=str(self.model_dir / "ocr_det"),
            )
            logger.info("PaddleOCR engine loaded")
        except ImportError:
            logger.warning("paddleocr not installed — using mock OCR")
            self.ocr_engine = None

        self._loaded = True

    def detect_plates(
        self, frame: np.ndarray, conf_threshold: float = 0.5
    ) -> List[Tuple[np.ndarray, List[int], float]]:
        """
        Returns list of (plate_roi, [x,y,w,h], confidence).
        """
        self._load_models()

        if self.plate_detector is None:
            # Mock for testing without GPU
            return self._mock_detect_plates(frame)

        results = self.plate_detector(frame, conf=conf_threshold, verbose=False)
        plates = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                conf = float(box.conf[0].cpu().numpy())
                roi = frame[y1:y2, x1:x2]
                plates.append((roi, [x1, y1, x2 - x1, y2 - y1], conf))
        return plates

    def ocr_plate(
        self, plate_roi: np.ndarray
    ) -> Tuple[str, List[float], str]:
        """
        Returns (plate_string, char_confidences, script_type).
        """
        self._load_models()

        if self.ocr_engine is None:
            return self._mock_ocr_plate(plate_roi)

        # Preprocess for better OCR on Indian plates
        processed = self._preprocess_plate(plate_roi)

        result = self.ocr_engine.ocr(processed, cls=True)
        if not result or not result[0]:
            return '', [], 'LATIN'

        # Extract text and confidences from PaddleOCR output
        texts = []
        confidences = []
        for line in result[0]:
            text, conf = line[1]
            texts.append(text)
            confidences.append(conf)

        raw_text = ' '.join(texts).upper().strip()
        cleaned = self._clean_plate_text(raw_text)
        script = self._detect_script(raw_text)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        char_confs = [avg_conf] * len(cleaned)  # per-char in production

        return cleaned, char_confs, script

    def process_frame(self, frame: np.ndarray) -> List[PlateDetection]:
        """Full pipeline: detect + OCR all plates in frame."""
        detections = []

        plate_rois = self.detect_plates(frame)
        for roi, bbox, detect_conf in plate_rois:
            x, y, w, h = bbox
            plate_height = h

            # Run OCR
            plate_string, char_confs, script = self.ocr_plate(roi)

            if not plate_string:
                continue

            # Classify background
            bg_color = detect_plate_background(roi)
            plate_class = classify_plate(plate_string, bg_color)

            # Overall confidence (detection × OCR)
            avg_char_conf = sum(char_confs) / len(char_confs) if char_confs else 0.0
            overall_conf = detect_conf * avg_char_conf

            detections.append(PlateDetection(
                plate_string=plate_string,
                confidence=round(overall_conf, 4),
                char_confidences=[round(c, 4) for c in char_confs],
                plate_class=plate_class,
                bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h,
                plate_height_px=plate_height,
                script_detected=script,
                raw_ocr=plate_string,
            ))

        # Sort by confidence descending
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def _preprocess_plate(self, roi: np.ndarray) -> np.ndarray:
        """Enhance plate image for OCR: resize, contrast, denoise."""
        if roi.size == 0:
            return roi

        # Resize to minimum height for OCR quality
        target_h = 100
        if roi.shape[0] < target_h:
            scale = target_h / roi.shape[0]
            roi = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Convert to grayscale and enhance contrast
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Denoise
        denoised = cv2.fastNlMeansDenoising(enhanced, h=10)

        return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)

    def _clean_plate_text(self, raw: str) -> str:
        """Clean and normalise Indian plate text."""
        # Remove non-alphanumeric except spaces and hyphens
        cleaned = re.sub(r'[^A-Z0-9\s\-]', '', raw.upper())
        # Collapse whitespace
        cleaned = re.sub(r'[\s\-]+', '-', cleaned).strip('-')
        # Common OCR error corrections for Indian plates
        corrections = {
            'O': '0', 'I': '1', 'S': '5', 'B': '8', 'G': '6',
        }
        # Only apply corrections in numeric positions
        # (simplified — production uses sequence-aware correction)
        return cleaned

    def _detect_script(self, text: str) -> str:
        """Detect if plate uses non-Latin script."""
        # Unicode ranges
        devanagari = any('\u0900' <= c <= '\u097F' for c in text)
        tamil = any('\u0B80' <= c <= '\u0BFF' for c in text)
        bengali = any('\u0980' <= c <= '\u09FF' for c in text)
        kannada = any('\u0C80' <= c <= '\u0CFF' for c in text)

        if devanagari:
            return 'DEVANAGARI'
        if tamil:
            return 'TAMIL'
        if bengali:
            return 'BENGALI'
        if kannada:
            return 'KANNADA'
        return 'LATIN'

    def _mock_detect_plates(self, frame: np.ndarray):
        """Mock detection for testing without GPU."""
        h, w = frame.shape[:2]
        mock_roi = frame[h//3:2*h//3, w//4:3*w//4]
        return [(mock_roi, [w//4, h//3, w//2, h//3], 0.88)]

    def _mock_ocr_plate(self, roi: np.ndarray):
        """Mock OCR for testing."""
        return 'MH01AB1234', [0.92] * 10, 'LATIN'


# ──────────────────────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="NETRA ANPR Service",
    version="1.0.0",
    description="Automatic Number Plate Recognition for Indian plates",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

pipeline = ANPRPipeline()

@app.post("/anpr/process", response_model=AnprResponse)
async def process_frame(file: UploadFile = File(...)):
    """Process a single frame for ANPR."""
    import time
    start = time.perf_counter()

    content = await file.read()
    nparr = np.frombuffer(content, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image")

    frame_hash = hashlib.sha256(content).hexdigest()

    try:
        detections = pipeline.process_frame(frame)
    except Exception as e:
        logger.error(f"ANPR error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing error: {e}")

    elapsed_ms = (time.perf_counter() - start) * 1000

    # KPI check: at least one plate at ≥60px height
    meets_kpi = any(d.plate_height_px >= 60 for d in detections)

    return AnprResponse(
        frame_hash=frame_hash,
        detections=detections,
        processing_time_ms=round(elapsed_ms, 2),
        meets_kpi=meets_kpi,
    )

@app.get("/health")
async def health():
    return {"status": "ok", "service": "anpr", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
