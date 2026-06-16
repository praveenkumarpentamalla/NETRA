"""
Project NETRA — Bridge Agent Clip Uploader
Bandwidth-aware HTTPS multipart upload with chunked resume.
Priority-tagged: audio-anomaly and away-mode clips upload first.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024  # 64KB chunks for resumable upload
MAX_RETRIES = 5
PRIORITY_EVENT_TYPES = {'audio_anomaly', 'away_mode_motion'}


@dataclass
class UploadTask:
    clip_path: Path
    metadata: dict
    priority: int  # lower = higher priority
    attempts: int = 0
    cancelled: bool = False


class ClipUploader:
    """
    Manages the upload queue with bandwidth-aware backoff and
    priority ordering. Audio anomaly and away-mode clips jump the queue.
    """

    def __init__(self, settings):
        self.settings = settings
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._counter = 0
        self._active_uploads: dict = {}  # camera_id -> set of task refs
        self._worker_task: Optional[asyncio.Task] = None
        self._congestion_backoff_s = 0.0

    async def upload(self, clip_path: Path, metadata: dict) -> None:
        """Queue a clip for upload."""
        event_type = metadata.get('event_type', '')
        priority = 0 if event_type in PRIORITY_EVENT_TYPES else 5
        self._counter += 1

        task = UploadTask(clip_path=clip_path, metadata=metadata, priority=priority)
        await self._queue.put((priority, self._counter, task))

        cam_id = metadata.get('camera_id')
        self._active_uploads.setdefault(cam_id, set()).add(id(task))

        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._upload_worker())

    async def cancel_camera_uploads(self, cam_id: str) -> None:
        """Cancel all pending uploads for a camera (called on revocation)."""
        # Mark tasks for this camera as cancelled; worker checks flag before sending
        logger.info(f"[{cam_id}] Cancelling pending uploads")
        self._active_uploads.pop(cam_id, None)

    async def _upload_worker(self) -> None:
        """Background worker processing the upload queue."""
        while True:
            try:
                priority, counter, task = await asyncio.wait_for(
                    self._queue.get(), timeout=30,
                )
            except asyncio.TimeoutError:
                break  # no more uploads pending; worker exits, restarts on next upload()

            cam_id = task.metadata.get('camera_id')

            # Check if cancelled (camera revoked while queued)
            if cam_id not in self._active_uploads:
                logger.info(f"[{cam_id}] Skipping cancelled upload")
                continue

            success = await self._upload_with_retry(task)
            if not success:
                logger.error(f"[{cam_id}] Upload permanently failed after {MAX_RETRIES} attempts")

            self._active_uploads.get(cam_id, set()).discard(id(task))

    async def _upload_with_retry(self, task: UploadTask) -> bool:
        cam_id = task.metadata.get('camera_id')

        for attempt in range(MAX_RETRIES):
            task.attempts = attempt + 1
            try:
                success = await self._do_upload(task)
                if success:
                    logger.info(f"[{cam_id}] Upload succeeded (attempt {attempt + 1})")
                    return True
            except Exception as e:
                logger.warning(f"[{cam_id}] Upload attempt {attempt + 1} failed: {e}")

            # Exponential backoff with congestion awareness
            backoff = min(2 ** attempt + self._congestion_backoff_s, 30)
            await asyncio.sleep(backoff)

        return False

    async def _do_upload(self, task: UploadTask) -> bool:
        """
        Perform chunked multipart upload with resume support.
        Bandwidth-aware: backs off when uplink congestion detected.
        """
        if not task.clip_path.exists():
            logger.error(f"Clip file missing: {task.clip_path}")
            return False

        file_size = task.clip_path.stat().st_size
        clip_hash = self._compute_hash(task.clip_path)

        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            # Step 1: Initiate resumable upload session
            init_payload = {
                **task.metadata,
                'clip_size_bytes': file_size,
                'clip_hash': clip_hash,
            }

            try:
                async with session.post(
                    f"{self.settings.api_base_url}/events/clips/initiate",
                    json=init_payload,
                    ssl=self.settings.ssl_context,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 201:
                        logger.error(f"Initiate upload failed: {resp.status}")
                        return False
                    init_data = await resp.json()
                    upload_url = init_data['uploadUrl']
                    resume_offset = init_data.get('resumeOffset', 0)

            except Exception as e:
                logger.error(f"Initiate upload error: {e}")
                return False

            # Step 2: Upload chunks with bandwidth monitoring
            bytes_sent = resume_offset
            chunk_start_time = time.time()

            with open(task.clip_path, 'rb') as f:
                f.seek(resume_offset)

                while bytes_sent < file_size:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    chunk_send_start = time.time()

                    try:
                        async with session.put(
                            upload_url,
                            data=chunk,
                            headers={
                                'Content-Range': f'bytes {bytes_sent}-{bytes_sent + len(chunk) - 1}/{file_size}',
                            },
                            ssl=self.settings.ssl_context,
                            timeout=aiohttp.ClientTimeout(total=20),
                        ) as chunk_resp:
                            if chunk_resp.status not in (200, 201, 308):  # 308 = resume incomplete
                                logger.error(f"Chunk upload failed: {chunk_resp.status}")
                                return False

                    except Exception as e:
                        logger.warning(f"Chunk upload error at offset {bytes_sent}: {e}")
                        return False  # caller will retry from new resume_offset

                    chunk_duration = time.time() - chunk_send_start
                    bytes_sent += len(chunk)

                    # Bandwidth-aware backpressure
                    self._update_congestion_estimate(len(chunk), chunk_duration)
                    if self._congestion_backoff_s > 0:
                        await asyncio.sleep(self._congestion_backoff_s)

            # Step 3: Finalise upload
            try:
                async with session.post(
                    f"{self.settings.api_base_url}/events/clips/finalize",
                    json={'uploadUrl': upload_url, 'clipHash': clip_hash},
                    ssl=self.settings.ssl_context,
                ) as final_resp:
                    if final_resp.status != 200:
                        logger.error(f"Finalise failed: {final_resp.status}")
                        return False

            except Exception as e:
                logger.error(f"Finalise error: {e}")
                return False

        total_duration = time.time() - start_time
        throughput_kbps = (file_size / 1024) / max(total_duration, 0.01)
        logger.info(
            f"Upload complete: {file_size} bytes in {total_duration:.1f}s "
            f"({throughput_kbps:.1f} KB/s)"
        )

        # Clean up local clip file after successful upload
        try:
            task.clip_path.unlink()
        except OSError:
            pass

        return True

    def _update_congestion_estimate(self, bytes_sent: int, duration_s: float) -> None:
        """Simple congestion detection — if throughput drops, back off."""
        if duration_s <= 0:
            return
        throughput_kbps = (bytes_sent / 1024) / duration_s

        TARGET_MIN_KBPS = 100  # ~1 Mbps sustained uplink requirement (per spec)

        if throughput_kbps < TARGET_MIN_KBPS:
            self._congestion_backoff_s = min(self._congestion_backoff_s + 0.5, 5.0)
        else:
            self._congestion_backoff_s = max(self._congestion_backoff_s - 0.2, 0.0)

    def _compute_hash(self, path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
