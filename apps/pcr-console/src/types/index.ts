// ──────────────────────────────────────────────────────────────
// Project NETRA — Shared TypeScript Types
// ──────────────────────────────────────────────────────────────

export type UserRole =
  | 'CITIZEN' | 'WATCHER' | 'IO' | 'SHIFT_SUPERVISOR'
  | 'SENIOR_SP' | 'AUDITOR' | 'SYSTEM_ADMIN';

export type CameraStatus = 'PENDING' | 'ONLINE' | 'OFFLINE' | 'PAUSED' | 'REVOKED' | 'ERROR';
export type CameraClass = 'ONVIF' | 'RTSP' | 'VENDOR_CLOUD' | 'DVR_NVR' | 'PHONE_CAMERA' | 'DASHCAM' | 'USB_WEBCAM';
export type LivePullAuth = 'ALWAYS_DENY' | 'ASK_EACH_TIME' | 'AUTO_ALLOW_EMERGENCY';
export type ConsentMode = 'EVENT_ONLY' | 'LIVE_PULL_ENABLED';

export interface Camera {
  id: string;
  cameraId: string;
  label?: string;
  cameraClass: CameraClass;
  status: CameraStatus;
  latitude: number;
  longitude: number;
  geoPrecisionM: number;
  fovImagePolygon?: PolygonPoint[];
  addressArea?: string;
  consentMode: ConsentMode;
  livePullAuth: LivePullAuth;
  awayModeEnabled: boolean;
  lastSeenAt?: string;
  lastEventAt?: string;
  agentVersion?: string;
  createdAt: string;
  updatedAt: string;
}

export interface PolygonPoint {
  x: number;
  y: number;
}

export type AlertType =
  | 'AWAY_MODE_NIGHT_MOTION' | 'VEHICLE_OF_INTEREST' | 'PERSON_OF_INTEREST'
  | 'LOITERING' | 'AUDIO_ANOMALY' | 'CROWD_ANOMALY' | 'CAMERA_OFFLINE'
  | 'CAMERA_TAMPER' | 'PRIVACY_ZONE_VIOLATION';

export type AlertStatus = 'NEW' | 'ACKNOWLEDGED' | 'INVESTIGATING' | 'RESOLVED' | 'DISMISSED';

export interface Alert {
  id: string;
  cameraId?: string;
  eventId?: string;
  alertType: AlertType;
  status: AlertStatus;
  title: string;
  description?: string;
  confidence?: number;
  latitude?: number;
  longitude?: number;
  matchCandidates?: WatchlistCandidate[];
  acknowledgedBy?: string;
  acknowledgedAt?: string;
  attestedBy?: string;
  attestedAt?: string;
  attestationNote?: string;
  createdAt: string;
  updatedAt: string;
}

export interface WatchlistCandidate {
  rank: number;
  watchlistEntryId: string;
  calibratedProbability: number;
  similarityScore: number;
  category: 'WANTED' | 'MISSING' | 'BOLO_SUSPECT';
}

export type InvestigationType = 'FIR' | 'PCR_CALL' | 'MISSING_PERSON' | 'BOLO';
export type InvestigationStatus = 'OPEN' | 'CLOSED' | 'SUSPENDED' | 'ARCHIVED';

export interface Investigation {
  id: string;
  caseReference: string;
  investigationType: InvestigationType;
  title: string;
  description?: string;
  status: InvestigationStatus;
  geoFence?: GeoJSONPolygon;
  timeWindowStart: string;
  timeWindowEnd?: string;
  leadOfficerId?: string;
  leadOfficerName?: string;
  supervisorId?: string;
  cctnsFireId?: string;
  openedAt: string;
  closedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export type EventType =
  | 'MOTION' | 'PERSON_DETECTED' | 'VEHICLE_DETECTED' | 'AUDIO_ANOMALY'
  | 'LOITERING' | 'CROWD_ANOMALY' | 'FIGHT_DETECTED' | 'ABANDONED_OBJECT'
  | 'AWAY_MODE_MOTION' | 'PRIVACY_ZONE_VIOLATION' | 'CAMERA_TAMPER';

export interface Event {
  id: string;
  cameraId: string;
  eventType: EventType;
  occurredAt: string;
  clipPath?: string;
  clipHash?: string;
  clipSizeBytes?: number;
  clipDurationMs?: number;
  clipResolution?: string;
  edgeDetections?: Detection[];
  triggerConfidence?: number;
  serverAnalytics?: Record<string, any>;
  latitude?: number;
  longitude?: number;
  legalHold: boolean;
  createdAt: string;
}

export interface Detection {
  class: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface LivePullSession {
  id: string;
  cameraId: string;
  investigationId?: string;
  requestedBy: string;
  caseReference: string;
  tier: 'TIER_1' | 'TIER_2' | 'TIER_3';
  status: 'REQUESTED' | 'PENDING_APPROVAL' | 'PENDING_CITIZEN' | 'ACTIVE' | 'COMPLETED' | 'DENIED' | 'TIMEOUT';
  approvedBy?: string;
  approvedAt?: string;
  watermarkId?: string;
  startedAt?: string;
  endedAt?: string;
  durationSeconds?: number;
  maxDurationSeconds: number;
  createdAt: string;
}

export interface AuditLog {
  id: number;
  logUuid: string;
  action: string;
  actorId?: string;
  actorRole?: UserRole;
  subjectType?: string;
  subjectId?: string;
  investigationId?: string;
  caseReference?: string;
  details: Record<string, any>;
  eventHash: string;
  occurredAt: string;
}

export interface WatchlistEntry {
  id: string;
  category: 'WANTED' | 'MISSING' | 'BOLO_SUSPECT';
  reference: string;
  description?: string;
  approvingOfficerId: string;
  approvedAt: string;
  reviewedAt?: string;
  expiryAt: string;
  status: 'ACTIVE' | 'EXPIRED' | 'REMOVED';
  createdAt: string;
}

export interface GeoBounds {
  north: number;
  south: number;
  east: number;
  west: number;
}

export interface GeoJSONPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
}

// Search query types
export type SearchType = 'attribute' | 'plate' | 'face' | 'reid';

export interface SearchQuery {
  type: SearchType;
  filters: {
    plate?: string;
    vehicleDesc?: string;
    clothingDesc?: string;
    timeStart?: string;
    timeEnd?: string;
    faceData?: string;
    personData?: string;
    eventTypes?: EventType[];
  };
}

export interface Notification {
  id: string;
  recipientId: string;
  notificationType: string;
  title: string;
  body?: string;
  isTransparency: boolean;
  cameraId?: string;
  caseReference?: string;
  accessDurationS?: number;
  isRead: boolean;
  createdAt: string;
}
