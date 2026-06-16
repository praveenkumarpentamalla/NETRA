# ──────────────────────────────────────────────────────────────
# Project NETRA — Bridge Agent Dockerfile
# Multi-arch: supports ARM (Raspberry Pi/Jetson) and x86 (PC)
# ──────────────────────────────────────────────────────────────

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 \
    ffmpeg \
    libavformat-dev libavcodec-dev libavdevice-dev \
    libavutil-dev libswscale-dev libswresample-dev libavfilter-dev \
    libsrtp2-dev libopus-dev libvpx-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1001 netra-agent
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=netra-agent:netra-agent . .

# Directories for models and certs (mounted at runtime)
RUN mkdir -p /models/edge /certs && chown -R netra-agent:netra-agent /models /certs

USER netra-agent

# Self-update channel verification happens at startup
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 8765)); s.close()" || exit 1

ENTRYPOINT ["python", "main.py"]
