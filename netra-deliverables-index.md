# Project NETRA — Deliverables Index

Maps every file in this repository to the hackathon's required deliverables (§7) and the 20-part request structure.

## Hackathon Deliverables (§7) → Location

| # | Deliverable | Location |
|---|---|---|
| 1 | Working prototype (onboarding, hybrid ingestion, PCR console, FR/ANPR/Re-ID, consent/revocation) | `services/`, `ai/`, `bridge-agent/`, `apps/pcr-console/` |
| 2 | Mock-deployment dataset | `database/seeds/dev_seed.sql` (4 cameras, 3 environments — extend per actual field test) |
| 3 | Citizen mobile app (onboarding, dashboard, transparency, pause/revoke, notifications) | `apps/citizen-mobile/` |
| 4 | Architecture document (≤30 pages) | `docs/architecture.md` |
| 5 | Legal mapping document (≤20 pages) | `docs/legal-mapping.md` |
| 6 | Bias, calibration, fairness report | `ai/calibration/bias_evaluation.py` + `ai/calibration/tests/test_ece.py` |
| 7 | Threat-model and red-team report | `docs/security-architecture.md` (§ Threat Model T1–T12) |
| 8 | Source code with documented OSS licence | This repository; Apache 2.0 (see `README.md`) |

## 20-Part Request → Location

| Part | Topic | Location |
|---|---|---|
| 1 | Project understanding | `docs/architecture.md` §1, conversation response |
| 2 | Complete system flow | `docs/architecture.md` §4–5, diagrams in conversation |
| 3 | Microservice architecture | `services/*/`, diagram in conversation |
| 4 | Database design | `database/migrations/V001__initial_schema.sql` |
| 5 | Redis design | `shared/types/redis-keys.ts` |
| 6 | Kafka design | `shared/types/kafka-topics.ts` |
| 7 | Vector database | `shared/types/milvus-schema.py` |
| 8 | API documentation | `docs/openapi.yaml` |
| 9 | UI/UX design | PCR console mockup (conversation), `apps/pcr-console/src/` |
| 10 | Figma-equivalent design | Interactive widget mockup (conversation) |
| 11 | Frontend (React/Next.js) | `apps/pcr-console/` |
| 12 | Mobile app (Flutter) | `apps/citizen-mobile/` |
| 13 | Backend (NestJS) | `services/auth/`, `services/camera/`, `services/watchlist/` |
| 14 | AI modules | `ai/anpr/`, `ai/face-recognition/`, `ai/person-reid/`, `ai/audio/`, `ai/calibration/` |
| 15 | Bridge Agent | `bridge-agent/` |
| 16 | DevOps | `docker-compose.yml`, `infrastructure/k8s/`, `infrastructure/terraform/`, `infrastructure/ci-cd/` |
| 17 | Security | `docs/security-architecture.md` |
| 18 | Deployment architecture | `infrastructure/terraform/main.tf` |
| 19 | Testing | `services/watchlist/test/watchlist.redteam.spec.ts`, `services/audit/test/audit.tamper.spec.ts`, `services/camera/test/consent.revocation.spec.ts`, `ai/calibration/tests/test_ece.py` |
| 20 | Source code / structure | Full repository, `README.md` |

## Note on Scope

This is a hackathon-grade reference implementation, not a deployed production system. It establishes the architecture, the governance-as-code patterns (prohibited-category rejection, investigation-scoped Re-ID, hash-chained audit, two-officer rule), and representative implementations of every layer named in the challenge document. A real deployment requires: live model weights and training pipelines for ANPR/FR/Re-ID (currently scaffolded with mock fallbacks), a completed Figma file (the conversation includes an interactive HTML/SVG mockup of the PCR console as a stand-in), full Flutter screen set (onboarding/FOV/privacy-zone editor screens are stubbed as route targets, with the dashboard screen fully implemented as a representative example), and a populated mock-deployment dataset from actual volunteer cameras per §7.2 of the challenge.
