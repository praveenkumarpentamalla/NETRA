"""
Project NETRA — Milvus Vector Database Service
Collections: face embeddings, person Re-ID, vehicle Re-ID, watchlist templates.
Watchlist collection has tighter access control than general index.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Collection Definitions
# ──────────────────────────────────────────────────────────────

COLLECTIONS = {

    # General face embedding index (anonymous — no name attached)
    # Searched only within investigation scope (camera + time window filter)
    "netra_face_embeddings": {
        "description": "Anonymous face embeddings for indexed search",
        "fields": [
            {"name": "id",            "dtype": "INT64",    "is_primary": True, "auto_id": True},
            {"name": "event_id",      "dtype": "VARCHAR",  "max_length": 36},
            {"name": "camera_id",     "dtype": "VARCHAR",  "max_length": 30},
            {"name": "occurred_at",   "dtype": "INT64"},   # Unix timestamp ms
            {"name": "quality_score", "dtype": "FLOAT"},
            {"name": "is_child",      "dtype": "BOOL"},    # excluded from recognition if True
            {"name": "bbox_x",        "dtype": "INT32"},
            {"name": "bbox_y",        "dtype": "INT32"},
            {"name": "bbox_w",        "dtype": "INT32"},
            {"name": "bbox_h",        "dtype": "INT32"},
            {"name": "embedding",     "dtype": "FLOAT_VECTOR", "dim": 512},
        ],
        "index": {
            "field_name": "embedding",
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 200},
        },
        "scalar_indexes": ["camera_id", "occurred_at", "is_child"],
        "access": "investigation_scoped",  # must filter by camera_id + time window
    },

    # Watchlist face templates (tightly access-controlled; separate collection)
    # Only queried during recognition runs against authorised watchlists
    "netra_watchlist_faces": {
        "description": "Watchlist face templates — tightly access controlled",
        "fields": [
            {"name": "id",                 "dtype": "INT64",    "is_primary": True, "auto_id": True},
            {"name": "watchlist_entry_id", "dtype": "VARCHAR",  "max_length": 36},
            {"name": "biometric_hash",     "dtype": "VARCHAR",  "max_length": 128},
            {"name": "category",           "dtype": "VARCHAR",  "max_length": 20},  # WANTED|MISSING|BOLO_SUSPECT
            {"name": "reference",          "dtype": "VARCHAR",  "max_length": 200},
            {"name": "status",             "dtype": "VARCHAR",  "max_length": 20},  # ACTIVE|EXPIRED|REMOVED
            {"name": "expiry_ts",          "dtype": "INT64"},   # Unix ms
            {"name": "embedding",          "dtype": "FLOAT_VECTOR", "dim": 512},
        ],
        "index": {
            "field_name": "embedding",
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 32, "efConstruction": 400},  # higher quality for watchlist
        },
        "scalar_indexes": ["category", "status", "watchlist_entry_id"],
        "access": "watchlist_governed",  # named-officer credentials required
    },

    # Person Re-ID gallery (investigation-scoped)
    "netra_person_reid": {
        "description": "Person Re-ID gallery embeddings",
        "fields": [
            {"name": "id",            "dtype": "INT64",    "is_primary": True, "auto_id": True},
            {"name": "event_id",      "dtype": "VARCHAR",  "max_length": 36},
            {"name": "camera_id",     "dtype": "VARCHAR",  "max_length": 30},
            {"name": "occurred_at",   "dtype": "INT64"},
            {"name": "track_id",      "dtype": "VARCHAR",  "max_length": 50},   # ByteTrack ID
            {"name": "bbox_x",        "dtype": "INT32"},
            {"name": "bbox_y",        "dtype": "INT32"},
            {"name": "bbox_w",        "dtype": "INT32"},
            {"name": "bbox_h",        "dtype": "INT32"},
            {"name": "embedding",     "dtype": "FLOAT_VECTOR", "dim": 256},     # OSNet 256-D
        ],
        "index": {
            "field_name": "embedding",
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 200},
        },
        "scalar_indexes": ["camera_id", "occurred_at", "event_id"],
        "access": "investigation_scoped",
    },

    # Vehicle Re-ID gallery (investigation-scoped)
    "netra_vehicle_reid": {
        "description": "Vehicle Re-ID gallery embeddings",
        "fields": [
            {"name": "id",            "dtype": "INT64",    "is_primary": True, "auto_id": True},
            {"name": "event_id",      "dtype": "VARCHAR",  "max_length": 36},
            {"name": "camera_id",     "dtype": "VARCHAR",  "max_length": 30},
            {"name": "occurred_at",   "dtype": "INT64"},
            {"name": "plate_string",  "dtype": "VARCHAR",  "max_length": 20},
            {"name": "vehicle_class", "dtype": "VARCHAR",  "max_length": 30},
            {"name": "colour",        "dtype": "VARCHAR",  "max_length": 30},
            {"name": "embedding",     "dtype": "FLOAT_VECTOR", "dim": 256},
        ],
        "index": {
            "field_name": "embedding",
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 200},
        },
        "scalar_indexes": ["camera_id", "occurred_at", "plate_string"],
        "access": "investigation_scoped",
    },
}

# ──────────────────────────────────────────────────────────────
# Milvus Service
# ──────────────────────────────────────────────────────────────

class MilvusService:
    """Milvus vector database client with governance enforcement."""

    def __init__(self, host: str = "localhost", port: int = 19530):
        self.host = host
        self.port = port
        self._connected = False

    def _connect(self):
        if self._connected:
            return
        try:
            from pymilvus import connections, utility
            connections.connect("default", host=self.host, port=self.port)
            self._connected = True
            logger.info(f"Milvus connected: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Milvus connection failed: {e}")
            raise

    def setup_collections(self):
        """Create all collections and indexes if they don't exist."""
        self._connect()
        from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, utility

        dtype_map = {
            "INT64": DataType.INT64,
            "INT32": DataType.INT32,
            "FLOAT": DataType.FLOAT,
            "BOOL": DataType.BOOL,
            "VARCHAR": DataType.VARCHAR,
            "FLOAT_VECTOR": DataType.FLOAT_VECTOR,
        }

        for collection_name, config in COLLECTIONS.items():
            if utility.has_collection(collection_name):
                logger.info(f"Collection exists: {collection_name}")
                continue

            fields = []
            for f in config["fields"]:
                dtype = dtype_map[f["dtype"]]
                kwargs = {"is_primary": f.get("is_primary", False), "auto_id": f.get("auto_id", False)}
                if dtype == DataType.VARCHAR:
                    kwargs["max_length"] = f.get("max_length", 256)
                if dtype == DataType.FLOAT_VECTOR:
                    kwargs["dim"] = f["dim"]
                fields.append(FieldSchema(name=f["name"], dtype=dtype, **kwargs))

            schema = CollectionSchema(fields=fields, description=config["description"])
            collection = Collection(name=collection_name, schema=schema)

            # Create vector index
            idx = config["index"]
            collection.create_index(
                field_name=idx["field_name"],
                index_params={
                    "index_type": idx["index_type"],
                    "metric_type": idx["metric_type"],
                    "params": idx["params"],
                },
            )

            # Create scalar indexes for filtered search
            for scalar_field in config.get("scalar_indexes", []):
                collection.create_index(field_name=scalar_field)

            collection.load()
            logger.info(f"Created collection: {collection_name}")

    def insert_face_embedding(
        self,
        event_id: str,
        camera_id: str,
        occurred_at: int,  # Unix ms
        quality_score: float,
        is_child: bool,
        bbox: List[int],
        embedding: List[float],
    ) -> int:
        """Insert face embedding. Returns Milvus ID."""
        self._connect()
        from pymilvus import Collection
        col = Collection("netra_face_embeddings")
        col.load()

        result = col.insert([[
            event_id, camera_id, occurred_at,
            quality_score, is_child,
            bbox[0], bbox[1], bbox[2], bbox[3],
            [embedding],
        ]])
        col.flush()
        return result.primary_keys[0]

    def insert_watchlist_embedding(
        self,
        watchlist_entry_id: str,
        biometric_hash: str,
        category: str,
        reference: str,
        expiry_ts: int,
        embedding: List[float],
    ) -> int:
        """Insert watchlist face template."""
        self._connect()
        from pymilvus import Collection
        col = Collection("netra_watchlist_faces")
        col.load()

        result = col.insert([[
            watchlist_entry_id, biometric_hash,
            category, reference, "ACTIVE", expiry_ts,
            [embedding],
        ]])
        col.flush()
        return result.primary_keys[0]

    def search_faces_in_investigation_scope(
        self,
        query_embedding: List[float],
        camera_ids: List[str],
        time_start_ms: int,
        time_end_ms: int,
        top_k: int = 20,
        score_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search face embeddings within investigation scope (camera + time window).
        STRUCTURAL ENFORCEMENT: This method ALWAYS applies camera_id and time filters.
        Global archive search is architecturally impossible via this method.
        """
        self._connect()
        from pymilvus import Collection

        if not camera_ids:
            raise ValueError("camera_ids must be provided — investigation scope required")

        col = Collection("netra_face_embeddings")
        col.load()

        # Build filter expression (enforcement of investigation scope)
        cam_filter = " || ".join([f'camera_id == "{c}"' for c in camera_ids])
        expr = f"({cam_filter}) && occurred_at >= {time_start_ms} && occurred_at <= {time_end_ms} && is_child == false"

        results = col.search(
            data=[[query_embedding]],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            expr=expr,
            output_fields=["event_id", "camera_id", "occurred_at", "quality_score",
                           "bbox_x", "bbox_y", "bbox_w", "bbox_h"],
        )

        hits = []
        for hit in results[0]:
            if hit.score < score_threshold:
                continue
            hits.append({
                "milvus_id": hit.id,
                "event_id": hit.entity.get("event_id"),
                "camera_id": hit.entity.get("camera_id"),
                "occurred_at": hit.entity.get("occurred_at"),
                "quality_score": hit.entity.get("quality_score"),
                "bbox": [hit.entity.get(f) for f in ["bbox_x", "bbox_y", "bbox_w", "bbox_h"]],
                "similarity": hit.score,
            })
        return hits

    def search_watchlist(
        self,
        query_embedding: List[float],
        categories: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search watchlist face templates.
        Always filters to ACTIVE status only.
        Returns top-N (default 5) — never just 1.
        """
        self._connect()
        from pymilvus import Collection

        col = Collection("netra_watchlist_faces")
        col.load()

        expr = 'status == "ACTIVE"'
        if categories:
            cat_filter = " || ".join([f'category == "{c}"' for c in categories])
            expr += f" && ({cat_filter})"

        results = col.search(
            data=[[query_embedding]],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=expr,
            output_fields=["watchlist_entry_id", "biometric_hash", "category", "reference"],
        )

        hits = []
        for hit in results[0]:
            hits.append({
                "milvus_id": hit.id,
                "watchlist_entry_id": hit.entity.get("watchlist_entry_id"),
                "biometric_hash": hit.entity.get("biometric_hash"),
                "category": hit.entity.get("category"),
                "reference": hit.entity.get("reference"),
                "similarity": hit.score,
            })
        return hits  # Caller applies Platt calibration

    def remove_watchlist_embedding(self, watchlist_entry_id: str):
        """Remove watchlist template on entry removal/expiry."""
        self._connect()
        from pymilvus import Collection
        col = Collection("netra_watchlist_faces")
        col.delete(f'watchlist_entry_id == "{watchlist_entry_id}"')
        col.flush()
        logger.info(f"Removed watchlist embedding: {watchlist_entry_id}")

    def insert_person_reid(
        self,
        event_id: str,
        camera_id: str,
        occurred_at: int,
        track_id: str,
        bbox: List[int],
        embedding: List[float],
    ) -> int:
        self._connect()
        from pymilvus import Collection
        col = Collection("netra_person_reid")
        col.load()
        result = col.insert([[
            event_id, camera_id, occurred_at,
            track_id, bbox[0], bbox[1], bbox[2], bbox[3],
            [embedding],
        ]])
        col.flush()
        return result.primary_keys[0]

    def search_person_reid_in_scope(
        self,
        query_embedding: List[float],
        camera_ids: List[str],
        time_start_ms: int,
        time_end_ms: int,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """Re-ID search — strictly scoped to investigation cameras + time window."""
        self._connect()
        from pymilvus import Collection

        if not camera_ids:
            raise ValueError("camera_ids required for scoped Re-ID")

        col = Collection("netra_person_reid")
        col.load()

        cam_filter = " || ".join([f'camera_id == "{c}"' for c in camera_ids])
        expr = f"({cam_filter}) && occurred_at >= {time_start_ms} && occurred_at <= {time_end_ms}"

        results = col.search(
            data=[[query_embedding]],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            expr=expr,
            output_fields=["event_id", "camera_id", "occurred_at", "track_id",
                           "bbox_x", "bbox_y", "bbox_w", "bbox_h"],
        )

        return [
            {
                "event_id": h.entity.get("event_id"),
                "camera_id": h.entity.get("camera_id"),
                "occurred_at": h.entity.get("occurred_at"),
                "track_id": h.entity.get("track_id"),
                "bbox": [h.entity.get(f) for f in ["bbox_x", "bbox_y", "bbox_w", "bbox_h"]],
                "similarity": h.score,
            }
            for h in results[0]
        ]
