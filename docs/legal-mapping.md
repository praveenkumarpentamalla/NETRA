# Project NETRA — Legal Compliance Mapping
## Section-by-Section Mapping: Technical Component → Indian Law

---

## 1. Constitution of India — Articles 19 & 21 (Puttaswamy 2017, 10 SCC 1)

**Judgment Summary:** K.S. Puttaswamy v. Union of India established privacy as a fundamental right under Article 21. Any state action infringing privacy must satisfy: (a) legality — a law authorising it; (b) legitimate aim; (c) proportionality.

| Technical Component | Constitutional Mapping |
|---|---|
| **Citizen-pull onboarding** — cameras registered only on explicit citizen consent; no discovery scans | Satisfies *legality* — no covert state acquisition of private feeds; citizen exercises free choice under Art. 19(1)(g) |
| **Per-camera, per-mode consent** — event vs live-pull are separately consented | Satisfies *proportionality* — least-intrusive means selected per use case |
| **One-tap revocation ≤ 60s** | Art. 21 right to withdraw consent enforceable in real time; not illusory |
| **Privacy-zone polygon editor** — citizen blacks out neighbour windows, private spaces | Protects third parties' Art. 21 rights; FOV validation prevents camera from becoming a surveillance instrument against non-consenting parties |
| **Purpose limitation hardcoded** — only FIR/PCR/MISSING/BOLO/traffic-incident; no political/tax/immigration | Satisfies *legitimate aim* — bounded by public-safety necessity; mission-creep structurally impossible |
| **FR top-N only + mandatory attestation** | Proportionality — AI is assist, not determination; human decision-maker preserved |
| **Bystander erasure workflow** | Proactive protection of non-participant Art. 21 rights |
| **Public transparency dashboard** | Judicial oversight proxy; enables constitutional challenge if drift detected |

**Risk:** No dedicated surveillance law currently exists in India. NETRA's consent architecture is designed to survive scrutiny under the necessity-and-proportionality test articulated in Puttaswamy's nine-judge bench.

---

## 2. Digital Personal Data Protection Act 2023 (DPDP Act)

### 2.1 Data Fiduciary Obligations (§ 8–11)

| Obligation | NETRA Implementation |
|---|---|
| **Lawful basis** (§ 4) | Consent for citizen-shared feeds; legitimate use of public-safety authority for PCR operations under state law |
| **Purpose limitation** (§ 6) | Hardcoded at API layer — no path for tax/immigration/political use |
| **Data minimisation** (§ 6) | Event clips only (not continuous recording); geo precision floor (±25m); pseudonymous Citizen-ID to PCR |
| **Accuracy** (§ 8(3)) | Calibrated models; ECE ≤ 0.05; FR top-N with uncertainty |
| **Storage limitation** (§ 8(7)) | Tiered retention: Hot 14d, Warm 90d; embeddings 1 yr; 7yr audit logs; legal hold only for active cases |
| **Security** (§ 8(5)) | AES-256-XTS, mTLS 1.3, per-camera KMS keys, Vault, MFA for all PCR roles |
| **Breach notification** (§ 8(6)) | Incident response plan; CERT-In notification ≤ 6 hours; citizen notification ≤ 72 hours |
| **Grievance Officer** | Designated; reachable via citizen app; 30-day response SLA |

### 2.2 Consent Framework (§ 5–7)

| Requirement | NETRA Implementation |
|---|---|
| **Free, informed, specific, unconditional** | No dark patterns; consent options visually equivalent to refusal; structured consent per camera per mode per alert type |
| **Consent notice** | Progressive disclosure at onboarding: camera, FOV, zones, hours, alert types — each explained in plain language |
| **Withdraw consent** | One-tap revoke; immediate effect; no re-registration penalty |
| **Record of consent** | Consent version, timestamp, mode stored in `cameras.consent_mode` + audit log |
| **No bundled consent** | Each camera, each mode (event/live-pull), each alert type is a separate consent decision |

### 2.3 Data Principal Rights (§ 12–13)

| Right | NETRA Implementation |
|---|---|
| **Access** | Transparency feed in citizen app: who accessed, when, for what case |
| **Correction** | Citizen can update geo precision, address area, camera label |
| **Erasure** | Revocation triggers deletion countdown; cryptographic erasure within configured window |
| **Grievance** | In-app + email channel; 30-day resolution SLA |
| **Nominate** | Family member can manage cameras of deceased citizen |

### 2.4 Significant Data Fiduciary (§ 10)

NETRA processes biometric data at scale. If designated as SDF by the Government, additional obligations apply: Data Protection Officer, Data Protection Impact Assessment, data audit. Architecture is designed to comply with anticipated SDF requirements.

---

## 3. Bharatiya Nyaya Sanhita (BNS) 2023

| Section | Relevance | NETRA Mapping |
|---|---|---|
| § 103 (Murder), § 109 (Attempt) | Investigation trigger | FIR linkage mandatory for serious offence investigations |
| § 179 (Kidnapping) | Missing-person alerts | NCMC reference required for MISSING category watchlist entries |
| § 303 (Theft), § 304 (Robbery) | Common investigation type | Purpose-limited to registered FIR |
| § 356 (Criminal Intimidation) | Audio anomaly alert | Server confirms edge audio trigger before PCR alert |

The BNS defines offences that constitute lawful investigation purposes. NETRA's `investigation_type` enum (FIR, PCR_CALL, MISSING_PERSON, BOLO) maps to BNS offence categories.

---

## 4. Bharatiya Nagarik Suraksha Sanhita (BNSS) 2023

| Section | Requirement | NETRA Implementation |
|---|---|---|
| § 94 (Search/Seizure) | Court order or authorised officer for seizure | Live-pull Tier-2/3 requires documented authorisation; all sessions logged |
| § 175 (Production of documents) | Evidence production mechanism | `investigation_events` table provides chain of custody for produced clips |
| § 63 (Statement recording) | Digital evidence procedure | Officer attestation creates a formal record equivalent to a statement |
| § 105 (Evidentiary certificate) | Now BSA § 63 — see below | Auto-generated electronic certificate on export |
| § 530 (Electronic records) | Admissibility of CCTV footage | Chain-of-custody hash + Bridge Agent signature + server watermark |

---

## 5. Bharatiya Sakshya Adhiniyam (BSA) 2023

### § 63 (Electronic Records Admissibility — successor to IT Act § 65B)

Every clip exported for evidentiary use must carry:

```
BSA_CERTIFICATE = {
  "document_type": "Electronic Record Certificate under BSA 2023 § 63",
  "case_reference": "FIR/MH/2026/001234",
  "camera_id": "CAM_XXXX",            // pseudonymous
  "clip_hash_sha256": "a3b4c5...",
  "clip_hash_algorithm": "SHA-256",
  "recording_timestamp_utc": "2026-03-15T18:42:00Z",
  "upload_timestamp_utc": "2026-03-15T18:42:35Z",
  "bridge_agent_signature": "Base64(RSA-PSS signature)",
  "bridge_agent_cert_thumbprint": "SHA-256 of agent cert",
  "server_ingestion_hash": "a4b5c6...",
  "export_timestamp_utc": "2026-03-16T10:00:00Z",
  "certifying_officer_id": "IO-badge-number",
  "certifying_officer_attestation": "I certify this electronic record...",
  "netra_system_version": "1.0.0",
  "merkle_proof": "...",               // proof against daily root
  "certificate_hash": "SHA-256 of above fields"
}
```

Auto-generated on export; Officer named attestation appended before court production.

---

## 6. Information Technology Act 2000 (as amended)

| Section | Requirement | NETRA Implementation |
|---|---|---|
| § 43A | Reasonable security practices for sensitive personal data | AES-256 storage, mTLS, MFA, Vault KMS — exceeds IS/ISO 27001 baseline |
| § 66E | Punishment for violation of privacy (publishing private images) | Privacy-zone masking prevents inadvertent exposure; bystander erasure workflow |
| § 72A | Punishment for disclosure of information in breach of lawful contract | Role-based access; no disclosure of citizen PII to PCR without documented consent |
| Intermediary Guidelines 2021 (Rule 4) | Significant Social Media Intermediary obligations | NETRA is not a social media platform; rule does not apply; however due-diligence approach adopted |

---

## 7. Aadhaar Act 2016 + UIDAI Authentication Regulations

| Requirement | NETRA Implementation |
|---|---|
| **Opt-in only** | Aadhaar-OTP is one option; mobile-OTP sufficient; system functions without Aadhaar |
| **Auth-only, no demographic fetch** | OTP authentication only; no name/address/photo fetched from UIDAI |
| **No storage of Aadhaar number** | Only auth success/failure stored; Aadhaar UID never persisted in NETRA database |
| **Purpose: identity verification only** | Citizen onboarding; Aadhaar auth result not used for any other purpose |
| **UIDAI API compliance** | Aadhaar OTP auth via licensed AUA/KUA; ASA channel per UIDAI circular |
| **Children** | UIDAI prohibits Aadhaar enrollment under 5; under-18 face excluded from recognition; JJ Act 2015 protection applied |

---

## 8. Juvenile Justice (Care and Protection of Children) Act 2015

| Requirement | NETRA Implementation |
|---|---|
| **Identification of children** | Face attribute classifier estimates age; persons assessed as under 18 excluded from recognition output entirely |
| **No publication of identity** | Child detections indexed but recognition matches filtered — no name or watchlist association surfaced |
| **Child-specific handling** | `is_child_estimate = true` → `recognition_run = false` always |
| **Limitation:** Age estimation is probabilistic; system applies conservative exclusion (err toward exclusion) | Error rate < 5% assessed vs Indian youth face dataset |

---

## 9. Indian Telegraph Act 1885

The Telegraph Act regulates interception of communications. Audio captured by citizen cameras may implicate this Act when ambient conversations are recorded.

| Risk | Mitigation |
|---|---|
| Continuous ambient audio capture may constitute unlawful interception | Default: audio capture OFF; requires separate citizen consent distinct from video consent |
| Audio anomaly detection (gunshot, scream) triggers | Edge classifier runs on-device; no raw audio transmitted without event trigger; server receives clip (not continuous stream) |
| Live-pull audio stream | Audio stream in live pull covered by the same live-pull authorisation; logged; citizen notified |

**Position:** NETRA does not engage in "interception" as defined in § 2(b) of the Telegraph Act (targeting specific communications) but captures ambient audio incident to video monitoring. Separate audio consent + event-only transmission + default-off design minimise risk.

---

## 10. Telecom Cybersecurity Rules 2024

| Rule | NETRA Implementation |
|---|---|
| Security requirements for telecom entities | mTLS on all external connections; VAPT of connectivity components |
| Incident reporting | CERT-In integration; 6-hour breach notification |
| Data localisation | All traffic terminates within India (no cross-border transfer of citizen feed data) |

---

## 11. MHA / MeitY CCTV Guidelines

Current MHA advisories on CCTV for crime prevention and MeitY guidance on video surveillance systems:

| Guideline | NETRA Implementation |
|---|---|
| Retention periods | NETRA 14d Hot / 90d Warm aligns with advisory 30–90d default; legal hold for active cases |
| Access logging | Every access audit-logged; officer name, case reference, timestamp |
| Privacy signage | Not applicable to citizen-owned cameras; citizen consent disclosure through app serves equivalent notice function |
| Data security | AES-256, MFA, role-based access — exceeds advisory baseline |

---

## 12. Summary: Compliance Posture

| Requirement | Status |
|---|---|
| Consent architecture (DPDP Act) | ✅ Per-camera, per-mode, revocable |
| Purpose limitation | ✅ Hardcoded; no API path for excluded uses |
| Data minimisation | ✅ Event-only default; geo floor; pseudonymous IDs |
| Security (AES-256, mTLS, MFA) | ✅ Implemented |
| Audit chain | ✅ Hash-chained, Merkle-rooted, 7-year retention |
| FR governance | ✅ Top-N, attestation, watchlist-bound, child exclusion |
| BSA § 63 certificates | ✅ Auto-generated on export |
| Bystander protection | ✅ Privacy zones, FOV validation, erasure workflow |
| Constitutional proportionality | ✅ Citizen-pull, purpose-limited, transparent |
| Aadhaar opt-in only | ✅ Mobile-OTP sufficient; no demographic fetch |
| Child protection | ✅ FR excluded for under-18 estimates |

**Remaining gaps (acknowledged):**
- No dedicated surveillance law in India → relying on Puttaswamy proportionality framework
- Watchlist governance relies on internal policy (Senior SP approval) without external judicial oversight → recommended: magistrate approval for Tier-3 operations
- Audio capture telecom law position requires legal opinion in each deployment jurisdiction
