"""
Project NETRA — Camera Adapter Factory
Supports: ONVIF, Generic RTSP, Vendor Cloud APIs, DVR/NVR, Phone, Dashcam, USB.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class CameraAdapter(ABC):
    """Base class for all camera adapters."""

    fps: float = 15.0
    width: int = 1280
    height: int = 720

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to camera. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect and release resources."""
        ...

    @abstractmethod
    async def stream(self) -> AsyncIterator[Tuple[np.ndarray, Optional[bytes], float]]:
        """Yield (frame_bgr, audio_chunk_or_None, timestamp_epoch)."""
        ...

    @abstractmethod
    async def get_snapshot(self) -> np.ndarray:
        """Capture a single still frame (for FOV validation)."""
        ...


# ──────────────────────────────────────────────────────────────
# ONVIF Adapter
# ──────────────────────────────────────────────────────────────

class ONVIFAdapter(CameraAdapter):
    """
    ONVIF Profile S/T cameras: Hikvision, Dahua, Axis, CP Plus, etc.
    Uses WS-Discovery + RTSP pull.
    """

    def __init__(self, config: dict):
        self.host = config['host']
        self.port = config.get('port', 80)
        self.username = config['username']
        self.password = config['password']
        self._rtsp_url: Optional[str] = None
        self._cap = None

    async def connect(self) -> bool:
        try:
            from onvif import ONVIFCamera
            cam = ONVIFCamera(self.host, self.port, self.username, self.password)
            await asyncio.to_thread(cam.update_xaddrs)
            media = cam.create_media_service()
            profiles = await asyncio.to_thread(media.GetProfiles)
            token = profiles[0].token
            uri_request = media.create_type('GetStreamUri')
            uri_request.ProfileToken = token
            uri_request.StreamSetup = {
                'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'},
            }
            uri = await asyncio.to_thread(media.GetStreamUri, uri_request)
            self._rtsp_url = uri.Uri
            # Inject credentials into RTSP URL
            self._rtsp_url = self._rtsp_url.replace(
                'rtsp://', f'rtsp://{self.username}:{self.password}@'
            )
            logger.info(f"ONVIF connected: {self.host}")
            return await self._open_capture()
        except Exception as e:
            logger.error(f"ONVIF connect failed {self.host}: {e}")
            return False

    async def disconnect(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    async def stream(self) -> AsyncIterator:
        if not self._cap:
            if not await self.connect():
                return
        import cv2, time
        while True:
            ret, frame = await asyncio.to_thread(self._cap.read)
            if not ret:
                logger.warning("ONVIF stream ended, reconnecting...")
                await asyncio.sleep(3)
                await self.connect()
                continue
            yield frame, None, time.time()
            await asyncio.sleep(1.0 / self.fps)

    async def get_snapshot(self) -> np.ndarray:
        if not self._cap:
            await self.connect()
        ret, frame = await asyncio.to_thread(self._cap.read)
        return frame if ret else np.zeros((720, 1280, 3), dtype=np.uint8)

    async def _open_capture(self) -> bool:
        import cv2
        self._cap = cv2.VideoCapture(self._rtsp_url, cv2.CAP_FFMPEG)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        return self._cap.isOpened()


# ──────────────────────────────────────────────────────────────
# Generic RTSP Adapter
# ──────────────────────────────────────────────────────────────

class RTSPAdapter(CameraAdapter):
    """Direct RTSP URL adapter — most IP cameras, IP doorbells."""

    def __init__(self, config: dict):
        self.rtsp_url = config['rtsp_url']
        self._cap = None

    async def connect(self) -> bool:
        import cv2
        self._cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        if self._cap.isOpened():
            self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 15.0
            self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(f"RTSP connected: {self.rtsp_url[:40]}... ({self.width}x{self.height}@{self.fps}fps)")
            return True
        logger.error(f"RTSP connect failed: {self.rtsp_url}")
        return False

    async def disconnect(self) -> None:
        if self._cap:
            self._cap.release()

    async def stream(self) -> AsyncIterator:
        if not self._cap or not self._cap.isOpened():
            if not await self.connect():
                return
        import time
        while True:
            ret, frame = await asyncio.to_thread(self._cap.read)
            if not ret:
                await asyncio.sleep(3)
                await self.connect()
                continue
            yield frame, None, time.time()
            await asyncio.sleep(1.0 / self.fps)

    async def get_snapshot(self) -> np.ndarray:
        if not self._cap:
            await self.connect()
        ret, frame = await asyncio.to_thread(self._cap.read)
        return frame if ret else np.zeros((720, 1280, 3), np.uint8)


# ──────────────────────────────────────────────────────────────
# Vendor Cloud API Adapter (Tapo / Ring / Wyze etc.)
# ──────────────────────────────────────────────────────────────

class VendorCloudAdapter(CameraAdapter):
    """
    Consumer cloud cameras via citizen-authorised OAuth.
    Platform operates as read-only OAuth client — never bypasses vendor terms.
    Falls back to RTSP-over-LAN if vendor exposes it.
    """

    def __init__(self, config: dict):
        self.vendor = config['vendor']  # tapo | ring | wyze | eufy
        self.oauth_token = config['oauth_token']
        self.device_id = config['device_id']
        self._rtsp_fallback: Optional[RTSPAdapter] = None

    async def connect(self) -> bool:
        # Try RTSP-over-LAN first (faster, private)
        rtsp_url = await self._get_local_rtsp()
        if rtsp_url:
            self._rtsp_fallback = RTSPAdapter({'rtsp_url': rtsp_url})
            return await self._rtsp_fallback.connect()
        logger.info(f"[{self.vendor}] No LAN RTSP, using cloud relay")
        return True

    async def disconnect(self) -> None:
        if self._rtsp_fallback:
            await self._rtsp_fallback.disconnect()

    async def stream(self) -> AsyncIterator:
        if self._rtsp_fallback:
            async for frame, audio, ts in self._rtsp_fallback.stream():
                yield frame, audio, ts
        else:
            # Cloud relay polling (vendor-specific SDK)
            import time
            while True:
                frame = await self._fetch_cloud_frame()
                if frame is not None:
                    yield frame, None, time.time()
                await asyncio.sleep(1.0 / self.fps)

    async def get_snapshot(self) -> np.ndarray:
        if self._rtsp_fallback:
            return await self._rtsp_fallback.get_snapshot()
        return await self._fetch_cloud_frame() or np.zeros((720, 1280, 3), np.uint8)

    async def _get_local_rtsp(self) -> Optional[str]:
        """Attempt to find RTSP stream on local network for supported vendors."""
        # Tapo devices expose RTSP on local network
        if self.vendor == 'tapo':
            return f"rtsp://admin:{self.oauth_token}@{self.device_id}:554/stream1"
        return None

    async def _fetch_cloud_frame(self) -> Optional[np.ndarray]:
        """Vendor-SDK frame fetch (simplified)."""
        return np.zeros((720, 1280, 3), np.uint8)


# ──────────────────────────────────────────────────────────────
# Phone Camera Adapter (WebRTC publish)
# ──────────────────────────────────────────────────────────────

class PhoneCameraAdapter(CameraAdapter):
    """Smartphone camera via aiortc WebRTC publish."""

    def __init__(self, config: dict):
        self.device_id = config.get('device_id', 0)
        self._cap = None

    async def connect(self) -> bool:
        import cv2
        self._cap = cv2.VideoCapture(self.device_id)
        return self._cap.isOpened()

    async def disconnect(self) -> None:
        if self._cap:
            self._cap.release()

    async def stream(self) -> AsyncIterator:
        import time
        while True:
            ret, frame = await asyncio.to_thread(self._cap.read)
            if not ret:
                await asyncio.sleep(0.1)
                continue
            yield frame, None, time.time()
            await asyncio.sleep(1.0 / 30.0)

    async def get_snapshot(self) -> np.ndarray:
        ret, frame = await asyncio.to_thread(self._cap.read)
        return frame if ret else np.zeros((720, 1280, 3), np.uint8)


# ──────────────────────────────────────────────────────────────
# USB / Webcam Adapter (V4L2 / Media Foundation)
# ──────────────────────────────────────────────────────────────

class USBWebcamAdapter(RTSPAdapter):
    """USB/Webcam via OpenCV — V4L2 on Linux, Media Foundation on Windows."""

    def __init__(self, config: dict):
        import platform
        device_index = config.get('device_index', 0)
        if platform.system() == 'Linux':
            rtsp_url = str(device_index)  # V4L2 device index
        else:
            rtsp_url = str(device_index)  # Windows camera index
        super().__init__({'rtsp_url': rtsp_url})
        self._device_index = device_index

    async def connect(self) -> bool:
        import cv2
        self._cap = cv2.VideoCapture(self._device_index)
        return self._cap.isOpened()


# ──────────────────────────────────────────────────────────────
# Adapter Factory
# ──────────────────────────────────────────────────────────────

class AdapterFactory:
    """Creates the appropriate camera adapter based on camera class."""

    _registry = {
        'ONVIF': ONVIFAdapter,
        'RTSP': RTSPAdapter,
        'VENDOR_CLOUD': VendorCloudAdapter,
        'DVR_NVR': ONVIFAdapter,       # DVRs often expose ONVIF/RTSP
        'PHONE_CAMERA': PhoneCameraAdapter,
        'DASHCAM': RTSPAdapter,        # Dashcams with Wi-Fi RTSP
        'USB_WEBCAM': USBWebcamAdapter,
    }

    @classmethod
    def create(cls, config: dict) -> CameraAdapter:
        camera_class = config.get('camera_class', 'RTSP').upper()
        adapter_cls = cls._registry.get(camera_class)
        if adapter_cls is None:
            raise ValueError(f"Unsupported camera class: {camera_class}")
        return adapter_cls(config)
