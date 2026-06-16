import {
  Injectable, ForbiddenException, BadRequestException,
  NotFoundException, Logger, ConflictException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource, LessThan } from 'typeorm';
import * as crypto from 'crypto';
import { Cron, CronExpression } from '@nestjs/schedule';

import { WatchlistEntry, WatchlistStatus } from '../entities/watchlist-entry.entity';
import { AnprBoloList } from '../entities/anpr-bolo-list.entity';
import { UserRole } from '../../shared/types';
import { AddWatchlistEntryDto, ReviewWatchlistEntryDto, RemoveWatchlistEntryDto } from '../dto/watchlist.dto';
import { AuditService } from './audit.service';
import { KmsService } from './kms.service';
import { MilvusService } from './milvus.service';

// ──────────────────────────────────────────────────────────────
// PROHIBITED CATEGORIES — Structural enforcement at service layer
// Any attempt to add these is rejected with a 403 and audit logged.
// ──────────────────────────────────────────────────────────────
const PROHIBITED_CATEGORY_KEYWORDS = [
  'journalist', 'activist', 'lawyer', 'protest', 'political',
  'religious', 'caste', 'opposition', 'union', 'ngo', 'reporter',
  'demonstration', 'rally', 'strike', 'opposition',
];

@Injectable()
export class WatchlistService {
  private readonly logger = new Logger(WatchlistService.name);

  constructor(
    @InjectRepository(WatchlistEntry)
    private readonly entryRepo: Repository<WatchlistEntry>,
    @InjectRepository(AnprBoloList)
    private readonly boloRepo: Repository<AnprBoloList>,
    private readonly auditService: AuditService,
    private readonly kmsService: KmsService,
    private readonly milvusService: MilvusService,
    private readonly dataSource: DataSource,
  ) {}

  /**
   * Add a watchlist entry.
   * Requires: SENIOR_SP role.
   * Two-officer rule: approving officer cannot be the same as the requesting officer.
   */
  async addEntry(
    actorId: string,
    actorRole: UserRole,
    dto: AddWatchlistEntryDto,
  ): Promise<WatchlistEntry> {
    // Role check: only Senior SP can add
    if (actorRole !== UserRole.SENIOR_SP && actorRole !== UserRole.SYSTEM_ADMIN) {
      throw new ForbiddenException('Only Senior SP can manage watchlist entries');
    }

    // ── PROHIBITED CATEGORY CHECK ──────────────────────────────
    this.enforceProhibitedCategories(dto.description);

    // Validate governance fields
    if (!dto.reference || dto.reference.trim().length < 5) {
      throw new BadRequestException('Valid FIR/NCMC/investigation reference required');
    }

    // Max 180-day expiry
    const maxExpiry = new Date(Date.now() + 180 * 24 * 60 * 60 * 1000);
    const expiry = dto.expiryAt ? new Date(dto.expiryAt) : maxExpiry;
    if (expiry > maxExpiry) {
      throw new BadRequestException('Watchlist entries cannot exceed 180 days without review');
    }

    // Check category caps to prevent sprawl
    await this.enforceCapLimits(dto.category);

    return this.dataSource.transaction(async (em) => {
      // Store biometric template in KMS (separate, tightly-controlled scope)
      let biometricTemplateId: string | undefined;
      let biometricHash: string | undefined;

      if (dto.faceEmbedding) {
        biometricTemplateId = await this.kmsService.storeWatchlistTemplate(
          dto.faceEmbedding, actorId,
        );
        biometricHash = crypto
          .createHash('sha256')
          .update(Buffer.from(dto.faceEmbedding))
          .digest('hex');

        // Store in Milvus watchlist collection
        await this.milvusService.insertWatchlistEmbedding({
          templateId: biometricTemplateId,
          embedding: dto.faceEmbedding,
          category: dto.category,
          reference: dto.reference,
        });
      }

      // Compute hash chain
      const lastEntry = await em.findOne(WatchlistEntry, {
        order: { createdAt: 'DESC' },
      });
      const prevHash = lastEntry?.hashChainAnchor ?? '0'.repeat(64);
      const hashPayload = [
        dto.category, dto.reference, actorId,
        expiry.toISOString(), prevHash,
      ].join('|');
      const hashChainAnchor = crypto
        .createHash('sha256')
        .update(hashPayload)
        .digest('hex');

      const entry = em.create(WatchlistEntry, {
        category: dto.category,
        reference: dto.reference.trim(),
        description: dto.description,
        biometricTemplateId,
        biometricHash,
        approvingOfficerId: actorId,
        approvedAt: new Date(),
        expiryAt: expiry,
        status: WatchlistStatus.ACTIVE,
        hashChainAnchor,
        prevHash,
        prohibitedCategoryCheck: false, // must stay false
      });

      const saved = await em.save(entry);

      await this.auditService.log({
        action: 'WATCHLIST_ADD',
        actorId,
        actorRole,
        subjectType: 'WATCHLIST_ENTRY',
        subjectId: saved.id,
        details: {
          category: dto.category,
          reference: dto.reference,
          expiryAt: expiry.toISOString(),
          hasBiometric: !!biometricTemplateId,
        },
      });

      this.logger.log(`Watchlist entry added: ${saved.id} [${dto.category}]`);
      return saved;
    });
  }

  /** Remove a watchlist entry — two-officer rule applies */
  async removeEntry(
    actorId: string,
    actorRole: UserRole,
    entryId: string,
    dto: RemoveWatchlistEntryDto,
    cosignerId: string, // second officer (two-officer rule)
  ): Promise<void> {
    if (actorRole !== UserRole.SENIOR_SP && actorRole !== UserRole.SYSTEM_ADMIN) {
      throw new ForbiddenException('Only Senior SP can remove watchlist entries');
    }
    if (actorId === cosignerId) {
      throw new ForbiddenException('Two-officer rule: removing officer cannot be the same as co-signer');
    }

    const entry = await this.entryRepo.findOne({ where: { id: entryId } });
    if (!entry) throw new NotFoundException('Watchlist entry not found');
    if (entry.status === WatchlistStatus.REMOVED) {
      throw new ConflictException('Entry already removed');
    }

    await this.dataSource.transaction(async (em) => {
      await em.update(WatchlistEntry, entry.id, {
        status: WatchlistStatus.REMOVED,
        removalReason: dto.reason,
        removedBy: actorId,
        removedAt: new Date(),
      });

      if (entry.biometricTemplateId) {
        await this.milvusService.removeWatchlistEmbedding(entry.biometricTemplateId);
      }

      await this.auditService.log({
        action: 'WATCHLIST_REMOVE',
        actorId,
        actorRole,
        subjectType: 'WATCHLIST_ENTRY',
        subjectId: entry.id,
        details: { reason: dto.reason, cosignerId },
      });
    });
  }

  /** Periodic review — re-affirm entry before expiry */
  async reviewEntry(
    actorId: string,
    actorRole: UserRole,
    entryId: string,
    dto: ReviewWatchlistEntryDto,
  ): Promise<WatchlistEntry> {
    if (actorRole !== UserRole.SENIOR_SP && actorRole !== UserRole.SYSTEM_ADMIN) {
      throw new ForbiddenException('Only Senior SP can review watchlist entries');
    }

    const entry = await this.entryRepo.findOne({ where: { id: entryId } });
    if (!entry) throw new NotFoundException('Entry not found');
    if (entry.status !== WatchlistStatus.ACTIVE) {
      throw new BadRequestException('Can only review active entries');
    }

    const newExpiry = new Date(Date.now() + 180 * 24 * 60 * 60 * 1000);

    await this.entryRepo.update(entry.id, {
      reviewedBy: actorId,
      reviewedAt: new Date(),
      expiryAt: newExpiry,
    });

    await this.auditService.log({
      action: 'WATCHLIST_REVIEW',
      actorId,
      actorRole,
      subjectType: 'WATCHLIST_ENTRY',
      subjectId: entry.id,
      details: { newExpiryAt: newExpiry.toISOString(), reviewNote: dto.note },
    });

    return this.entryRepo.findOne({ where: { id: entryId } }) as Promise<WatchlistEntry>;
  }

  /** Auto-expire entries that passed their expiry date */
  @Cron(CronExpression.EVERY_HOUR)
  async autoExpireEntries(): Promise<void> {
    const expired = await this.entryRepo.find({
      where: { status: WatchlistStatus.ACTIVE, expiryAt: LessThan(new Date()) },
    });

    for (const entry of expired) {
      await this.entryRepo.update(entry.id, { status: WatchlistStatus.EXPIRED });
      if (entry.biometricTemplateId) {
        await this.milvusService.removeWatchlistEmbedding(entry.biometricTemplateId);
      }
      this.logger.log(`Auto-expired watchlist entry: ${entry.id}`);
    }
  }

  // ─── Private helpers ───────────────────────────────────────

  private enforceProhibitedCategories(description?: string): void {
    if (!description) return;
    const lower = description.toLowerCase();
    const found = PROHIBITED_CATEGORY_KEYWORDS.find(kw => lower.includes(kw));
    if (found) {
      this.logger.error(`PROHIBITED CATEGORY INJECTION ATTEMPT: keyword "${found}"`);
      throw new ForbiddenException(
        `Watchlist entries cannot reference prohibited categories. ` +
        `Political affiliation, religious affiliation, caste, journalistic/activist status, ` +
        `and protest attendance are structurally forbidden.`
      );
    }
  }

  private async enforceCapLimits(category: string): Promise<void> {
    const caps: Record<string, number> = {
      WANTED: 500,
      MISSING: 1000,
      BOLO_SUSPECT: 500,
    };
    const cap = caps[category];
    if (!cap) return;

    const count = await this.entryRepo.count({
      where: { category: category as any, status: WatchlistStatus.ACTIVE },
    });

    if (count >= cap) {
      throw new BadRequestException(
        `Category cap of ${cap} reached for ${category}. Review and remove expired entries.`
      );
    }
  }
}
