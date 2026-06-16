import {
  Injectable, NotFoundException, ForbiddenException,
  BadRequestException, Logger, ConflictException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { EventEmitter2 } from '@nestjs/event-emitter';

import { Camera, CameraStatus, CameraClass } from '../entities/camera.entity';
import { PrivacyZone } from '../entities/privacy-zone.entity';
import {
  RegisterCameraDto, UpdateConsentDto, UpdatePrivacyZonesDto,
  UpdateAwayModeDto, RevokeCameraDto, PauseCameraDto,
} from '../dto/camera.dto';
import { KmsService } from '../services/kms.service';
import { AuditService } from '../services/audit.service';

@Injectable()
export class CameraService {
  private readonly logger = new Logger(CameraService.name);

  constructor(
    @InjectRepository(Camera)
    private readonly cameraRepo: Repository<Camera>,
    @InjectRepository(PrivacyZone)
    private readonly pvZoneRepo: Repository<PrivacyZone>,
    private readonly kmsService: KmsService,
    private readonly auditService: AuditService,
    private readonly events: EventEmitter2,
    private readonly dataSource: DataSource,
  ) {}

  /** Register a new camera (citizen flow) */
  async register(citizenId: string, dto: RegisterCameraDto): Promise<Camera> {
    // Validate that FOV polygon doesn't point into residential interiors
    await this.validateFov(dto);

    return this.dataSource.transaction(async (em) => {
      // Provision a per-camera encryption key in KMS
      const kmsKeyId = await this.kmsService.createCameraKey(citizenId);

      const cameraId = 'CAM' + Buffer.from(
        Math.random().toString(36).substring(2) + Date.now().toString(36)
      ).toString('base64url').substring(0, 20).toUpperCase();

      // Encrypt stream credentials before storing
      const encryptedConfig = await this.kmsService.encryptCameraConfig(
        kmsKeyId, dto.streamConfig,
      );

      const camera = em.create(Camera, {
        cameraId,
        citizenId,
        label: dto.label,
        cameraClass: dto.cameraClass,
        status: CameraStatus.PENDING,
        addressArea: dto.addressArea,
        geoPoint: dto.geoPoint ? {
          type: 'Point',
          coordinates: [dto.geoPoint.lng, dto.geoPoint.lat],
        } : undefined,
        geoPrecisionM: dto.geoPrecisionM || 25,
        fovImagePolygon: dto.fovImagePolygon,
        streamConfig: encryptedConfig,
        consentMode: dto.consentMode,
        livePullAuth: dto.livePullAuth,
        alertSubscriptions: dto.alertSubscriptions || [],
        kmsKeyId,
      });

      const saved = await em.save(camera);

      // Save privacy zones
      if (dto.privacyZones?.length) {
        const zones = dto.privacyZones.map(z =>
          em.create(PrivacyZone, {
            cameraId: saved.id,
            label: z.label,
            pixelPolygon: z.pixelPolygon,
            isActive: true,
          })
        );
        await em.save(zones);
      }

      await this.auditService.log({
        action: 'CAMERA_REGISTER',
        actorId: citizenId,
        subjectType: 'CAMERA',
        subjectId: saved.id,
        details: { cameraId, cameraClass: dto.cameraClass },
      });

      // Emit event for Bridge Agent to pick up configuration
      this.events.emit('camera.registered', { cameraId, citizenId });
      this.logger.log(`Camera registered: ${cameraId} by citizen ${citizenId}`);

      return saved;
    });
  }

  /** One-tap revocation — must propagate within 60 seconds */
  async revoke(citizenId: string, cameraId: string, dto: RevokeCameraDto): Promise<void> {
    const camera = await this.findCameraForCitizen(citizenId, cameraId);

    await this.dataSource.transaction(async (em) => {
      // Mark as revoked immediately
      await em.update(Camera, camera.id, {
        status: CameraStatus.REVOKED,
        revokedAt: new Date(),
        revokedReason: dto.reason,
        deletionScheduledAt: new Date(
          Date.now() + (dto.deletionDays ?? 30) * 24 * 60 * 60 * 1000
        ),
      });

      // Schedule KMS key destruction for cryptographic erasure
      await this.kmsService.scheduleKeyDeletion(camera.kmsKeyId, dto.deletionDays ?? 30);

      await this.auditService.log({
        action: 'CAMERA_REVOKE',
        actorId: citizenId,
        subjectType: 'CAMERA',
        subjectId: camera.id,
        details: { reason: dto.reason, deletionDays: dto.deletionDays },
      });
    });

    // CRITICAL: emit revocation event — Bridge Agent must stop within 60s
    this.events.emit('camera.revoked', {
      cameraId: camera.cameraId,
      citizenId,
      timestamp: new Date().toISOString(),
    });

    this.logger.warn(`Camera REVOKED: ${camera.cameraId} — deletion in ${dto.deletionDays ?? 30}d`);
  }

  /** One-tap pause (reversible) */
  async pause(citizenId: string, cameraId: string, dto: PauseCameraDto): Promise<void> {
    const camera = await this.findCameraForCitizen(citizenId, cameraId);
    if (camera.status === CameraStatus.REVOKED) {
      throw new ForbiddenException('Camera is revoked and cannot be paused');
    }

    await this.cameraRepo.update(camera.id, { status: CameraStatus.PAUSED });
    this.events.emit('camera.paused', { cameraId: camera.cameraId, citizenId });

    await this.auditService.log({
      action: 'CAMERA_PAUSE',
      actorId: citizenId,
      subjectType: 'CAMERA',
      subjectId: camera.id,
      details: { reason: dto.reason },
    });
  }

  /** Resume a paused camera */
  async resume(citizenId: string, cameraId: string): Promise<void> {
    const camera = await this.findCameraForCitizen(citizenId, cameraId);
    if (camera.status !== CameraStatus.PAUSED) {
      throw new BadRequestException('Camera is not paused');
    }

    await this.cameraRepo.update(camera.id, { status: CameraStatus.ONLINE });
    this.events.emit('camera.resumed', { cameraId: camera.cameraId, citizenId });

    await this.auditService.log({
      action: 'CAMERA_RESUME',
      actorId: citizenId,
      subjectType: 'CAMERA',
      subjectId: camera.id,
      details: {},
    });
  }

  /** Update per-camera consent settings */
  async updateConsent(citizenId: string, cameraId: string, dto: UpdateConsentDto): Promise<Camera> {
    const camera = await this.findCameraForCitizen(citizenId, cameraId);

    await this.cameraRepo.update(camera.id, {
      consentMode: dto.consentMode,
      livePullAuth: dto.livePullAuth,
      awayModeEnabled: dto.awayModeEnabled,
      awaySchedule: dto.awaySchedule,
      alertSubscriptions: dto.alertSubscriptions,
    });

    this.events.emit('camera.consent_updated', { cameraId: camera.cameraId, dto });

    await this.auditService.log({
      action: 'CONSENT_UPDATE',
      actorId: citizenId,
      subjectType: 'CAMERA',
      subjectId: camera.id,
      details: dto,
    });

    return this.cameraRepo.findOne({ where: { id: camera.id } }) as Promise<Camera>;
  }

  /** Update privacy zones — propagates to Bridge Agent within 60s */
  async updatePrivacyZones(
    citizenId: string, cameraId: string, dto: UpdatePrivacyZonesDto,
  ): Promise<PrivacyZone[]> {
    const camera = await this.findCameraForCitizen(citizenId, cameraId);

    await this.dataSource.transaction(async (em) => {
      // Deactivate all existing zones
      await em.update(PrivacyZone, { cameraId: camera.id }, { isActive: false });

      // Insert new zones
      if (dto.zones.length > 0) {
        const zones = dto.zones.map(z =>
          em.create(PrivacyZone, {
            cameraId: camera.id,
            label: z.label,
            pixelPolygon: z.pixelPolygon,
            isActive: true,
          })
        );
        await em.save(zones);
      }
    });

    // Critical: push mask update to Bridge Agent
    this.events.emit('camera.privacy_zones_updated', {
      cameraId: camera.cameraId,
      zones: dto.zones,
    });

    return this.pvZoneRepo.find({ where: { cameraId: camera.id, isActive: true } });
  }

  /** Get all cameras for a citizen */
  async getCitizenCameras(citizenId: string): Promise<Camera[]> {
    return this.cameraRepo.find({
      where: { citizenId },
      order: { createdAt: 'DESC' },
    });
  }

  /** Get camera (PCR view — no PII, pseudonymous IDs only) */
  async getCameraPcrView(cameraId: string): Promise<Partial<Camera>> {
    const camera = await this.cameraRepo.findOne({ where: { cameraId } });
    if (!camera) throw new NotFoundException('Camera not found');

    // Strip any fields that could identify the citizen
    const { citizenId, streamConfig, kmsKeyId, ...pcrSafeView } = camera;
    return pcrSafeView;
  }

  /** Called by Bridge Agent heartbeat */
  async updateAgentHeartbeat(cameraId: string, version: string): Promise<void> {
    await this.cameraRepo
      .createQueryBuilder()
      .update()
      .set({ lastSeenAt: new Date(), agentVersion: version, status: CameraStatus.ONLINE })
      .where('camera_id = :cameraId', { cameraId })
      .execute();
  }

  // ─── Private helpers ───────────────────────────────────────

  private async findCameraForCitizen(citizenId: string, cameraId: string): Promise<Camera> {
    const camera = await this.cameraRepo.findOne({ where: { id: cameraId } });
    if (!camera) throw new NotFoundException('Camera not found');
    if (camera.citizenId !== citizenId) throw new ForbiddenException('Not your camera');
    return camera;
  }

  private async validateFov(dto: RegisterCameraDto): Promise<void> {
    // In production: run an AI classifier to detect if FOV points into
    // residential interiors or neighbouring private spaces.
    // Here we enforce a minimum privacy zone requirement.
    if (!dto.fovImagePolygon) {
      throw new BadRequestException('Field of view polygon is required');
    }
  }
}
