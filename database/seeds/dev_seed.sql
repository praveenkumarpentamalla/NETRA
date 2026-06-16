-- Project NETRA — Development Seed Data
-- NOT for production. Provides test users, cameras, and investigations.

-- ──────────────────────────────────────────────────────────────
-- Test users (BCrypt hash of "TestPassword123!" for all)
-- ──────────────────────────────────────────────────────────────

INSERT INTO users (id, username, email, phone, role, department, badge_number, is_active, mfa_enabled, password_hash) VALUES
  ('00000000-0000-0000-0000-000000000001', 'io_rajesh',    'rajesh@example.gov.in', '+919876500001', 'IO',               'Pune City Police', 'IO-2024-001', true, true,  '$2b$12$placeholder_hash'),
  ('00000000-0000-0000-0000-000000000002', 'sup_priya',    'priya@example.gov.in',  '+919876500002', 'SHIFT_SUPERVISOR',  'Pune City Police', 'SS-2024-001', true, true,  '$2b$12$placeholder_hash'),
  ('00000000-0000-0000-0000-000000000003', 'sp_krishna',   'krishna@example.gov.in','+919876500003', 'SENIOR_SP',         'Pune City Police', 'SSP-001',     true, true,  '$2b$12$placeholder_hash'),
  ('00000000-0000-0000-0000-000000000004', 'auditor_meena','meena@example.gov.in',  '+919876500004', 'AUDITOR',           'Internal Affairs', 'AUD-001',     true, true,  '$2b$12$placeholder_hash'),
  ('00000000-0000-0000-0000-000000000005', 'sysadmin',     'sysadmin@netra.local',  NULL,            'SYSTEM_ADMIN',      'IT',               NULL,          true, true,  '$2b$12$placeholder_hash'),
  ('00000000-0000-0000-0000-000000000010', 'citizen_arun', NULL,                    '+919876500010', 'CITIZEN',           NULL,               NULL,          true, false, '$2b$12$placeholder_hash'),
  ('00000000-0000-0000-0000-000000000011', 'citizen_suma', NULL,                    '+919876500011', 'CITIZEN',           NULL,               NULL,          true, false, '$2b$12$placeholder_hash'),
  ('00000000-0000-0000-0000-000000000012', 'citizen_ram',  NULL,                    '+919876500012', 'CITIZEN',           NULL,               NULL,          true, false, '$2b$12$placeholder_hash');

-- Citizens (pseudonymised)
INSERT INTO citizens (id, user_id, citizen_id, encrypted_phone, verified_at, verification_method) VALUES
  ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', 'CITABC123DEF456G', '\x706c616365686f6c646572', NOW(), 'MOBILE_OTP'),
  ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000011', 'CITXYZ789QRS012H', '\x706c616365686f6c646572', NOW(), 'MOBILE_OTP'),
  ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000012', 'CITLMN345TUV678I', '\x706c616365686f6c646572', NOW(), 'MOBILE_OTP');

-- ──────────────────────────────────────────────────────────────
-- Test cameras (Pune, Maharashtra area)
-- ──────────────────────────────────────────────────────────────

INSERT INTO cameras (
  id, camera_id, citizen_id, label, camera_class, status,
  geo_point, geo_precision_m, address_area,
  stream_config, consent_mode, live_pull_auth,
  kms_key_id, last_seen_at, agent_version
) VALUES
  (
    '20000000-0000-0000-0000-000000000001',
    'CAM2F9A3B8C1D',
    '10000000-0000-0000-0000-000000000001',
    'Front gate camera',
    'ONVIF',
    'ONLINE',
    ST_SetSRID(ST_MakePoint(73.8567, 18.5204), 4326),
    25,
    'Sector 12, Baner, Pune',
    '{"encrypted": true, "ref": "kms://cam-001"}',
    'EVENT_ONLY',
    'ASK_EACH_TIME',
    'vault://netra-kms/camera-keys/cam-001',
    NOW() - INTERVAL '2 minutes',
    '1.0.0'
  ),
  (
    '20000000-0000-0000-0000-000000000002',
    'CAM4B31A7E2F',
    '10000000-0000-0000-0000-000000000001',
    'Shop entrance',
    'RTSP',
    'ONLINE',
    ST_SetSRID(ST_MakePoint(73.8590, 18.5215), 4326),
    25,
    'Market Road, Baner, Pune',
    '{"encrypted": true, "ref": "kms://cam-002"}',
    'LIVE_PULL_ENABLED',
    'AUTO_ALLOW_EMERGENCY',
    'vault://netra-kms/camera-keys/cam-002',
    NOW() - INTERVAL '5 minutes',
    '1.0.0'
  ),
  (
    '20000000-0000-0000-0000-000000000003',
    'CAM7D22C9F4A',
    '10000000-0000-0000-0000-000000000002',
    'Dashcam Route NH48',
    'DASHCAM',
    'OFFLINE',
    ST_SetSRID(ST_MakePoint(73.7898, 18.5456), 4326),
    100,
    'NH48, near Hinjewadi',
    '{"encrypted": true, "ref": "kms://cam-003"}',
    'EVENT_ONLY',
    'ALWAYS_DENY',
    'vault://netra-kms/camera-keys/cam-003',
    NOW() - INTERVAL '3 hours',
    '1.0.0'
  ),
  (
    '20000000-0000-0000-0000-000000000004',
    'CAM1A09D5E3B',
    '10000000-0000-0000-0000-000000000002',
    'Bus stand CCTV',
    'VENDOR_CLOUD',
    'ONLINE',
    ST_SetSRID(ST_MakePoint(73.8678, 18.5301), 4326),
    25,
    'Baner Bus Stand, Pune',
    '{"encrypted": true, "ref": "kms://cam-004", "vendor": "tapo"}',
    'EVENT_ONLY',
    'ASK_EACH_TIME',
    'vault://netra-kms/camera-keys/cam-004',
    NOW() - INTERVAL '1 minute',
    '1.0.0'
  );

-- Privacy zones for camera 1
INSERT INTO privacy_zones (id, camera_id, label, pixel_polygon) VALUES
  (
    '30000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    'Neighbour window',
    '[{"x": 0, "y": 0}, {"x": 200, "y": 0}, {"x": 200, "y": 150}, {"x": 0, "y": 150}]'
  );

-- ──────────────────────────────────────────────────────────────
-- Integration configs
-- ──────────────────────────────────────────────────────────────

INSERT INTO integration_configs (system_name, is_enabled, endpoint_url, circuit_breaker_state) VALUES
  ('CCTNS',          false, 'https://cctns.api.gov.in/v1',     'CLOSED'),
  ('VAHAN',          false, 'https://vahan.api.nic.in/v1',     'CLOSED'),
  ('SARATHI',        false, 'https://sarathi.api.nic.in/v1',   'CLOSED'),
  ('DIAL_112',       false, 'https://erss.api.gov.in/v1',      'CLOSED'),
  ('KHOYA_PAYA',     false, 'https://khoyapaya.gov.in/api/v1', 'CLOSED'),
  ('SMART_CITY_ICCC',false, NULL,                              'OPEN');

-- ──────────────────────────────────────────────────────────────
-- Sample investigation
-- ──────────────────────────────────────────────────────────────

INSERT INTO investigations (
  id, case_reference, investigation_type, title, status,
  time_window_start, time_window_end,
  lead_officer_id, supervisor_id,
  opened_by, opened_at
) VALUES (
  '40000000-0000-0000-0000-000000000001',
  'FIR/MH/2026/001234',
  'FIR',
  'Hit and run — NH48 near Hinjewadi — 15 Mar 2026',
  'OPEN',
  '2026-03-15 17:00:00+05:30',
  '2026-03-15 21:00:00+05:30',
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  NOW()
);

INSERT INTO investigation_cameras (investigation_id, camera_id, added_by) VALUES
  ('40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001'),
  ('40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001'),
  ('40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001');

-- ──────────────────────────────────────────────────────────────
-- Sample alerts
-- ──────────────────────────────────────────────────────────────

INSERT INTO alerts (id, camera_id, alert_type, status, title, description, confidence, notify_citizen, notify_pcr) VALUES
  (
    '50000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    'PERSON_OF_INTEREST',
    'NEW',
    'Person of interest — BOLO match',
    'Face recognition match against active BOLO watchlist entry. Top-5 candidates returned. Officer attestation required.',
    0.87,
    false,
    true
  ),
  (
    '50000000-0000-0000-0000-000000000002',
    '20000000-0000-0000-0000-000000000002',
    'AUDIO_ANOMALY',
    'ACKNOWLEDGED',
    'Audio anomaly detected — possible scream',
    'YAMNet classifier triggered at 91% confidence. Server confirmation: scream. Edge trigger corroborated.',
    0.91,
    false,
    true
  );

-- ──────────────────────────────────────────────────────────────
-- Audit log genesis record (first entry, prev_hash = 0*64)
-- ──────────────────────────────────────────────────────────────

INSERT INTO audit_logs (action, actor_id, actor_role, subject_type, details, event_hash, prev_hash, occurred_at) VALUES
  (
    'SYSTEM_CONFIG_CHANGE',
    '00000000-0000-0000-0000-000000000005',
    'SYSTEM_ADMIN',
    'SYSTEM',
    '{"action": "database_seeded", "environment": "development"}',
    encode(digest('SYSTEM_CONFIG_CHANGE|00000000-0000-0000-0000-000000000005|SYSTEM|{"action":"database_seeded"}|' || NOW()::text || '|' || repeat('0', 64), 'sha256'), 'hex'),
    repeat('0', 64),
    NOW()
  );

-- Kafka topics (reference only — created by application)
-- netra.clips.raw            partitions=12
-- netra.events               partitions=12
-- netra.analytics.jobs       partitions=24
-- netra.alerts               partitions=6
-- netra.consent.changes      partitions=12
-- netra.audit                partitions=1  (single for ordering)
-- netra.notifications        partitions=6
