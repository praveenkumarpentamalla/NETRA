"""
Project NETRA — Bridge Agent Configuration
Loads settings from environment and local config file.
"""

import os
import ssl
from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path
import json


@dataclass
class AgentSettings:
    citizen_id: str
    api_base_url: str
    cert_path: str
    key_path: str
    ca_cert_path: str
    cameras: Dict[str, dict] = field(default_factory=dict)
    pre_roll_seconds: float = 7.0
    post_roll_seconds: float = 12.0
    max_clip_seconds: float = 60.0
    yolo_model_path: str = "/models/edge/yolov8n.onnx"
    version: str = "1.0.0"
    ssl_context: Optional[ssl.SSLContext] = None

    @classmethod
    def from_env(cls) -> "AgentSettings":
        config_path = os.environ.get("NETRA_AGENT_CONFIG", "/etc/netra/agent.json")
        cameras = {}

        if Path(config_path).exists():
            with open(config_path) as f:
                config = json.load(f)
                cameras = config.get("cameras", {})

        cert_path = os.environ.get("NETRA_CERT_PATH", "/certs/agent.crt")
        key_path = os.environ.get("NETRA_KEY_PATH", "/certs/agent.key")
        ca_cert_path = os.environ.get("NETRA_CA_CERT_PATH", "/certs/ca.crt")

        ssl_context = None
        if Path(cert_path).exists() and Path(key_path).exists():
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_context.load_cert_chain(cert_path, key_path)
            if Path(ca_cert_path).exists():
                ssl_context.load_verify_locations(ca_cert_path)

        return cls(
            citizen_id=os.environ.get("NETRA_CITIZEN_ID", "unknown"),
            api_base_url=os.environ.get("NETRA_API_BASE_URL", "https://api.netra.gov.in/v1"),
            cert_path=cert_path,
            key_path=key_path,
            ca_cert_path=ca_cert_path,
            cameras=cameras,
            pre_roll_seconds=float(os.environ.get("NETRA_PRE_ROLL_S", "7.0")),
            post_roll_seconds=float(os.environ.get("NETRA_POST_ROLL_S", "12.0")),
            max_clip_seconds=float(os.environ.get("NETRA_MAX_CLIP_S", "60.0")),
            yolo_model_path=os.environ.get("NETRA_YOLO_MODEL", "/models/edge/yolov8n.onnx"),
            ssl_context=ssl_context,
        )
