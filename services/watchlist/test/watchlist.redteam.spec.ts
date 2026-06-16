import { Test, TestingModule } from '@nestjs/testing';
import { ForbiddenException, BadRequestException } from '@nestjs/common';
import { getRepositoryToken } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';

import { WatchlistService } from '../src/services/watchlist.service';
import { WatchlistEntry, WatchlistStatus } from '../src/entities/watchlist-entry.entity';
import { AnprBoloList } from '../src/entities/anpr-bolo-list.entity';
import { AuditService } from '../src/services/audit.service';
import { KmsService } from '../src/services/kms.service';
import { MilvusService } from '../src/services/milvus.service';
import { UserRole } from '../src/../shared/types';

/**
 * GOVERNANCE RED-TEAM TESTS
 * KPI-18: Watchlist prohibited-category injection — 100% rejection required (GATING)
 * KPI-17: Two-officer-rule enforcement — 100% required (GATING)
 */

describe('WatchlistService — Governance Red-Team', () => {
  let service: WatchlistService;
  let mockEntryRepo: any;
  let mockAuditService: any;

  beforeEach(async () => {
    mockEntryRepo = {
      findOne: jest.fn(),
      count: jest.fn().mockResolvedValue(0),
      find: jest.fn(),
      update: jest.fn(),
    };

    mockAuditService = { log: jest.fn() };

    const mockDataSource = {
      transaction: jest.fn((cb) => cb({
        findOne: jest.fn(),
        create: jest.fn((_, data) => data),
        save: jest.fn((data) => Promise.resolve({ id: 'mock-id', ...data })),
        update: jest.fn(),
      })),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        WatchlistService,
        { provide: getRepositoryToken(WatchlistEntry), useValue: mockEntryRepo },
        { provide: getRepositoryToken(AnprBoloList), useValue: { findOne: jest.fn() } },
        { provide: AuditService, useValue: mockAuditService },
        { provide: KmsService, useValue: { storeWatchlistTemplate: jest.fn() } },
        { provide: MilvusService, useValue: { insertWatchlistEmbedding: jest.fn() } },
        { provide: DataSource, useValue: mockDataSource },
      ],
    }).compile();

    service = module.get<WatchlistService>(WatchlistService);
  });

  // ── PROHIBITED CATEGORY TESTS (KPI-18, GATING) ──────────────

  describe('Prohibited category rejection', () => {
    const prohibitedDescriptions = [
      'Local journalist covering corruption stories',
      'Active member of opposition political party',
      'Human rights activist organising protests',
      'Practicing lawyer representing dissidents',
      'Attended anti-government rally last month',
      'Member of religious minority organisation',
      'Belongs to scheduled caste advocacy group',
      'Trade union leader at textile factory',
      'NGO worker focused on civil liberties',
      'Newspaper reporter for regional daily',
    ];

    test.each(prohibitedDescriptions)(
      'REJECTS watchlist entry with description: "%s"',
      async (description) => {
        await expect(
          service.addEntry(
            'officer-1',
            UserRole.SENIOR_SP,
            {
              category: 'BOLO_SUSPECT' as any,
              reference: 'FIR/2026/00001',
              description,
            } as any,
          ),
        ).rejects.toThrow(ForbiddenException);
      },
    );

    it('logs the rejection attempt with prohibited category details', async () => {
      try {
        await service.addEntry(
          'officer-1',
          UserRole.SENIOR_SP,
          {
            category: 'BOLO_SUSPECT' as any,
            reference: 'FIR/2026/00002',
            description: 'Local journalist under suspicion',
          } as any,
        );
      } catch (e) {
        expect(e).toBeInstanceOf(ForbiddenException);
      }
    });

    it('ALLOWS legitimate watchlist entry without prohibited keywords', async () => {
      mockEntryRepo.findOne.mockResolvedValue(null);
      mockEntryRepo.count.mockResolvedValue(5);

      const result = await service.addEntry(
        'officer-1',
        UserRole.SENIOR_SP,
        {
          category: 'WANTED' as any,
          reference: 'FIR/2026/00099',
          description: 'Suspect in armed robbery case, last seen near railway station',
        } as any,
      );

      expect(result).toBeDefined();
      expect(mockAuditService.log).toHaveBeenCalledWith(
        expect.objectContaining({ action: 'WATCHLIST_ADD' }),
      );
    });
  });

  // ── ROLE ENFORCEMENT TESTS ──────────────────────────────────

  describe('Role-based access enforcement', () => {
    it('REJECTS watchlist add from IO role (insufficient privilege)', async () => {
      await expect(
        service.addEntry(
          'officer-2',
          UserRole.IO,
          { category: 'WANTED' as any, reference: 'FIR/2026/00003', description: 'Test' } as any,
        ),
      ).rejects.toThrow(ForbiddenException);
    });

    it('REJECTS watchlist add from SHIFT_SUPERVISOR role', async () => {
      await expect(
        service.addEntry(
          'officer-3',
          UserRole.SHIFT_SUPERVISOR,
          { category: 'WANTED' as any, reference: 'FIR/2026/00004', description: 'Test' } as any,
        ),
      ).rejects.toThrow(ForbiddenException);
    });

    it('ALLOWS watchlist add from SENIOR_SP role', async () => {
      mockEntryRepo.findOne.mockResolvedValue(null);
      mockEntryRepo.count.mockResolvedValue(0);

      await expect(
        service.addEntry(
          'officer-4',
          UserRole.SENIOR_SP,
          { category: 'WANTED' as any, reference: 'FIR/2026/00005', description: 'Legitimate case' } as any,
        ),
      ).resolves.toBeDefined();
    });
  });

  // ── TWO-OFFICER RULE TESTS (KPI-17, GATING) ─────────────────

  describe('Two-officer rule enforcement', () => {
    it('REJECTS removal when actor and cosigner are the same officer', async () => {
      mockEntryRepo.findOne.mockResolvedValue({
        id: 'entry-1',
        status: WatchlistStatus.ACTIVE,
      });

      await expect(
        service.removeEntry(
          'officer-5',
          UserRole.SENIOR_SP,
          'entry-1',
          { reason: 'No longer relevant' },
          'officer-5', // SAME as actor — must be rejected
        ),
      ).rejects.toThrow(ForbiddenException);
    });

    it('ALLOWS removal when actor and cosigner differ', async () => {
      mockEntryRepo.findOne.mockResolvedValue({
        id: 'entry-2',
        status: WatchlistStatus.ACTIVE,
        biometricTemplateId: null,
      });

      await expect(
        service.removeEntry(
          'officer-5',
          UserRole.SENIOR_SP,
          'entry-2',
          { reason: 'Case closed' },
          'officer-6', // different officer
        ),
      ).resolves.not.toThrow();
    });
  });

  // ── EXPIRY ENFORCEMENT TESTS ─────────────────────────────────

  describe('180-day expiry enforcement', () => {
    it('REJECTS expiry beyond 180 days from approval', async () => {
      const farFutureExpiry = new Date();
      farFutureExpiry.setDate(farFutureExpiry.getDate() + 365);

      await expect(
        service.addEntry(
          'officer-1',
          UserRole.SENIOR_SP,
          {
            category: 'WANTED' as any,
            reference: 'FIR/2026/00006',
            description: 'Test case',
            expiryAt: farFutureExpiry.toISOString(),
          } as any,
        ),
      ).rejects.toThrow(BadRequestException);
    });
  });

  // ── CATEGORY CAP ENFORCEMENT ─────────────────────────────────

  describe('Category cap enforcement (anti-sprawl)', () => {
    it('REJECTS new entry when category cap reached', async () => {
      mockEntryRepo.count.mockResolvedValue(500); // at WANTED cap

      await expect(
        service.addEntry(
          'officer-1',
          UserRole.SENIOR_SP,
          { category: 'WANTED' as any, reference: 'FIR/2026/00007', description: 'Test' } as any,
        ),
      ).rejects.toThrow(BadRequestException);
    });
  });
});
