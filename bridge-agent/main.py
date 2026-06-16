"""
Project NETRA — Bridge Agent
Edge software that runs on the citizen's device (phone / router / edge box / PC).
Normalises heterogeneous camera feeds, runs edge inference, enforces privacy zones,
uploads event clips, manages WebRTC live-pull tunnels.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from config.settings import AgentSettings
from adapters.adapter_factory import AdapterFactory
from inference.edge_detector import EdgeDetector
from privacy.privacy_masker import PrivacyMasker
from upload.clip_uploader import ClipUploader
from streaming.webrtc_tunnel import WebRTCTunnel
from consent.consent_manager import ConsentManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)
logger = logging.getLogger('bridge-agent')


class BridgeAgent:
    """
    Main Bridge Agent orchestrator.

    Responsibilities:
    1. Discover and connect to registered cameras
    2. Run lightweight edge inference (MOG2 + YOLOv8-nano)
    3. Apply privacy-zone pixel masking before any frame leaves device
    4. Buffer pre-roll (5–10s) for triggered clips
    5. Upload event clips via mTLS HTTPS with resume
    6. Manage WebRTC live-pull tunnels (open only when authorised)
    7. Honour consent state in real time (revocation ≤ 60s)
    8. Self-update via signed release channel
    """

    def __init__(self, settings: AgentSettings):
        self.settings = settings
        self.cameras: dict = {}          # camera_id → adapter
        self.running = False
        self._tasks: list = []

        self.consent_mgr = ConsentManager(settings)
        self.privacy_masker = PrivacyMasker(settings)
        self.edge_detector = EdgeDetector(settings)
        self.clip_uploader = ClipUploader(settings)
        self.webrtc_tunnel = WebRTCTunnel(settings)

    async def start(self):
        logger.info(f"Bridge Agent starting — citizen_id={self.settings.citizen_id}")
        self.running = True

        # Load registered camera configurations from server
        await self._load_camera_configs()

        # Start camera processing loops
        for cam_id, config in self.settings.cameras.items():
            task = asyncio.create_task(
                self._camera_loop(cam_id, config),
                name=f"cam-{cam_id}",
            )
            self._tasks.append(task)

        # Start consent state poll (must propagate revocation within 60s)
        self._tasks.append(asyncio.create_task(
            self._consent_poll_loop(), name="consent-poll",
        ))

        # Start live-pull command listener
        self._tasks.append(asyncio.create_task(
            self._live_pull_listener(), name="live-pull-listener",
        ))

        # Start heartbeat
        self._tasks.append(asyncio.create_task(
            self._heartbeat_loop(), name="heartbeat",
        ))

        logger.info(f"Bridge Agent running — {len(self.cameras)} cameras active")
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        logger.info("Bridge Agent stopping…")
        self.running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.webrtc_tunnel.close_all()
        logger.info("Bridge Agent stopped")

    # ─── Camera processing loop ────────────────────────────────

    async def _camera_loop(self, cam_id: str, config: dict):
        """Main per-camera processing loop."""
        adapter = AdapterFactory.create(config)
        self.cameras[cam_id] = adapter

        logger.info(f"[{cam_id}] Starting — class={config['camera_class']}")

        # Load privacy zones for this camera
        privacy_zones = await self.consent_mgr.get_privacy_zones(cam_id)
        self.privacy_masker.update_zones(cam_id, privacy_zones)

        # Pre-roll ring buffer (5–10 seconds)
        pre_roll_seconds = self.settings.pre_roll_seconds
        pre_roll_buffer = []

        try:
            async for frame, audio, timestamp in adapter.stream():
                if not self.running:
                    break

                # ── CONSENT CHECK ────────────────────────────────
                consent = await self.consent_mgr.get_consent(cam_id)
                if not consent.is_active:
                    logger.info(f"[{cam_id}] Consent inactive — skipping frame")
                    await asyncio.sleep(1)
                    continue

                # ── PRIVACY MASKING ─────────────────────────────
                # Applied BEFORE any frame is stored or analysed
                masked_frame = self.privacy_masker.apply_masks(cam_id, frame)

                # ── PRE-ROLL BUFFER ──────────────────────────────
                pre_roll_buffer.append((masked_frame, audio, timestamp))
                max_buffer = int(pre_roll_seconds * adapter.fps)
                if len(pre_roll_buffer) > max_buffer:
                    pre_roll_buffer.pop(0)

                # ── EDGE INFERENCE ───────────────────────────────
                detection = self.edge_detector.detect(masked_frame, audio, cam_id)

                if detection.triggered:
                    logger.info(
                        f"[{cam_id}] Event triggered: "
                        f"{detection.event_type} (conf={detection.confidence:.2f})"
                    )
                    # Collect post-roll then upload
                    asyncio.create_task(
                        self._collect_and_upload_clip(
                            cam_id, cam_id, list(pre_roll_buffer),
                            detection, adapter,
                        )
                    )

        except asyncio.CancelledError:
            logger.info(f"[{cam_id}] Camera loop cancelled")
        except Exception as e:
            logger.error(f"[{cam_id}] Camera loop error: {e}", exc_info=True)
        finally:
            await adapter.disconnect()

    async def _collect_and_upload_clip(
        self, cam_id: str, camera_label: str,
        pre_roll: list, detection, adapter,
    ):
        """Collect post-roll frames then build and upload clip."""
        post_roll_frames = []
        post_roll_seconds = self.settings.post_roll_seconds
        deadline = asyncio.get_event_loop().time() + post_roll_seconds

        # Collect post-roll
        try:
            async for frame, audio, ts in adapter.stream():
                masked = self.privacy_masker.apply_masks(cam_id, frame)
                post_roll_frames.append((masked, audio, ts))
                if asyncio.get_event_loop().time() >= deadline:
                    break
                if len(post_roll_frames) > post_roll_seconds * adapter.fps:
                    break
        except Exception as e:
            logger.error(f"[{cam_id}] Post-roll error: {e}")

        all_frames = pre_roll + post_roll_frames
        if not all_frames:
            return

        # Build clip
        from upload.clip_builder import ClipBuilder
        builder = ClipBuilder(self.settings)
        clip_path, metadata = await builder.build(
            cam_id=cam_id,
            frames=all_frames,
            detection=detection,
        )

        # Upload with mTLS + bandwidth-aware resume
        await self.clip_uploader.upload(clip_path, metadata)

    # ─── Consent poll loop ────────────────────────────────────

    async def _consent_poll_loop(self):
        """
        Poll server for consent state changes every 15 seconds.
        Must propagate revocation within 60 seconds of citizen tap.
        """
        while self.running:
            try:
                updates = await self.consent_mgr.poll_updates()
                for cam_id, state in updates.items():
                    if state == 'REVOKED':
                        logger.warning(f"[{cam_id}] REVOCATION received — stopping all uplink")
                        await self._handle_revocation(cam_id)
                    elif state == 'PAUSED':
                        logger.info(f"[{cam_id}] Paused by citizen")
                        await self.consent_mgr.set_local_state(cam_id, 'PAUSED')
            except Exception as e:
                logger.error(f"Consent poll error: {e}")
            await asyncio.sleep(15)  # ≤60s propagation guarantee

    async def _handle_revocation(self, cam_id: str):
        """Immediately stop all uplink for a revoked camera."""
        # Stop camera loop
        if cam_id in self.cameras:
            await self.cameras[cam_id].disconnect()
            del self.cameras[cam_id]
        # Close any live tunnel
        await self.webrtc_tunnel.close(cam_id)
        # Cancel pending uploads
        await self.clip_uploader.cancel_camera_uploads(cam_id)
        # Update local state
        await self.consent_mgr.set_local_state(cam_id, 'REVOKED')
        logger.warning(f"[{cam_id}] Revocation complete — all uplink stopped")

    # ─── Live pull listener ───────────────────────────────────

    async def _live_pull_listener(self):
        """
        Listen for authorised live-pull commands from server (via WebSocket).
        Opens WebRTC tunnel ONLY when authorised.
        Citizen IP is NEVER exposed to PCR — TURN relay used.
        """
        while self.running:
            try:
                cmd = await self.webrtc_tunnel.poll_command()
                if cmd is None:
                    await asyncio.sleep(2)
                    continue

                cam_id = cmd['camera_id']
                session_id = cmd['session_id']
                consent = await self.consent_mgr.get_consent(cam_id)

                if not consent.is_active:
                    logger.warning(f"[{cam_id}] Live pull denied — camera not active")
                    await self.webrtc_tunnel.deny(session_id, reason="camera_not_active")
                    continue

                if consent.live_pull_auth == 'ALWAYS_DENY':
                    logger.info(f"[{cam_id}] Live pull denied — citizen preference")
                    await self.webrtc_tunnel.deny(session_id, reason="citizen_deny")
                    continue

                if consent.live_pull_auth == 'ASK_EACH_TIME':
                    # Push notification to citizen app; wait for approval
                    approved = await self.consent_mgr.request_citizen_approval(
                        cam_id, session_id, timeout_s=30,
                    )
                    if not approved:
                        await self.webrtc_tunnel.deny(session_id, reason="citizen_timeout")
                        continue

                # Open WebRTC tunnel via TURN relay
                logger.info(f"[{cam_id}] Opening live-pull tunnel — session {session_id}")
                adapter = self.cameras.get(cam_id)
                if adapter is None:
                    await self.webrtc_tunnel.deny(session_id, reason="camera_not_connected")
                    continue

                asyncio.create_task(
                    self.webrtc_tunnel.open_session(cam_id, session_id, adapter, self.privacy_masker)
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Live pull listener error: {e}")
                await asyncio.sleep(5)

    # ─── Heartbeat ────────────────────────────────────────────

    async def _heartbeat_loop(self):
        """Send heartbeat to server every 60s to update last_seen_at."""
        import aiohttp
        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    for cam_id, adapter in self.cameras.items():
                        async with session.post(
                            f"{self.settings.api_base_url}/cameras/{cam_id}/heartbeat",
                            json={"agent_version": self.settings.version},
                            ssl=self.settings.ssl_context,
                        ) as resp:
                            if resp.status != 200:
                                logger.warning(f"[{cam_id}] Heartbeat failed: {resp.status}")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(60)

    async def _load_camera_configs(self):
        """Load camera configurations from server on startup."""
        # In production: fetch from Camera Service API with mTLS
        # Here we load from local config file
        pass


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

async def main():
    settings = AgentSettings.from_env()
    agent = BridgeAgent(settings)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(agent.stop()))

    try:
        await agent.start()
    except asyncio.CancelledError:
        pass
    finally:
        await agent.stop()

if __name__ == '__main__':
    asyncio.run(main())
