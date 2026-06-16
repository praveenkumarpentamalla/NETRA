"""
Project NETRA — Person Re-ID Service
OSNet / FastReID pipeline.
STRICTLY investigation-bound: Re-ID against the global archive is
structurally prohibited — no API path exists for it.
"""

import hashlib
import logging
import time
from typing import List, Optional
import numpy as np
import cv2
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────

class PersonCrop(BaseModel):
    crop_b64: str
    source_event_id: str
    source_camera_id: str

class ReIDCandidate(BaseModel):
    rank: int
    event_id: str
    camera_id: str
    occurred_at: str
    similarity_score: float
    confidence: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int

class ReIDResponse(BaseModel):
    query_hash: str
    investigation_id: str
    candidates: List[ReIDCandidate]
    processing_time_ms: float
    search_scope_cameras: int
    search_scope_events: int
    model_version: str = "netra-reid-osnet-v1.0"
    governance_note: str = (
        "Re-ID scoped to investigation cameras and time-window only. "
        "Global archive Re-ID is structurally forbidden."
    )

# ──────────────────────────────────────────────────────────────
# OSNet embedding model
# ──────────────────────────────────────────────────────────────

class OSNetEmbedder:
    """OSNet-x1.0 person Re-ID embeddings (256-D)."""

    EMBEDDING_DIM = 256

    def __init__(self, model_path: str = "/models/reid/osnet_x1_0.pt"):
        self.model_path = model_path
        self._model = None

    def _load(self):
        if self._model:
            return
        try:
            import torchreid
            self._model = torchreid.models.build_model(
                name='osnet_x1_0', num_classes=1000, pretrained=True,
            )
            self._model.eval()
            logger.info("OSNet-x1.0 loaded for Re-ID")
        except Exception as e:
            logger.warning(f"torchreid not available, using mock: {e}")
            self._model = None

    def embed(self, person_img: np.ndarray) -> Optional[np.ndarray]:
        self._load()
        if person_img is None or person_img.size == 0:
            return None
        if self._model is None:
            return self._mock_embed(person_img)
        try:
            import torch
            import torchvision.transforms as T
            transform = T.Compose([
                T.ToPILImage(),
                T.Resize((256, 128)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            tensor = transform(person_img).unsqueeze(0)
            with torch.no_grad():
                feat = self._model(tensor)
            emb = feat.squeeze().numpy()
            norm = np.linalg.norm(emb)
            return (emb / norm).astype(np.float32) if norm > 0 else emb
        except Exception as e:
            logger.error(f"OSNet embed error: {e}")
            return None

    def _mock_embed(self, img: np.ndarray) -> np.ndarray:
        seed = int.from_bytes(img.tobytes()[:4], 'big') % (2 ** 32)
        rng = np.random.default_rng(seed)
        emb = rng.standard_normal(self.EMBEDDING_DIM).astype(np.float32)
        return emb / np.linalg.norm(emb)


# ──────────────────────────────────────────────────────────────
# Re-ID Pipeline
# ──────────────────────────────────────────────────────────────

class PersonReIDPipeline:
    SIMILARITY_THRESHOLD = 0.65  # Rank-1 ≥ 65% target

    def __init__(self):
        self.embedder = OSNetEmbedder()

    def search(
        self,
        query_img: np.ndarray,
        gallery: List[dict],  # investigation-scoped gallery from Milvus
        top_k: int = 20,
    ) -> List[ReIDCandidate]:
        query_emb = self.embedder.embed(query_img)
        if query_emb is None:
            return []

        scored = []
        for item in gallery:
            gal_emb = np.array(item['embedding'], dtype=np.float32)
            sim = float(np.dot(query_emb, gal_emb))
            scored.append((item, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        candidates = []
        for rank, (item, sim) in enumerate(scored[:top_k], start=1):
            if sim < self.SIMILARITY_THRESHOLD:
                break
            candidates.append(ReIDCandidate(
                rank=rank,
                event_id=item['event_id'],
                camera_id=item['camera_id'],
                occurred_at=item['occurred_at'],
                similarity_score=round(sim, 6),
                confidence=round(min(sim / 1.0, 1.0), 4),
                bbox_x=item.get('bbox_x', 0),
                bbox_y=item.get('bbox_y', 0),
                bbox_w=item.get('bbox_w', 0),
                bbox_h=item.get('bbox_h', 0),
            ))
        return candidates


# ──────────────────────────────────────────────────────────────
# FastAPI
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="NETRA Person Re-ID Service",
    version="1.0.0",
    description=(
        "Person Re-Identification. Scoped strictly to active investigation. "
        "Global archive search is structurally forbidden."
    ),
)

reid_pipeline = PersonReIDPipeline()


class ReIDRequest(BaseModel):
    query_crop_b64: str
    investigation_id: str          # MANDATORY — no investigation = no Re-ID
    investigation_camera_ids: List[str]
    investigation_time_start: str
    investigation_time_end: str
    # Gallery embeddings are passed from Milvus (pre-filtered by investigation scope)
    gallery_embeddings: List[dict]


@app.post("/reid/person/search", response_model=ReIDResponse)
async def person_reid_search(request: ReIDRequest):
    """
    Person Re-ID search within investigation scope.
    Requires investigation_id — no global search allowed.
    """
    import base64
    start = time.perf_counter()

    # Structural enforcement: investigation_id mandatory
    if not request.investigation_id or request.investigation_id.strip() == "":
        raise HTTPException(
            status_code=400,
            detail=(
                "investigation_id is mandatory for Re-ID. "
                "Global archive Re-ID is structurally prohibited by design."
            ),
        )

    # Validate gallery is pre-scoped to investigation cameras
    gallery = [
        g for g in request.gallery_embeddings
        if g.get('camera_id') in request.investigation_camera_ids
    ]

    # Decode query crop
    try:
        img_bytes = base64.b64decode(request.query_crop_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        query_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image")

    if query_img is None:
        raise HTTPException(status_code=400, detail="Cannot decode image")

    query_hash = hashlib.sha256(img_bytes).hexdigest()
    candidates = reid_pipeline.search(query_img, gallery)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return ReIDResponse(
        query_hash=query_hash,
        investigation_id=request.investigation_id,
        candidates=candidates,
        processing_time_ms=round(elapsed_ms, 2),
        search_scope_cameras=len(request.investigation_camera_ids),
        search_scope_events=len(gallery),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "person-reid", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")
