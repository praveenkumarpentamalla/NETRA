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


I've thoroughly read the Project NETRA document. This is an extraordinarily complex, 20-part request covering a complete production-grade public safety platform. Let me deliver this comprehensively, part by part.This is one of the most comprehensive technical challenges I've encountered. I'll deliver all 20 parts systematically. Let me begin.

---

# PROJECT NETRA — Complete Technical Blueprint

## PART 1 — PROJECT UNDERSTANDING**Problem Statement:** India has a bifurcated CCTV ecosystem. State cameras cover arterial roads; citizen cameras (50–200 per 500m in urban areas) cover the residential interiors where most crime occurs — but remain invisible to law enforcement. After incidents, IOs spend days physically walking neighbourhoods asking for footage that's already been overwritten.

**Goals:** Build a production-grade, vendor-agnostic, citizen-consented platform that bridges citizen cameras to the police PCR (Police Control Room) with privacy, governance, and purpose limitation as structural load-bearing elements.

**Business Flow:** Citizens voluntarily register cameras → Bridge Agent normalises feeds → event clips upload on trigger → analytics run on server → alerts surface in PCR console → IO investigates within case scope → audit log records every action → citizen sees full transparency history.

---

## PART 2 — COMPLETE SYSTEM FLOWEvery step explained:

**Citizen → Mobile App:** The citizen uses the Flutter/Android app to register cameras, draw privacy-zone polygons over still frames, set operating hours, and choose live-pull authorization preferences. Identity is pseudonymised — only a Citizen-ID reaches the PCR.

**Bridge Agent → Camera Adapters:** The Bridge Agent software runs on the citizen's device (phone, router, edge box, or PC). It discovers cameras via ONVIF WS-Discovery, direct RTSP URLs, vendor OAuth (Tapo/Ring), or DVR backplanes and normalises all streams to H.265/H.264 fragmented MP4.

**Edge Processing → Event Trigger:** Lightweight YOLOv8-nano and MOG2 run on-device at ≥12fps. When motion, a person, vehicle, or audio anomaly is detected, the agent assembles a clip with 5–10s pre-roll and 10–15s post-roll, enforces privacy-zone pixel masking, then uploads via bandwidth-aware chunked HTTPS with mTLS.

**Kafka:** All clips and events publish to Kafka topics (`netra.clips.raw`, `netra.events`, `netra.alerts`). Consumers are independent microservices that can scale independently.

**Analytics Services → AI Modules:** ANPR (YOLOv8 + PaddleOCR), Face Recognition (RetinaFace + ArcFace), Person/Vehicle Re-ID (OSNet/FastReID), Behavior (X3D/SlowFast), Audio (YAMNet/PANN) each consume from Kafka and write results back. All outputs include calibrated confidence scores.

**Metadata + Vector DB:** PostgreSQL/PostGIS stores all structured event metadata, investigation records, watchlist entries. Milvus/Qdrant stores 512-D face and vehicle re-ID embeddings for similarity search.

**Investigation Engine → PCR Console:** The map-first React console lets IOs search by attribute, plate, face crop, or person crop within case scope. Multi-camera synchronized timelines enable trajectory reconstruction.

**Audit Logs:** Every action — every search, every live pull, every FR attestation, every watchlist mutation — is appended to a hash-chained append-only log with daily Merkle-root publication for external attestability.

---

## PART 3 — MICROSERVICE ARCHITECTURENow let me generate the complete source code files. Given the scale of this project, I'll build everything systematically:Now let me build the complete codebase:## PART 4 — DATABASE DESIGN
