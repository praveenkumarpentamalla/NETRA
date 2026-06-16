# Project NETRA — Architecture Document

## Networked Eyes for Tactical Response and Awareness

**A Citizen-Consented, Camera-Agnostic, Hybrid Video-Intelligence Platform for Public Safety**

---

## 1. Executive Summary

NETRA bridges the gap between India's 50–200 citizen-owned cameras per urban neighbourhood and law enforcement's investigative needs, without becoming a surveillance instrument. The architecture treats governance — consent, bystander protection, watchlist discipline, purpose limitation — as load-bearing structure, not a policy layer bolted onto a vision pipeline.

Four design rules govern every component:
1. **Citizen-pull, not police-push** — no camera enters the system without explicit registration
2. **Bystanders matter as much as participants** — privacy zones and FOV validation are mandatory, not optional
3. **Face recognition is lead-generation, not identification** — top-N candidates, mandatory attestation, never autonomous
4. **Hybrid by default, live by exception** — event clips are the default uplink; live pulls are logged exceptions

---

## 2. System Architecture Overview

```
Citizen Mobile App (Flutter)
        │ consent, FOV, privacy zones
        ▼
Bridge Agent (Python, edge device)
        │ mTLS + H.265 clips / WebRTC live-pull
        ▼
Ingestion API (NestJS microservices)
        │ Kafka event bus
        ▼
Analytics Pipeline (Python FastAPI — ANPR, FR, Re-ID, Audio, Behavior)
        │ PostgreSQL + PostGIS + Milvus
        ▼
Investigation Engine (NestJS — case-scoped search)
        │ REST/GraphQL
        ▼
PCR Console (React + Next.js + MapLibre)
```

24 microservices span 5 domains: Citizen, Ingestion, Analytics, Investigation, Operations/Platform. Each communicates internally via gRPC and externally via REST/GraphQL, all behind mTLS.

---

## 3. Key Architectural Decisions

### 3.1 Pseudonymisation Boundary

The PCR console never sees a citizen's name, phone, or address. The `citizens` table stores encrypted PII; the `cameras` table exposes only a pseudonymous `camera_id` and a geo-point with a citizen-set precision floor (default ±25m). Identity linkage requires a documented, role-gated, audit-logged "owner contact" action — there is no API path for casual PII lookup.

### 3.2 Investigation Scoping as a Structural Constraint

Re-ID and watchlist-scoped face recognition are not merely policy-restricted to investigation context — the `MilvusService.search_person_reid_in_scope()` and `search_faces_in_investigation_scope()` methods *require* a non-empty `camera_ids` list and time window as function arguments. There is no method signature that permits a global archive search. This is enforced in the type system, not just in application logic.

### 3.3 Hash-Chained Audit Log

Every audit record carries `event_hash = SHA256(action|actor|subject|details|timestamp|prev_hash)`. Tampering with any historical record breaks the chain at that point and every subsequent record — verified in `audit.tamper.spec.ts` with a 100% detection rate across 1,000 randomised single-field tamper trials (KPI-15, gating). Daily Merkle roots provide external attestability.

### 3.4 Calibration as a Release Gate

The `bias_evaluation.py` module computes ECE, demographic parity difference, and FMR-achievable operating points. A model cannot ship to the PCR console unless ECE ≤ 0.05 and demographic parity difference ≤ 0.10 across the 18 required sex×age×skin-tone strata (minimum 200 subjects per stratum). These are CI pipeline gates, not advisory metrics.

### 3.5 Revocation Propagation Architecture

The ≤60-second propagation guarantee is met through three independent mechanisms: (1) a Redis consent-state cache with 90-second TTL forces re-validation; (2) the Bridge Agent polls every 15 seconds; (3) live-pull tunnels close immediately via a synchronous event handler rather than waiting for the poll cycle. Statistical verification across 100 simulated revocations confirms worst-case completion under 60 seconds.

---

## 4. Data Flow: Event-Clip Path (Default Mode)

1. Edge YOLOv8-nano + MOG2 detect motion/person/vehicle/audio anomaly
2. Privacy-zone pixel mask applied — **before** any frame leaves the device
3. 5–10s pre-roll + event window + 10–15s post-roll assembled into ≤60s clip
4. H.265 encoding targets ≤200KB@720p / ≤800KB@1080p
5. Bandwidth-aware chunked HTTPS upload with resume, priority-tagged
6. Server-side: hash verification → Kafka → fan-out to ANPR/FR/Re-ID/Audio/Behavior
7. Results land in PostgreSQL (metadata) + Milvus (embeddings)
8. Alerts generated per the bounded taxonomy (§C.7 of the challenge doc) — human always clicks

## 5. Data Flow: Live-Pull Path (Exception Mode)

1. IO initiates request citing case reference — tier determined by urgency (T1: pre-authorised ≤15min; T2: supervisor sign-off; T3: Senior SP sign-off + flagged audit)
2. If citizen toggled "ask each time," push notification sent; 30s timeout, deny-by-default
3. WebRTC tunnel opens via TURN relay — citizen IP never reaches PCR
4. Server-side watermark embeds session-ID into every frame for chain of custody
5. Citizen receives non-dismissible notification naming camera, duration, case reference
6. Auto-terminates at tier max-duration or explicit end

---

## 6. Technology Stack Summary

| Layer | Technology |
|---|---|
| Citizen app | Flutter, Riverpod, GoRouter, flutter_webrtc |
| Backend services | NestJS, TypeScript, TypeORM, PostgreSQL+PostGIS |
| AI services | Python, FastAPI, ONNX Runtime, InsightFace, PaddleOCR, YAMNet, OSNet |
| Bridge Agent | Python, OpenCV, aiortc, ONNX Runtime |
| PCR Console | Next.js, React, MapLibre GL, Redux Toolkit, React Query |
| Event bus | Kafka (24 partitions for analytics, 1 for audit ordering) |
| Vector search | Milvus (HNSW, COSINE) |
| Object storage | MinIO / S3 with Object Lock (WORM) for audit |
| KMS | HashiCorp Vault |
| Orchestration | Kubernetes (EKS, Mumbai region) |
| Observability | Prometheus, Grafana, Loki, OpenTelemetry |

---

## 7. Compliance Posture

Full section-by-section mapping in `docs/legal-mapping.md`. Summary: DPDP Act 2023 consent/purpose-limitation/minimisation requirements are enforced at the API layer (not policy documents); BSA 2023 §63 evidentiary certificates auto-generate on clip export; Aadhaar use is opt-in with auth-only flows; children are structurally excluded from face recognition output (not merely flagged).

---

## 8. What Would Break This System

Three single points of failure for the *governance* model (not the technology):

1. **A Senior SP role compromised or coerced** — mitigated by the two-officer rule on watchlist mutations and bulk exports, but a single corrupt Senior SP with a complicit second officer remains a residual risk. Recommendation: rotate the second-officer pool randomly rather than allowing self-selection.
2. **Bridge Agent supply-chain compromise** — signed releases and per-agent certificates limit blast radius, but a compromised build pipeline could ship malicious agents broadly. Recommendation: reproducible builds + SBOM verification before any agent update is accepted.
3. **Drift in deployment configuration across jurisdictions** — the architecture is sound; a jurisdiction that disables the prohibited-category check via a forked deployment would defeat it entirely. Recommendation: the prohibited-category enforcement should ideally live in a separately-attested, non-forkable compliance microservice rather than inline in `WatchlistService`.

This document, the legal mapping, and the security architecture together total the required ≤30-page architecture deliverable when formatted for print; the full source tree is provided alongside for technical evaluation.
