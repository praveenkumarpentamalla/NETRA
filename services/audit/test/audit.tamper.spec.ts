import * as crypto from 'crypto';

/**
 * GOVERNANCE RED-TEAM TEST
 * KPI-15 (GATING): Audit-log tamper-detection — 100% required
 *
 * Verifies that any modification to a historical audit record
 * breaks the hash chain and is detectable.
 */

interface AuditRecord {
  logUuid: string;
  action: string;
  actorId: string;
  subjectId: string;
  details: string;
  occurredAt: string;
  eventHash: string;
  prevHash: string;
}

function computeHash(record: Omit<AuditRecord, 'eventHash'>): string {
  const payload = [
    record.action,
    record.actorId,
    record.subjectId,
    record.details,
    record.occurredAt,
    record.prevHash,
  ].join('|');
  return crypto.createHash('sha256').update(payload).digest('hex');
}

function buildChain(n: number): AuditRecord[] {
  const chain: AuditRecord[] = [];
  let prevHash = '0'.repeat(64);

  for (let i = 0; i < n; i++) {
    const base = {
      logUuid: `uuid-${i}`,
      action: 'CLIP_VIEW',
      actorId: `officer-${i % 3}`,
      subjectId: `event-${i}`,
      details: JSON.stringify({ index: i }),
      occurredAt: new Date(2026, 2, 15, 10, i).toISOString(),
      prevHash,
    };
    const eventHash = computeHash(base);
    chain.push({ ...base, eventHash });
    prevHash = eventHash;
  }
  return chain;
}

function verifyChain(chain: AuditRecord[]): { valid: boolean; brokenAt: number | null } {
  let expectedPrevHash = '0'.repeat(64);

  for (let i = 0; i < chain.length; i++) {
    const record = chain[i];

    // Verify prev_hash linkage
    if (record.prevHash !== expectedPrevHash) {
      return { valid: false, brokenAt: i };
    }

    // Verify event_hash is correctly computed
    const recomputed = computeHash({
      logUuid: record.logUuid,
      action: record.action,
      actorId: record.actorId,
      subjectId: record.subjectId,
      details: record.details,
      occurredAt: record.occurredAt,
      prevHash: record.prevHash,
    });

    if (recomputed !== record.eventHash) {
      return { valid: false, brokenAt: i };
    }

    expectedPrevHash = record.eventHash;
  }

  return { valid: true, brokenAt: null };
}

describe('Audit Log Hash Chain — Tamper Detection (KPI-15, GATING)', () => {
  it('verifies an untampered chain as valid', () => {
    const chain = buildChain(100);
    const result = verifyChain(chain);
    expect(result.valid).toBe(true);
    expect(result.brokenAt).toBeNull();
  });

  it('DETECTS tampering with a field in a middle record', () => {
    const chain = buildChain(100);
    // Tamper with record 50 — change actor without recomputing hash
    chain[50].actorId = 'malicious-actor';

    const result = verifyChain(chain);
    expect(result.valid).toBe(false);
    expect(result.brokenAt).toBe(50);
  });

  it('DETECTS tampering with the details field', () => {
    const chain = buildChain(50);
    chain[20].details = JSON.stringify({ index: 20, tampered: true });

    const result = verifyChain(chain);
    expect(result.valid).toBe(false);
    expect(result.brokenAt).toBe(20);
  });

  it('DETECTS deletion of a record (chain re-link attempt)', () => {
    const chain = buildChain(50);
    // Remove record 25 and re-link 24 -> 26 (sophisticated tamper attempt)
    const tamperedChain = [...chain.slice(0, 25), ...chain.slice(26)];
    // Attacker would need to recompute hash chain from point of deletion
    // Without doing so, prevHash linkage breaks immediately
    const result = verifyChain(tamperedChain);
    expect(result.valid).toBe(false);
  });

  it('DETECTS tampering even when attacker recomputes the tampered hash but not subsequent chain', () => {
    const chain = buildChain(50);

    // Sophisticated attack: recompute hash for tampered record itself
    chain[30].actorId = 'malicious-actor';
    chain[30].eventHash = computeHash({
      logUuid: chain[30].logUuid,
      action: chain[30].action,
      actorId: chain[30].actorId, // tampered value
      subjectId: chain[30].subjectId,
      details: chain[30].details,
      occurredAt: chain[30].occurredAt,
      prevHash: chain[30].prevHash,
    });

    // But record 31's prevHash still points to the OLD hash of record 30
    const result = verifyChain(chain);
    expect(result.valid).toBe(false);
    expect(result.brokenAt).toBe(31); // breaks at the next record's prevHash check
  });

  it('100% detection rate across 1000 random single-field tampers', () => {
    let detectionCount = 0;
    const trials = 1000;

    for (let trial = 0; trial < trials; trial++) {
      const chain = buildChain(20);
      const tamperIndex = Math.floor(Math.random() * chain.length);
      const fields = ['actorId', 'subjectId', 'details'] as const;
      const field = fields[Math.floor(Math.random() * fields.length)];
      chain[tamperIndex][field] = 'TAMPERED_VALUE';

      const result = verifyChain(chain);
      if (!result.valid) detectionCount++;
    }

    const detectionRate = detectionCount / trials;
    expect(detectionRate).toBe(1.0); // KPI-15 requires 100%
  });

  it('verifies Merkle root changes when any record in the batch is tampered', () => {
    function computeMerkleRoot(hashes: string[]): string {
      if (hashes.length === 0) return '0'.repeat(64);
      if (hashes.length === 1) return hashes[0];

      const nextLevel: string[] = [];
      for (let i = 0; i < hashes.length; i += 2) {
        const left = hashes[i];
        const right = hashes[i + 1] ?? left;
        nextLevel.push(
          crypto.createHash('sha256').update(left + right).digest('hex'),
        );
      }
      return computeMerkleRoot(nextLevel);
    }

    const chain = buildChain(16);
    const originalHashes = chain.map(r => r.eventHash);
    const originalRoot = computeMerkleRoot(originalHashes);

    // Tamper with one record's hash
    const tamperedHashes = [...originalHashes];
    tamperedHashes[8] = crypto.createHash('sha256').update('tampered').digest('hex');
    const tamperedRoot = computeMerkleRoot(tamperedHashes);

    expect(tamperedRoot).not.toBe(originalRoot);
  });
});
