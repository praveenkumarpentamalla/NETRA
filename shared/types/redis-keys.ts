/**
 * Project NETRA — Redis Key Design
 * All keys follow hierarchical pattern: domain:entity:id:field
 * TTLs enforce data minimisation.
 */

// ──────────────────────────────────────────────────────────────
// SESSION CACHE
// ──────────────────────────────────────────────────────────────

/**
 * User session (JWT refresh token tracking)
 * Key:   session:{userId}:{sessionId}
 * Value: { refreshTokenHash, expiresAt, deviceFingerprint, ipHash }
 * TTL:   7 days (matches refresh token lifetime)
 */
export const SESSION_KEY = (userId: string, sessionId: string) =>
  `session:${userId}:${sessionId}`;

/**
 * MFA intermediate token (between password verify and TOTP)
 * Key:   mfa_token:{token}
 * Value: { userId }
 * TTL:   5 minutes
 */
export const MFA_TOKEN_KEY = (token: string) => `mfa_token:${token}`;
export const MFA_TOKEN_TTL = 300; // 5 minutes

/**
 * OTP (one-time password for citizen login)
 * Key:   otp:{normalizedPhone}
 * Value: { code, attempts, createdAt }
 * TTL:   10 minutes; max 3 attempts
 */
export const OTP_KEY = (phone: string) => `otp:${phone}`;
export const OTP_TTL = 600;

// ──────────────────────────────────────────────────────────────
// CONSENT STATE CACHE
// ──────────────────────────────────────────────────────────────

/**
 * Camera consent state (critical — revocation must propagate ≤60s)
 * Key:   consent:{cameraId}
 * Value: { status, consentMode, livePullAuth, awayMode, updatedAt }
 * TTL:   90 seconds (force re-read from DB; ensures ≤60s propagation window)
 */
export const CONSENT_KEY = (cameraId: string) => `consent:${cameraId}`;
export const CONSENT_TTL = 90;

/**
 * Privacy zones for camera (pushed to Bridge Agent)
 * Key:   privacy_zones:{cameraId}
 * Value: JSON array of polygon objects
 * TTL:   90 seconds (same propagation guarantee)
 */
export const PRIVACY_ZONES_KEY = (cameraId: string) => `privacy_zones:${cameraId}`;
export const PRIVACY_ZONES_TTL = 90;

// ──────────────────────────────────────────────────────────────
// CAMERA STATE CACHE
// ──────────────────────────────────────────────────────────────

/**
 * Camera online status + last heartbeat
 * Key:   camera:state:{cameraId}
 * Value: { status, lastSeenAt, agentVersion, onlineSince }
 * TTL:   5 minutes (heartbeat every 60s; 5 min = 5 missed beats = offline)
 */
export const CAMERA_STATE_KEY = (cameraId: string) => `camera:state:${cameraId}`;
export const CAMERA_STATE_TTL = 300;

/**
 * Cameras in geo bounds (map query cache)
 * Key:   cameras:geo:{boundsHash}
 * Value: JSON array of Camera objects (PCR-safe view)
 * TTL:   30 seconds (balance freshness vs query cost)
 */
export const CAMERAS_GEO_KEY = (boundsHash: string) => `cameras:geo:${boundsHash}`;
export const CAMERAS_GEO_TTL = 30;

// ──────────────────────────────────────────────────────────────
// LIVE PULL SESSION CACHE
// ──────────────────────────────────────────────────────────────

/**
 * Active live pull sessions
 * Key:   live_pull:session:{sessionId}
 * Value: { cameraId, tier, status, approvedAt, watermarkId, expiresAt }
 * TTL:   max session duration + 60s buffer (e.g. 960s for Tier-1)
 */
export const LIVE_PULL_SESSION_KEY = (sessionId: string) =>
  `live_pull:session:${sessionId}`;
export const LIVE_PULL_TTL = 960;

/**
 * Live pull command queue (per camera — Bridge Agent polls)
 * Key:   live_pull:cmd:{cameraId}
 * Type:  Redis List (LPUSH / BRPOP pattern)
 * TTL:   60 seconds per item
 */
export const LIVE_PULL_CMD_KEY = (cameraId: string) => `live_pull:cmd:${cameraId}`;

/**
 * Citizen approval pending (ASK_EACH_TIME flow)
 * Key:   citizen_approval:{sessionId}
 * Value: { status: 'PENDING' | 'APPROVED' | 'DENIED' }
 * TTL:   35 seconds (30s timeout + 5s buffer)
 */
export const CITIZEN_APPROVAL_KEY = (sessionId: string) =>
  `citizen_approval:${sessionId}`;
export const CITIZEN_APPROVAL_TTL = 35;

// ──────────────────────────────────────────────────────────────
// NOTIFICATION QUEUES
// ──────────────────────────────────────────────────────────────

/**
 * Unread notification count (citizen dashboard badge)
 * Key:   notif:unread:{userId}
 * Value: integer count
 * TTL:   24 hours
 */
export const NOTIF_UNREAD_KEY = (userId: string) => `notif:unread:${userId}`;
export const NOTIF_UNREAD_TTL = 86400;

/**
 * Push notification queue (Redis Pub/Sub channel)
 * Channel: notifications:{userId}
 * Used for real-time push via WebSocket
 */
export const NOTIF_CHANNEL = (userId: string) => `notifications:${userId}`;

// ──────────────────────────────────────────────────────────────
// WATCHLIST MATCH CACHE
// ──────────────────────────────────────────────────────────────

/**
 * Active watchlist summary (embedding IDs list for fast Milvus lookup)
 * Key:   watchlist:active_ids:{category}
 * Value: JSON array of { id, biometric_hash, milvus_id }
 * TTL:   5 minutes (watchlist changes are rare)
 */
export const WATCHLIST_ACTIVE_KEY = (category: string) =>
  `watchlist:active_ids:${category}`;
export const WATCHLIST_ACTIVE_TTL = 300;

// ──────────────────────────────────────────────────────────────
// RATE LIMITING
// ──────────────────────────────────────────────────────────────

/**
 * API rate limiter (sliding window)
 * Key:   ratelimit:{identifier}:{windowStart}
 * Value: request count
 * TTL:   window duration (e.g. 60s)
 */
export const RATE_LIMIT_KEY = (id: string, window: number) =>
  `ratelimit:${id}:${window}`;

/**
 * OTP resend rate limit
 * Key:   otp_rate:{phone}
 * Value: count
 * TTL:   60 seconds
 */
export const OTP_RATE_KEY = (phone: string) => `otp_rate:${phone}`;
export const OTP_RATE_TTL = 60;

// ──────────────────────────────────────────────────────────────
// SEARCH RESULT CACHE
// ──────────────────────────────────────────────────────────────

/**
 * Investigation search results (short cache for re-render)
 * Key:   search:{investigationId}:{queryHash}
 * Value: JSON search results
 * TTL:   60 seconds
 */
export const SEARCH_CACHE_KEY = (invId: string, queryHash: string) =>
  `search:${invId}:${queryHash}`;
export const SEARCH_CACHE_TTL = 60;

// ──────────────────────────────────────────────────────────────
// AUDIT LOG HASH CHAIN
// ──────────────────────────────────────────────────────────────

/**
 * Last audit log hash (for chaining — must be atomic)
 * Key:   audit:last_hash
 * Value: SHA-256 hex string
 * TTL:   none (persistent)
 * NOTE:  Must use Redis WATCH + MULTI/EXEC for atomic chain updates
 */
export const AUDIT_LAST_HASH_KEY = 'audit:last_hash';

// ──────────────────────────────────────────────────────────────
// Redis connection config
// ──────────────────────────────────────────────────────────────

export const redisConfig = {
  host: process.env.REDIS_HOST || 'localhost',
  port: parseInt(process.env.REDIS_PORT || '6379'),
  password: process.env.REDIS_PASSWORD,
  tls: process.env.REDIS_TLS === 'true' ? {} : undefined,
  retryStrategy: (times: number) => Math.min(times * 100, 3000),
  maxRetriesPerRequest: 3,
  enableReadyCheck: true,
  lazyConnect: false,
};
