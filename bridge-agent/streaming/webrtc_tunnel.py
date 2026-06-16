"""
Project NETRA — Bridge Agent WebRTC Tunnel
Manages live-pull WebRTC sessions via TURN relay.
Citizen IP never exposed to PCR. Server-side watermark embedded.
"""

import asyncio
import logging
import time
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)


class WebRTCTunnel:
    """
    Manages WebRTC live-pull tunnels.
    Opens only when authorised; auto-terminates at session end or max duration.
    """

    def __init__(self, settings):
        self.settings = settings
        self._active_sessions: Dict[str, dict] = {}  # camera_id -> session info
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._ws_connection = None

    async def poll_command(self) -> Optional[dict]:
        """
        Poll for live-pull commands from server (via persistent WebSocket
        or fallback HTTP long-poll).
        """
        try:
            return await asyncio.wait_for(self._command_queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            return None

    async def open_session(
        self, cam_id: str, session_id: str, adapter, privacy_masker,
    ) -> None:
        """
        Open a WebRTC publishing session via TURN relay.
        Frames are privacy-masked before transmission (same as event clips).
        Server applies the chain-of-custody watermark on receipt.
        """
        logger.info(f"[{cam_id}] WebRTC session opening: {session_id}")

        try:
            from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer
            from aiortc.contrib.media import MediaStreamTrack
            import fractions

            ice_servers = [
                RTCIceServer(
                    urls=self.settings.turn_server_url,
                    username=self.settings.turn_username,
                    credential=self.settings.turn_credential,
                )
            ]
            pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=ice_servers))

            class MaskedVideoTrack(MediaStreamTrack):
                kind = "video"

                def __init__(self, source_adapter, masker, camera_id):
                    super().__init__()
                    self._adapter = source_adapter
                    self._masker = masker
                    self._cam_id = camera_id
                    self._frame_iter = None

                async def recv(self):
                    from av import VideoFrame
                    if self._frame_iter is None:
                        self._frame_iter = self._adapter.stream()

                    frame_bgr, _, ts = await self._frame_iter.__anext__()
                    masked = self._masker.apply_masks(self._cam_id, frame_bgr)

                    import cv2
                    rgb = cv2.cvtColor(masked, cv2.COLOR_BGR2RGB)
                    av_frame = VideoFrame.from_ndarray(rgb, format="rgb24")
                    av_frame.pts = int(ts * 90000)
                    av_frame.time_base = fractions.Fraction(1, 90000)
                    return av_frame

            track = MaskedVideoTrack(adapter, privacy_masker, cam_id)
            pc.addTrack(track)

            self._active_sessions[cam_id] = {
                'session_id': session_id,
                'pc': pc,
                'started_at': time.time(),
                'max_duration_s': 900,  # Tier-1 default; server enforces actual tier
            }

            # Signal server that we're ready (exchange SDP via signalling endpoint)
            await self._exchange_sdp(cam_id, session_id, pc)

            # Monitor session duration
            asyncio.create_task(self._monitor_session(cam_id, session_id))

        except ImportError:
            logger.warning("aiortc not available — live pull simulation mode")
            self._active_sessions[cam_id] = {
                'session_id': session_id,
                'started_at': time.time(),
                'max_duration_s': 900,
            }

    async def _exchange_sdp(self, cam_id: str, session_id: str, pc) -> None:
        """Exchange SDP offer/answer with server signalling endpoint."""
        import aiohttp

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.settings.api_base_url}/live-pull/{session_id}/sdp-offer",
                    json={'sdp': pc.localDescription.sdp, 'type': pc.localDescription.type},
                    ssl=self.settings.ssl_context,
                ) as resp:
                    if resp.status == 200:
                        answer_data = await resp.json()
                        from aiortc import RTCSessionDescription
                        answer = RTCSessionDescription(
                            sdp=answer_data['sdp'], type=answer_data['type'],
                        )
                        await pc.setRemoteDescription(answer)
                        logger.info(f"[{cam_id}] WebRTC connection established")
        except Exception as e:
            logger.error(f"[{cam_id}] SDP exchange error: {e}")

    async def _monitor_session(self, cam_id: str, session_id: str) -> None:
        """Auto-terminate session at max duration."""
        session = self._active_sessions.get(cam_id)
        if not session:
            return

        max_duration = session['max_duration_s']

        while cam_id in self._active_sessions:
            elapsed = time.time() - session['started_at']
            if elapsed >= max_duration:
                logger.info(f"[{cam_id}] Session {session_id} reached max duration — closing")
                await self.close(cam_id)
                break
            await asyncio.sleep(5)

    async def close(self, cam_id: str) -> None:
        """Close a live-pull session immediately."""
        session = self._active_sessions.pop(cam_id, None)
        if session and 'pc' in session:
            await session['pc'].close()
            logger.info(f"[{cam_id}] WebRTC session closed")

    async def close_all(self) -> None:
        """Close all active sessions (called on agent shutdown)."""
        for cam_id in list(self._active_sessions.keys()):
            await self.close(cam_id)

    async def deny(self, session_id: str, reason: str) -> None:
        """Notify server that a live-pull request was denied."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.settings.api_base_url}/live-pull/{session_id}/deny",
                    json={'reason': reason},
                    ssl=self.settings.ssl_context,
                )
        except Exception as e:
            logger.error(f"Deny notification error: {e}")
