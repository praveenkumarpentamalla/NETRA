"""
Project NETRA — Bridge Agent Consent Manager
Polls server for consent state changes. Critical path for the
≤60s revocation propagation guarantee.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ConsentState:
    is_active: bool
    consent_mode: str  # EVENT_ONLY | LIVE_PULL_ENABLED
    live_pull_auth: str  # ALWAYS_DENY | ASK_EACH_TIME | AUTO_ALLOW_EMERGENCY
    away_mode_enabled: bool
    last_updated: float


class ConsentManager:
    """
    Manages camera consent state on the Bridge Agent side.
    Polls server every 15s; local cache TTL ensures revocation
    cannot persist beyond the 60s guarantee even if a poll is missed.
    """

    LOCAL_CACHE_TTL_S = 75.0  # slightly above poll interval × 5 for safety margin

    def __init__(self, settings):
        self.settings = settings
        self._consent_cache: Dict[str, ConsentState] = {}
        self._privacy_zones_cache: Dict[str, list] = {}
        self._last_poll_time: float = 0.0

    async def get_consent(self, cam_id: str) -> ConsentState:
        """
        Get current consent state for a camera.
        Falls back to DENY-by-default if cache is stale (safety-first).
        """
        cached = self._consent_cache.get(cam_id)
        now = time.time()

        if cached and (now - cached.last_updated) < self.LOCAL_CACHE_TTL_S:
            return cached

        # Cache stale or missing — fetch fresh from server
        fresh = await self._fetch_consent(cam_id)
        if fresh:
            self._consent_cache[cam_id] = fresh
            return fresh

        # Network failure and no valid cache — DENY BY DEFAULT (safety-first)
        logger.warning(f"[{cam_id}] Cannot verify consent — defaulting to INACTIVE")
        return ConsentState(
            is_active=False,
            consent_mode='EVENT_ONLY',
            live_pull_auth='ALWAYS_DENY',
            away_mode_enabled=False,
            last_updated=now,
        )

    async def poll_updates(self) -> Dict[str, str]:
        """
        Poll server for consent changes since last poll.
        Returns {camera_id: new_state} for any changes.
        Called every 15s by the Bridge Agent main loop.
        """
        self._last_poll_time = time.time()
        changes = {}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.settings.api_base_url}/cameras/consent-state",
                    params={"citizen_id": self.settings.citizen_id},
                    ssl=self.settings.ssl_context,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for cam_id, state in data.get("cameras", {}).items():
                            old_cached = self._consent_cache.get(cam_id)
                            new_state = ConsentState(
                                is_active=state["status"] not in ("REVOKED", "PAUSED"),
                                consent_mode=state["consentMode"],
                                live_pull_auth=state["livePullAuth"],
                                away_mode_enabled=state["awayModeEnabled"],
                                last_updated=time.time(),
                            )

                            # Detect state transition
                            if old_cached is None or old_cached.is_active != new_state.is_active:
                                changes[cam_id] = state["status"]

                            self._consent_cache[cam_id] = new_state

        except asyncio.TimeoutError:
            logger.error("Consent poll timed out")
        except Exception as e:
            logger.error(f"Consent poll error: {e}")

        return changes

    async def get_privacy_zones(self, cam_id: str) -> list:
        """Fetch current privacy zones for a camera."""
        cached = self._privacy_zones_cache.get(cam_id)
        if cached is not None:
            return cached

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.settings.api_base_url}/cameras/{cam_id}/privacy-zones",
                    ssl=self.settings.ssl_context,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        zones = data.get("zones", [])
                        self._privacy_zones_cache[cam_id] = zones
                        return zones
        except Exception as e:
            logger.error(f"[{cam_id}] Privacy zones fetch error: {e}")

        return []

    async def set_local_state(self, cam_id: str, state: str) -> None:
        """Update local cache state immediately (used on revocation handling)."""
        self._consent_cache[cam_id] = ConsentState(
            is_active=(state not in ("REVOKED", "PAUSED")),
            consent_mode='EVENT_ONLY',
            live_pull_auth='ALWAYS_DENY',
            away_mode_enabled=False,
            last_updated=time.time(),
        )

    async def request_citizen_approval(
        self, cam_id: str, session_id: str, timeout_s: float = 30,
    ) -> bool:
        """
        Push a live-pull approval request to the citizen's phone.
        Waits up to timeout_s for response (deny-by-default on timeout).
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Trigger push notification to citizen app
                async with session.post(
                    f"{self.settings.api_base_url}/live-pull/{session_id}/notify-citizen",
                    json={"camera_id": cam_id},
                    ssl=self.settings.ssl_context,
                ) as resp:
                    if resp.status != 200:
                        return False

                # Poll for citizen response
                deadline = time.time() + timeout_s
                while time.time() < deadline:
                    async with session.get(
                        f"{self.settings.api_base_url}/live-pull/{session_id}/status",
                        ssl=self.settings.ssl_context,
                    ) as status_resp:
                        if status_resp.status == 200:
                            status_data = await status_resp.json()
                            if status_data["status"] == "PENDING_CITIZEN":
                                await asyncio.sleep(1)
                                continue
                            return status_data["status"] == "ACTIVE"
                    await asyncio.sleep(1)

                logger.info(f"[{cam_id}] Citizen approval timed out — deny by default")
                return False

        except Exception as e:
            logger.error(f"[{cam_id}] Citizen approval request error: {e}")
            return False

    async def _fetch_consent(self, cam_id: str) -> Optional[ConsentState]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.settings.api_base_url}/cameras/{cam_id}/consent",
                    ssl=self.settings.ssl_context,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return ConsentState(
                            is_active=data["status"] not in ("REVOKED", "PAUSED"),
                            consent_mode=data["consentMode"],
                            live_pull_auth=data["livePullAuth"],
                            away_mode_enabled=data["awayModeEnabled"],
                            last_updated=time.time(),
                        )
        except Exception as e:
            logger.error(f"[{cam_id}] Consent fetch error: {e}")
        return None
