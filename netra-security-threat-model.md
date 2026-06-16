# Project NETRA — Security Architecture & Threat Model

## Zero Trust Architecture

NETRA applies zero trust at every boundary:
- No implicit trust between services (all mutual TLS)
- Every request authenticated and authorised, even internal
- Minimal privilege at every role
- All actions audited

---

## Cryptography Implementation

### mTLS (Bridge Agent ↔ Server)

```
┌─────────────────┐  mTLS 1.3   ┌──────────────────┐
│  Bridge Agent   │◄──────────►│  Ingestion API    │
│  (citizen edge) │             │  (server cluster) │
│  Per-agent cert │             │  CA-signed cert   │
└─────────────────┘             └──────────────────┘

Certificate lifecycle:
- Issued at camera registration (signed by NETRA internal CA)
- Rotated quarterly (automated via cert-manager)
- Revoked within 5 minutes of citizen revocation
- CRL/OCSP checked on every connection establishment
```

### Storage Encryption

```
Event Clips (MinIO):
  AES-256-XTS full-disk encryption at storage layer
  + Per-camera content key (DEK) wrapped by KMS
  Key hierarchy:
    Master Key (HSM) → KEK per camera → DEK per clip
  Cryptographic erasure on revocation: destroy DEK

Watchlist Templates:
  Stored in separate KMS scope (higher access control)
  Requires named-officer credentials to unwrap
  Access logged to separate audit trail

Citizen PII (name, phone):
  AES-256-GCM at field level before DB storage
  KEK managed in Vault; rotated annually
```

### Live Pull Tunnel Security

```
WebRTC DTLS-SRTP with ephemeral session keys:
- DTLS handshake per session
- SRTP for media encryption
- Session key destroyed at tunnel close
- Citizen IP never exposed to PCR operator
  (TURN relay terminates both ends)
- Server-side watermark (session-ID) embedded in frames
```

---

## Vault Configuration (KMS)

```hcl
# vault/policy/netra-backend.hcl
path "netra-kms/+/camera-keys/*" {
  capabilities = ["create", "read", "update", "delete"]
}

path "netra-kms/+/camera-encrypt/*" {
  capabilities = ["update"]  # encrypt only, not read key material
}

path "netra-kms/+/camera-decrypt/*" {
  capabilities = ["update"]  # decrypt only
}

# Watchlist: separate policy, named-officer only
path "netra-kms/+/watchlist-keys/*" {
  capabilities = ["read"]
}
```

---

## Audit Log Hash Chain

Every audit record is hash-chained to prevent tampering:

```
AuditRecord_N = {
  ...fields...,
  event_hash: SHA256(
    action || actor_id || subject_id || details || occurred_at || prev_hash
  ),
  prev_hash: AuditRecord_{N-1}.event_hash
}

Daily Merkle root:
  All records for date D → Merkle tree → root published
  External attestation: root signed and published to
  public transparency endpoint (quarterly aggregate)

Tamper detection:
  Any modification to historical record breaks the chain
  Red-team test: 100% detection required (KPI-15)
```

---

## RBAC Implementation

```typescript
// Role hierarchy (enforced by RolesGuard)
SYSTEM_ADMIN > SENIOR_SP > SHIFT_SUPERVISOR > IO > WATCHER

// Special roles:
// AUDITOR: read-only to all logs; no operational access
// CITIZEN: only own cameras and data

// Sensitive operations requiring TWO officers:
const TWO_OFFICER_OPERATIONS = [
  'WATCHLIST_ADD',
  'WATCHLIST_REMOVE',
  'BULK_EXPORT',
  'CITIZEN_IDENTITY_DISCLOSURE',
];

// Step-up auth required for:
const STEP_UP_REQUIRED = [
  'SENIOR_SP' role operations,
  'BULK_EXPORT',
  'WATCHLIST_ADD',
];
```

---

## Threat Model (T1–T12)

| ID | Threat | Mitigation |
|----|--------|-----------|
| T1 | Bridge Agent compromise | Per-agent certs, signed updates, anomaly detection on uplink |
| T2 | Police over-reach | Investigation scope at API layer, prohibited-category enforcement, two-officer rule, AUDITOR role |
| T3 | Bystander harm | FOV validation, privacy zones, detection-only by default, bystander erasure workflow |
| T4 | Stalking via platform | Re-ID investigation-bound, audit anomaly detection, no global face search |
| T5 | Watchlist poisoning | Named approver, periodic review, prohibited-category API enforcement, public transparency |
| T6 | Model bias | §H bias audit, gating KPIs, top-N output, threshold management |
| T7 | Spoofed feeds | Per-agent attestation, monotonic timestamps, video provenance signing |
| T8 | Live-tunnel hijack | mTLS + DTLS-SRTP, per-session keys, citizen indicator, server watermark |
| T9 | Vendor-cloud failure | Adapter pattern with circuit breaker, graceful degradation |
| T10 | Mission creep | Purpose-limitation at API, prohibited categories in code, public dashboard |
| T11 | Court challenge | Legal mapping, calibrated/bias-audited models, opt-in only, bystander protection |
| T12 | Wrongful arrest from FR | Top-N only, mandatory attestation, FR is lead not ID, calibration, threshold |

---

## Security Headers (NestJS Middleware)

```typescript
// Applied to all API responses
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],  // Tailwind needs this
      imgSrc: ["'self'", 'data:', 'blob:'],
      connectSrc: ["'self'", 'wss:', 'https:'],
      frameSrc: ["'none'"],
      objectSrc: ["'none'"],
    },
  },
  hsts: { maxAge: 31536000, includeSubDomains: true, preload: true },
  referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
  xContentTypeOptions: true,
  xFrameOptions: { action: 'deny' },
}));
```

---

## Key Rotation Schedule

| Key Type | Rotation Period | Method |
|----------|----------------|--------|
| Bridge Agent mTLS certs | 90 days | cert-manager automated |
| JWT signing key | 30 days | Vault key rotation + cache invalidation |
| Per-camera content DEK | On revocation | Destroy immediately |
| Watchlist KMS keys | 180 days | Manual + audit logged |
| Database encryption KEK | 365 days | Vault + online re-encrypt |
| TURN credentials | 7 days | Automated rotation |

---

## Penetration Test Checklist (Red-team)

- [ ] Attempt FR search without investigation_id → must return 400
- [ ] Attempt Re-ID against global archive → no API path, must fail
- [ ] Add watchlist entry with "journalist" in description → must return 403
- [ ] Add watchlist entry without Senior SP role → must return 403
- [ ] Attempt watchlist removal without co-signer → must return 403
- [ ] Modify historical audit log → hash chain must detect immediately
- [ ] Bulk export without second officer → must be blocked
- [ ] Access citizen PII from PCR role → must return de-identified view only
- [ ] Attempt live pull without case reference → must return 400
- [ ] Override revocation state → Bridge Agent must stop within 60s regardless
- [ ] IDOR between citizen cameras → must return 403
- [ ] JWT algorithm confusion (RS256 → HS256) → must reject
- [ ] SQL injection in search filters → all parameterised, must be safe
- [ ] Rate limit bypass on OTP endpoint → must enforce 3/min
