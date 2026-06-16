import {
  Entity, PrimaryGeneratedColumn, Column, ManyToOne,
  OneToMany, JoinColumn, CreateDateColumn, UpdateDateColumn, Index,
} from 'typeorm';

export enum CameraStatus {
  PENDING = 'PENDING',
  ONLINE = 'ONLINE',
  OFFLINE = 'OFFLINE',
  PAUSED = 'PAUSED',
  REVOKED = 'REVOKED',
  ERROR = 'ERROR',
}

export enum CameraClass {
  ONVIF = 'ONVIF',
  RTSP = 'RTSP',
  VENDOR_CLOUD = 'VENDOR_CLOUD',
  DVR_NVR = 'DVR_NVR',
  PHONE_CAMERA = 'PHONE_CAMERA',
  DASHCAM = 'DASHCAM',
  USB_WEBCAM = 'USB_WEBCAM',
}

export enum LivePullAuth {
  ALWAYS_DENY = 'ALWAYS_DENY',
  ASK_EACH_TIME = 'ASK_EACH_TIME',
  AUTO_ALLOW_EMERGENCY = 'AUTO_ALLOW_EMERGENCY',
}

export enum ConsentMode {
  EVENT_ONLY = 'EVENT_ONLY',
  LIVE_PULL_ENABLED = 'LIVE_PULL_ENABLED',
}

@Entity('cameras')
export class Camera {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Index({ unique: true })
  @Column({ name: 'camera_id', length: 30 })
  cameraId: string; // pseudonymous — shown to PCR

  @Column({ name: 'citizen_id' })
  citizenId: string;

  @Column({ length: 100, nullable: true })
  label?: string;

  @Column({ name: 'camera_class', type: 'enum', enum: CameraClass })
  cameraClass: CameraClass;

  @Column({ type: 'enum', enum: CameraStatus, default: CameraStatus.PENDING })
  status: CameraStatus;

  @Column({
    name: 'geo_point',
    type: 'geometry',
    spatialFeatureType: 'Point',
    srid: 4326,
    nullable: true,
  })
  geoPoint?: object;

  @Column({ name: 'geo_precision_m', default: 25 })
  geoPrecisionM: number;

  @Column({ name: 'fov_polygon', type: 'geometry', spatialFeatureType: 'Polygon', srid: 4326, nullable: true })
  fovPolygon?: object;

  @Column({ name: 'fov_image_polygon', type: 'jsonb', nullable: true })
  fovImagePolygon?: object; // pixel-coordinate polygon

  @Column({ name: 'address_area', length: 200, nullable: true })
  addressArea?: string;

  @Column({ name: 'stream_config', type: 'jsonb', default: '{}' })
  streamConfig: object; // encrypted credentials

  @Column({ name: 'consent_mode', type: 'enum', enum: ConsentMode, default: ConsentMode.EVENT_ONLY })
  consentMode: ConsentMode;

  @Column({ name: 'live_pull_auth', type: 'enum', enum: LivePullAuth, default: LivePullAuth.ASK_EACH_TIME })
  livePullAuth: LivePullAuth;

  @Column({ name: 'away_mode_enabled', default: false })
  awayModeEnabled: boolean;

  @Column({ name: 'away_schedule', type: 'jsonb', nullable: true })
  awaySchedule?: { start: string; end: string; days: number[] };

  @Column({ name: 'alert_subscriptions', type: 'jsonb', default: '[]' })
  alertSubscriptions: string[];

  @Column({ name: 'kms_key_id', length: 200 })
  kmsKeyId: string;

  @Column({ name: 'last_seen_at', type: 'timestamptz', nullable: true })
  lastSeenAt?: Date;

  @Column({ name: 'last_event_at', type: 'timestamptz', nullable: true })
  lastEventAt?: Date;

  @Column({ name: 'online_since', type: 'timestamptz', nullable: true })
  onlineSince?: Date;

  @Column({ name: 'agent_version', length: 50, nullable: true })
  agentVersion?: string;

  @Column({ name: 'revoked_at', type: 'timestamptz', nullable: true })
  revokedAt?: Date;

  @Column({ name: 'revoked_reason', length: 500, nullable: true })
  revokedReason?: string;

  @Column({ name: 'deletion_scheduled_at', type: 'timestamptz', nullable: true })
  deletionScheduledAt?: Date;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt: Date;
}
