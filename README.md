# Project NETRA
## Networked Eyes for Tactical Response and Awareness

> A Citizen-Consented, Camera-Agnostic, Hybrid Video-Intelligence Platform for Public Safety

---

## Architecture at a Glance

```
Citizen (Mobile App)
  ↓ consent + camera register
Bridge Agent (Edge)
  ↓ mTLS + H.265 clips
Ingestion API
  ↓ Kafka
Analytics Pipeline (ANPR · Face · ReID · Behavior · Audio)
  ↓ PostgreSQL + Milvus
Investigation Engine
  ↓ REST/GraphQL
PCR Console (React)
```

---

## Repository Structure

```
netra/
├── apps/
│   ├── citizen-mobile/      # Flutter app (Android primary)
│   ├── pcr-console/         # React + Next.js + MapLibre
│   └── admin-dashboard/     # React admin panel
├── services/
│   ├── auth/                # NestJS – JWT, OTP, MFA
│   ├── citizen/             # NestJS – profiles, pseudonymisation
│   ├── camera/              # NestJS – registry, FOV, state
│   ├── consent/             # NestJS – per-camera consent
│   ├── event/               # NestJS – triggers, clips
│   ├── streaming/           # Go – WebRTC/SRT/HLS
│   ├── analytics/           # Python FastAPI – AI pipeline orchestrator
│   ├── anpr/                # Python FastAPI – plate detection + OCR
│   ├── face-recognition/    # Python FastAPI – ArcFace + governed
│   ├── watchlist/           # NestJS – governed watchlist management
│   ├── investigation/       # NestJS – cases, scope, search
│   ├── audit/               # NestJS – hash-chained audit log
│   ├── live-pull/           # Go – WebRTC tunnel management
│   └── notification/        # NestJS – push, FCM, transparency
├── ai/
│   ├── anpr/                # YOLO + PaddleOCR training + inference
│   ├── face-recognition/    # RetinaFace + ArcFace pipelines
│   ├── person-reid/         # OSNet + FastReID
│   ├── audio/               # YAMNet + PANN classifiers
│   ├── behavior/            # X3D + SlowFast + CSRNet
│   └── calibration/         # Platt scaling, ECE evaluation
├── bridge-agent/            # Python – edge agent
│   ├── adapters/            # ONVIF, RTSP, cloud APIs
│   ├── inference/           # Edge YOLOv8-nano
│   ├── privacy/             # Pixel-level masking
│   ├── upload/              # Chunked HTTPS uploader
│   └── streaming/           # WebRTC/aiortc
├── database/
│   ├── migrations/          # Flyway SQL migrations
│   └── seeds/               # Dev/test seed data
├── infrastructure/
│   ├── docker/              # Dockerfiles per service
│   ├── k8s/                 # Kubernetes manifests
│   ├── terraform/           # AWS EKS infrastructure
│   ├── monitoring/          # Prometheus + Grafana + Loki
│   └── ci-cd/               # GitHub Actions workflows
└── shared/
    ├── types/               # Shared TypeScript types
    └── proto/               # gRPC protobuf definitions
```

---

## Quick Start

### Prerequisites
- Docker 24+ & Docker Compose
- Node.js 20+, Python 3.11+, Go 1.22+, Flutter 3.19+
- AWS CLI (for cloud deploy)

### Local Development

```bash
cp .env.example .env
docker compose up -d postgres redis kafka minio milvus vault
cd services/auth && npm install && npm run start:dev
# ... start other services
cd apps/pcr-console && npm install && npm run dev
```

### Environment Variables

See `.env.example` for all required variables.

---

## Compliance

This system is designed for compliance with:
- Constitution of India, Articles 19 & 21 (Puttaswamy 2017 privacy judgment)
- DPDP Act 2023
- BNS, BNSS, BSA 2023
- IT Act 2000 (as amended)
- Aadhaar Act 2016 + UIDAI Authentication Regulations

See `docs/legal-mapping.md` for the section-by-section mapping.

---

## License

Apache 2.0 — see LICENSE. All AI models must ship with model cards (see `ai/*/MODEL_CARD.md`).
