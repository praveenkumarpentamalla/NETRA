-- =============================================================
-- PROJECT NETRA — PostgreSQL Schema
-- Migration V001: Initial Schema
-- Requires: PostgreSQL 15+, PostGIS 3+, pgcrypto
-- =============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- =============================================================
-- ENUMS
-- =============================================================

CREATE TYPE user_role AS ENUM (
  'CITIZEN', 'WATCHER', 'IO', 'SHIFT_SUPERVISOR',
  'SENIOR_SP', 'AUDITOR', 'SYSTEM_ADMIN'
);

CREATE TYPE camera_status AS ENUM (
  'PENDING', 'ONLINE', 'OFFLINE', 'PAUSED', 'REVOKED', 'ERROR'
);

CREATE TYPE camera_class AS ENUM (
  'ONVIF', 'RTSP', 'VENDOR_CLOUD', 'DVR_NVR',
  'PHONE_CAMERA', 'DASHCAM', 'USB_WEBCAM'
);

CREATE TYPE live_pull_auth AS ENUM (
  'ALWAYS_DENY', 'ASK_EACH_TIME', 'AUTO_ALLOW_EMERGENCY'
);

CREATE TYPE event_type AS ENUM (
  'MOTION', 'PERSON_DETECTED', 'VEHICLE_DETECTED', 'AUDIO_ANOMALY',
  'LOITERING', 'CROWD_ANOMALY', 'FIGHT_DETECTED', 'ABANDONED_OBJECT',
  'AWAY_MODE_MOTION', 'PRIVACY_ZONE_VIOLATION', 'CAMERA_TAMPER'
);

CREATE TYPE alert_type AS ENUM (
  'AWAY_MODE_NIGHT_MOTION', 'VEHICLE_OF_INTEREST',
  'PERSON_OF_INTEREST', 'LOITERING', 'AUDIO_ANOMALY',
  'CROWD_ANOMALY', 'CAMERA_OFFLINE', 'CAMERA_TAMPER',
  'PRIVACY_ZONE_VIOLATION'
);

CREATE TYPE alert_status AS ENUM (
  'NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'DISMISSED'
);

CREATE TYPE investigation_type AS ENUM (
  'FIR', 'PCR_CALL', 'MISSING_PERSON', 'BOLO'
);

CREATE TYPE investigation_status AS ENUM (
  'OPEN', 'CLOSED', 'SUSPENDED', 'ARCHIVED'
);

CREATE TYPE watchlist_category AS ENUM (
  'WANTED', 'MISSING', 'BOLO_SUSPECT'
);

CREATE TYPE watchlist_status AS ENUM (
  'ACTIVE', 'EXPIRED', 'REMOVED'
);

CREATE TYPE live_pull_tier AS ENUM ('TIER_1', 'TIER_2', 'TIER_3');

CREATE TYPE live_pull_status AS ENUM (
  'REQUESTED', 'PENDING_APPROVAL', 'PENDING_CITIZEN',
  'ACTIVE', 'COMPLETED', 'DENIED', 'TIMEOUT'
);

CREATE TYPE consent_mode AS ENUM ('EVENT_ONLY', 'LIVE_PULL_ENABLED');

CREATE TYPE audit_action AS ENUM (
  'CAMERA_REGISTER', 'CAMERA_REVOKE', 'CAMERA_PAUSE', 'CAMERA_RESUME',
  'CONSENT_GRANT', 'CONSENT_REVOKE', 'CONSENT_UPDATE',
  'LIVE_PULL_REQUEST', 'LIVE_PULL_APPROVE', 'LIVE_PULL_DENY',
  'LIVE_PULL_START', 'LIVE_PULL_END',
  'INVESTIGATION_CREATE', 'INVESTIGATION_CLOSE',
  'SEARCH_ATTRIBUTE', 'SEARCH_PLATE', 'SEARCH_FACE', 'SEARCH_REID',
  'FR_MATCH_ATTESTED', 'FR_MATCH_DISMISSED',
  'WATCHLIST_ADD', 'WATCHLIST_REMOVE', 'WATCHLIST_REVIEW',
  'CLIP_VIEW', 'CLIP_EXPORT', 'CLIP_DELETE',
  'CITIZEN_IDENTITY_DISCLOSURE',
  'BYSTANDER_ERASURE_REQUEST', 'BYSTANDER_ERASURE_COMPLETE',
  'BULK_EXPORT', 'SYSTEM_CONFIG_CHANGE'
);

-- =============================================================
-- USERS & ROLES
-- =============================================================

CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  username          VARCHAR(100) UNIQUE NOT NULL,
  email             VARCHAR(255) UNIQUE,
  phone             VARCHAR(20) UNIQUE,
  role              user_role NOT NULL DEFAULT 'CITIZEN',
  department        VARCHAR(200),
  badge_number      VARCHAR(50),
  is_active         BOOLEAN NOT NULL DEFAULT true,
  mfa_enabled       BOOLEAN NOT NULL DEFAULT false,
  mfa_secret        TEXT,
  last_login_at     TIMESTAMPTZ,
  password_hash     TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ
);

CREATE TABLE user_sessions (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id           UUID NOT NULL REFERENCES users(id),
  device_fingerprint TEXT,
  ip_address        INET,
  user_agent        TEXT,
  refresh_token_hash TEXT NOT NULL,
  expires_at        TIMESTAMPTZ NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked_at        TIMESTAMPTZ
);

-- =============================================================
-- CITIZENS (Pseudonymised layer)
-- =============================================================

CREATE TABLE citizens (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id           UUID NOT NULL REFERENCES users(id) UNIQUE,
  citizen_id        VARCHAR(20) UNIQUE NOT NULL,
  encrypted_phone   BYTEA NOT NULL,
  encrypted_name    BYTEA,
  verified_at       TIMESTAMPTZ,
  verification_method VARCHAR(50) DEFAULT 'MOBILE_OTP',
  aadhaar_linked    BOOLEAN DEFAULT false,
  participation_score INTEGER DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- CAMERAS
-- =============================================================

CREATE TABLE cameras (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  camera_id         VARCHAR(30) UNIQUE NOT NULL,
  citizen_id        UUID NOT NULL REFERENCES citizens(id),
  label             VARCHAR(100),
  camera_class      camera_class NOT NULL,
  status            camera_status NOT NULL DEFAULT 'PENDING',
  geo_point         GEOMETRY(POINT, 4326),
  geo_precision_m   INTEGER DEFAULT 25,
  fov_polygon       GEOMETRY(POLYGON, 4326),
  fov_image_polygon JSONB,
  address_area      VARCHAR(200),
  stream_config     JSONB NOT NULL DEFAULT '{}',
  consent_mode      consent_mode NOT NULL DEFAULT 'EVENT_ONLY',
  live_pull_auth    live_pull_auth NOT NULL DEFAULT 'ASK_EACH_TIME',
  away_mode_enabled BOOLEAN DEFAULT false,
  away_schedule     JSONB,
  alert_subscriptions JSONB DEFAULT '[]',
  kms_key_id        VARCHAR(200) NOT NULL,
  last_seen_at      TIMESTAMPTZ,
  last_event_at     TIMESTAMPTZ,
  online_since      TIMESTAMPTZ,
  agent_version     VARCHAR(50),
  revoked_at        TIMESTAMPTZ,
  revoked_reason    VARCHAR(500),
  deletion_scheduled_at TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE privacy_zones (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  camera_id         UUID NOT NULL REFERENCES cameras(id),
  label             VARCHAR(100),
  pixel_polygon     JSONB NOT NULL,
  is_active         BOOLEAN DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- EVENTS & CLIPS
-- =============================================================

CREATE TABLE events (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  camera_id         UUID NOT NULL REFERENCES cameras(id),
  event_type        event_type NOT NULL,
  occurred_at       TIMESTAMPTZ NOT NULL,
  clip_path         VARCHAR(500),
  clip_hash         VARCHAR(128),
  clip_signature    TEXT,
  clip_size_bytes   BIGINT,
  clip_duration_ms  INTEGER,
  clip_resolution   VARCHAR(20),
  edge_detections   JSONB DEFAULT '[]',
  trigger_confidence FLOAT,
  server_analytics  JSONB DEFAULT '{}',
  geo_point         GEOMETRY(POINT, 4326),
  upload_ip_hash    VARCHAR(128),
  received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at      TIMESTAMPTZ,
  legal_hold        BOOLEAN DEFAULT false,
  investigation_ids UUID[] DEFAULT '{}',
  retention_tier    VARCHAR(10) DEFAULT 'HOT',
  expires_at        TIMESTAMPTZ,
  deleted_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- ALERTS
-- =============================================================

CREATE TABLE alerts (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  camera_id         UUID REFERENCES cameras(id),
  event_id          UUID REFERENCES events(id),
  alert_type        alert_type NOT NULL,
  status            alert_status NOT NULL DEFAULT 'NEW',
  title             VARCHAR(200) NOT NULL,
  description       TEXT,
  confidence        FLOAT,
  notify_citizen    BOOLEAN DEFAULT false,
  notify_pcr        BOOLEAN DEFAULT false,
  watchlist_entry_id UUID,
  match_candidates  JSONB,
  geo_point         GEOMETRY(POINT, 4326),
  acknowledged_by   UUID REFERENCES users(id),
  acknowledged_at   TIMESTAMPTZ,
  attested_by       UUID REFERENCES users(id),
  attested_at       TIMESTAMPTZ,
  attestation_note  TEXT,
  dismissed_by      UUID REFERENCES users(id),
  dismissed_at      TIMESTAMPTZ,
  dismiss_reason    TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- INVESTIGATIONS
-- =============================================================

CREATE TABLE investigations (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  case_reference    VARCHAR(100) UNIQUE NOT NULL,
  investigation_type investigation_type NOT NULL,
  title             VARCHAR(300) NOT NULL,
  description       TEXT,
  status            investigation_status NOT NULL DEFAULT 'OPEN',
  geo_fence         GEOMETRY(POLYGON, 4326),
  time_window_start TIMESTAMPTZ NOT NULL,
  time_window_end   TIMESTAMPTZ,
  lead_officer_id   UUID REFERENCES users(id),
  supervisor_id     UUID REFERENCES users(id),
  cctns_fir_id      VARCHAR(100),
  ncmc_ref          VARCHAR(100),
  dial112_call_id   VARCHAR(100),
  opened_by         UUID REFERENCES users(id),
  opened_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closed_by         UUID REFERENCES users(id),
  closed_at         TIMESTAMPTZ,
  legal_hold_until  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE investigation_cameras (
  investigation_id  UUID NOT NULL REFERENCES investigations(id),
  camera_id         UUID NOT NULL REFERENCES cameras(id),
  added_by          UUID REFERENCES users(id),
  added_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (investigation_id, camera_id)
);

CREATE TABLE investigation_events (
  investigation_id  UUID NOT NULL REFERENCES investigations(id),
  event_id          UUID NOT NULL REFERENCES events(id),
  relevance_note    TEXT,
  added_by          UUID REFERENCES users(id),
  added_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (investigation_id, event_id)
);

-- =============================================================
-- WATCHLISTS
-- =============================================================

CREATE TABLE watchlist_entries (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  category          watchlist_category NOT NULL,
  reference         VARCHAR(200) NOT NULL,
  description       VARCHAR(500),
  biometric_template_id VARCHAR(200),
  biometric_hash    VARCHAR(128),
  approving_officer_id UUID NOT NULL REFERENCES users(id),
  approved_at       TIMESTAMPTZ NOT NULL,
  reviewed_by       UUID REFERENCES users(id),
  reviewed_at       TIMESTAMPTZ,
  expiry_at         TIMESTAMPTZ NOT NULL,
  status            watchlist_status NOT NULL DEFAULT 'ACTIVE',
  removal_reason    TEXT,
  removed_by        UUID REFERENCES users(id),
  removed_at        TIMESTAMPTZ,
  hash_chain_anchor TEXT NOT NULL,
  prev_hash         TEXT,
  prohibited_category_check BOOLEAN NOT NULL DEFAULT false,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT no_prohibited_categories CHECK (prohibited_category_check = false)
);

CREATE TABLE anpr_bolo_list (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  plate_string      VARCHAR(20) NOT NULL,
  plate_fuzzy_variants JSONB DEFAULT '[]',
  reference         VARCHAR(200) NOT NULL,
  approving_officer_id UUID NOT NULL REFERENCES users(id),
  approved_at       TIMESTAMPTZ NOT NULL,
  expiry_at         TIMESTAMPTZ NOT NULL,
  status            watchlist_status NOT NULL DEFAULT 'ACTIVE',
  removal_reason    TEXT,
  removed_at        TIMESTAMPTZ,
  hash_chain_anchor TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- FACE DETECTIONS
-- =============================================================

CREATE TABLE face_detections (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id          UUID NOT NULL REFERENCES events(id),
  camera_id         UUID NOT NULL REFERENCES cameras(id),
  occurred_at       TIMESTAMPTZ NOT NULL,
  bbox_x            INTEGER,
  bbox_y            INTEGER,
  bbox_w            INTEGER,
  bbox_h            INTEGER,
  quality_score     FLOAT,
  is_child_estimate BOOLEAN DEFAULT false,
  face_attribute_age_min INTEGER,
  face_attribute_age_max INTEGER,
  milvus_id         BIGINT,
  embedding_model   VARCHAR(100) DEFAULT 'ArcFace-R100',
  embedding_version VARCHAR(50),
  recognition_run   BOOLEAN DEFAULT false,
  watchlist_match   BOOLEAN DEFAULT false,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- LIVE PULL SESSIONS
-- =============================================================

CREATE TABLE live_pull_sessions (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  camera_id         UUID NOT NULL REFERENCES cameras(id),
  investigation_id  UUID REFERENCES investigations(id),
  requested_by      UUID NOT NULL REFERENCES users(id),
  case_reference    VARCHAR(100) NOT NULL,
  tier              live_pull_tier NOT NULL,
  status            live_pull_status NOT NULL DEFAULT 'REQUESTED',
  approved_by       UUID REFERENCES users(id),
  approved_at       TIMESTAMPTZ,
  denied_by         UUID REFERENCES users(id),
  denied_at         TIMESTAMPTZ,
  deny_reason       TEXT,
  citizen_approved_at TIMESTAMPTZ,
  citizen_denied_at TIMESTAMPTZ,
  session_key_id    VARCHAR(200),
  webrtc_session_id VARCHAR(200),
  watermark_id      VARCHAR(100),
  started_at        TIMESTAMPTZ,
  ended_at          TIMESTAMPTZ,
  duration_seconds  INTEGER,
  max_duration_seconds INTEGER DEFAULT 900,
  recording_path    VARCHAR(500),
  request_timeout_at TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- NOTIFICATIONS
-- =============================================================

CREATE TABLE notifications (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  recipient_id      UUID NOT NULL REFERENCES users(id),
  recipient_type    VARCHAR(20) NOT NULL,
  notification_type VARCHAR(100) NOT NULL,
  title             VARCHAR(200) NOT NULL,
  body              TEXT,
  data              JSONB DEFAULT '{}',
  is_transparency   BOOLEAN DEFAULT false,
  camera_id         UUID REFERENCES cameras(id),
  case_reference    VARCHAR(100),
  access_duration_s INTEGER,
  is_read           BOOLEAN DEFAULT false,
  is_dismissed      BOOLEAN DEFAULT false,
  sent_at           TIMESTAMPTZ,
  read_at           TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- AUDIT LOGS (append-only, hash-chained)
-- =============================================================

CREATE TABLE audit_logs (
  id                BIGSERIAL PRIMARY KEY,
  log_uuid          UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
  action            audit_action NOT NULL,
  actor_id          UUID REFERENCES users(id),
  actor_role        user_role,
  subject_type      VARCHAR(50),
  subject_id        UUID,
  investigation_id  UUID REFERENCES investigations(id),
  case_reference    VARCHAR(100),
  details           JSONB NOT NULL DEFAULT '{}',
  ip_address_hash   VARCHAR(128),
  event_hash        VARCHAR(128) NOT NULL,
  prev_hash         TEXT NOT NULL,
  merkle_root       VARCHAR(128),
  occurred_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- INTEGRATIONS
-- =============================================================

CREATE TABLE integration_configs (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  system_name       VARCHAR(100) NOT NULL UNIQUE,
  is_enabled        BOOLEAN DEFAULT false,
  endpoint_url      VARCHAR(500),
  auth_config       JSONB,
  circuit_breaker_state VARCHAR(20) DEFAULT 'CLOSED',
  failure_count     INTEGER DEFAULT 0,
  last_success_at   TIMESTAMPTZ,
  last_failure_at   TIMESTAMPTZ,
  last_failure_reason TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE integration_audit (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  system_name       VARCHAR(100) NOT NULL,
  action            VARCHAR(100) NOT NULL,
  actor_id          UUID REFERENCES users(id),
  query_params      JSONB,
  response_status   INTEGER,
  purpose           TEXT NOT NULL,
  case_reference    VARCHAR(100),
  occurred_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE bystander_erasure_requests (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  requestor_info    JSONB NOT NULL,
  description       TEXT NOT NULL,
  geo_area          GEOMETRY(POLYGON, 4326),
  time_window_start TIMESTAMPTZ NOT NULL,
  time_window_end   TIMESTAMPTZ NOT NULL,
  status            VARCHAR(50) DEFAULT 'PENDING',
  assigned_to       UUID REFERENCES users(id),
  completed_at      TIMESTAMPTZ,
  completion_note   TEXT,
  affected_clips    INTEGER DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================
-- INDEXES
-- =============================================================

CREATE INDEX idx_cameras_citizen_id ON cameras(citizen_id);
CREATE INDEX idx_cameras_status ON cameras(status);
CREATE INDEX idx_cameras_geo ON cameras USING GIST(geo_point);
CREATE INDEX idx_cameras_fov ON cameras USING GIST(fov_polygon);

CREATE INDEX idx_events_camera_id ON events(camera_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_occurred_at ON events(occurred_at DESC);
CREATE INDEX idx_events_geo ON events USING GIST(geo_point);
CREATE INDEX idx_events_legal_hold ON events(legal_hold) WHERE legal_hold = true;

CREATE INDEX idx_alerts_camera_id ON alerts(camera_id);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_type ON alerts(alert_type);
CREATE INDEX idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX idx_alerts_geo ON alerts USING GIST(geo_point);

CREATE INDEX idx_investigations_status ON investigations(status);
CREATE INDEX idx_investigations_lead_officer ON investigations(lead_officer_id);
CREATE INDEX idx_investigations_geo ON investigations USING GIST(geo_fence);
CREATE INDEX idx_investigations_time ON investigations(time_window_start, time_window_end);

CREATE INDEX idx_face_detections_event_id ON face_detections(event_id);
CREATE INDEX idx_face_detections_camera_id ON face_detections(camera_id);
CREATE INDEX idx_face_detections_occurred_at ON face_detections(occurred_at DESC);

CREATE INDEX idx_watchlist_status ON watchlist_entries(status);
CREATE INDEX idx_watchlist_category ON watchlist_entries(category);
CREATE INDEX idx_watchlist_expiry ON watchlist_entries(expiry_at);
CREATE INDEX idx_anpr_bolo_plate ON anpr_bolo_list(plate_string);

CREATE INDEX idx_live_pull_camera ON live_pull_sessions(camera_id);
CREATE INDEX idx_live_pull_status ON live_pull_sessions(status);
CREATE INDEX idx_live_pull_started_at ON live_pull_sessions(started_at DESC);

CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_occurred_at ON audit_logs(occurred_at DESC);
CREATE INDEX idx_audit_investigation ON audit_logs(investigation_id);

CREATE INDEX idx_notifications_recipient ON notifications(recipient_id);
CREATE INDEX idx_notifications_unread ON notifications(recipient_id, is_read) WHERE is_read = false;
CREATE INDEX idx_users_role ON users(role);

-- =============================================================
-- FUNCTIONS
-- =============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cameras_updated_at BEFORE UPDATE ON cameras
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_investigations_updated_at BEFORE UPDATE ON investigations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_alerts_updated_at BEFORE UPDATE ON alerts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE FUNCTION generate_citizen_id()
RETURNS VARCHAR(20) AS $$
BEGIN
  RETURN 'CIT' || UPPER(ENCODE(GEN_RANDOM_BYTES(8), 'hex'));
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION generate_camera_id()
RETURNS VARCHAR(30) AS $$
BEGIN
  RETURN 'CAM' || UPPER(ENCODE(GEN_RANDOM_BYTES(10), 'hex'));
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION compute_audit_hash(
  p_action TEXT, p_actor_id TEXT, p_subject_id TEXT,
  p_details TEXT, p_occurred_at TEXT, p_prev_hash TEXT
) RETURNS TEXT AS $$
BEGIN
  RETURN ENCODE(
    DIGEST(
      p_action || '|' || COALESCE(p_actor_id,'') || '|' ||
      COALESCE(p_subject_id,'') || '|' || p_details || '|' ||
      p_occurred_at || '|' || p_prev_hash, 'sha256'
    ), 'hex'
  );
END;
$$ LANGUAGE plpgsql;
