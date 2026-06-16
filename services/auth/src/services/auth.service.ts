import {
  Injectable, UnauthorizedException, BadRequestException,
  ConflictException, ForbiddenException, Logger,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import * as bcrypt from 'bcryptjs';
import { v4 as uuidv4 } from 'uuid';

import { User, UserRole } from '../entities/user.entity';
import { UserSession } from '../entities/user-session.entity';
import { Citizen } from '../entities/citizen.entity';
import { OtpService } from './otp.service';
import { TokenService } from './token.service';
import { AuditService } from './audit.service';
import {
  RegisterCitizenDto, LoginDto, VerifyOtpDto,
  RegisterOfficerDto, RefreshTokenDto, SetupMfaDto, VerifyMfaDto,
} from '../dto/auth.dto';

@Injectable()
export class AuthService {
  private readonly logger = new Logger(AuthService.name);

  constructor(
    @InjectRepository(User)
    private readonly userRepo: Repository<User>,
    @InjectRepository(UserSession)
    private readonly sessionRepo: Repository<UserSession>,
    @InjectRepository(Citizen)
    private readonly citizenRepo: Repository<Citizen>,
    private readonly otpService: OtpService,
    private readonly tokenService: TokenService,
    private readonly auditService: AuditService,
    private readonly dataSource: DataSource,
  ) {}

  /** Step 1: Citizen sends phone number, gets OTP */
  async sendOtp(phone: string): Promise<{ message: string }> {
    const normalised = this.normalisePhone(phone);
    await this.otpService.sendOtp(normalised);
    return { message: 'OTP sent' };
  }

  /** Step 2: Citizen verifies OTP, gets account created or logged in */
  async verifyOtpAndLogin(dto: VerifyOtpDto, ipHash: string): Promise<{
    accessToken: string;
    refreshToken: string;
    isNewUser: boolean;
  }> {
    const phone = this.normalisePhone(dto.phone);
    const valid = await this.otpService.verifyOtp(phone, dto.otp);
    if (!valid) throw new UnauthorizedException('Invalid or expired OTP');

    let user = await this.userRepo.findOne({ where: { phone } });
    let isNewUser = false;

    if (!user) {
      isNewUser = true;
      user = await this.createCitizenUser(phone, ipHash);
    }

    if (!user.isActive) {
      throw new ForbiddenException('Account is suspended');
    }

    const { accessToken, refreshToken } = await this.createSession(user, ipHash);
    await this.userRepo.update(user.id, { lastLoginAt: new Date() });

    return { accessToken, refreshToken, isNewUser };
  }

  /** Officer login with username/password + MFA */
  async officerLogin(dto: LoginDto, ipHash: string): Promise<{
    accessToken: string;
    refreshToken: string;
    requiresMfa: boolean;
    mfaToken?: string;
  }> {
    const user = await this.userRepo.findOne({ where: { username: dto.username } });
    if (!user || !(await bcrypt.compare(dto.password, user.passwordHash))) {
      throw new UnauthorizedException('Invalid credentials');
    }
    if (!user.isActive) throw new ForbiddenException('Account is suspended');
    if (user.role === UserRole.CITIZEN) throw new ForbiddenException('Use citizen login');

    // MFA required for all PCR roles
    if (user.mfaEnabled) {
      const mfaToken = await this.tokenService.generateMfaToken(user.id);
      return { accessToken: '', refreshToken: '', requiresMfa: true, mfaToken };
    }

    const { accessToken, refreshToken } = await this.createSession(user, ipHash);
    await this.userRepo.update(user.id, { lastLoginAt: new Date() });
    this.logger.log(`Officer login: ${user.username} [${user.role}]`);

    return { accessToken, refreshToken, requiresMfa: false };
  }

  /** Complete MFA step for officer */
  async verifyMfaAndLogin(dto: VerifyMfaDto, ipHash: string): Promise<{
    accessToken: string;
    refreshToken: string;
  }> {
    const userId = await this.tokenService.verifyMfaToken(dto.mfaToken);
    if (!userId) throw new UnauthorizedException('Invalid or expired MFA token');

    const user = await this.userRepo.findOne({ where: { id: userId } });
    if (!user) throw new UnauthorizedException('User not found');

    const isValid = this.otpService.verifyTotp(user.mfaSecret!, dto.totp);
    if (!isValid) throw new UnauthorizedException('Invalid TOTP code');

    const { accessToken, refreshToken } = await this.createSession(user, ipHash);
    await this.userRepo.update(user.id, { lastLoginAt: new Date() });

    return { accessToken, refreshToken };
  }

  /** Refresh access token */
  async refreshToken(dto: RefreshTokenDto, ipHash: string): Promise<{
    accessToken: string;
    refreshToken: string;
  }> {
    const session = await this.tokenService.validateRefreshToken(dto.refreshToken);
    if (!session) throw new UnauthorizedException('Invalid refresh token');

    const user = await this.userRepo.findOne({ where: { id: session.userId } });
    if (!user || !user.isActive) throw new UnauthorizedException('User not found or suspended');

    // Revoke old session (rotation)
    await this.sessionRepo.update(session.id, { revokedAt: new Date() });

    const { accessToken, refreshToken } = await this.createSession(user, ipHash);
    return { accessToken, refreshToken };
  }

  /** Logout: revoke session */
  async logout(userId: string, refreshToken: string): Promise<void> {
    const session = await this.tokenService.validateRefreshToken(refreshToken);
    if (session && session.userId === userId) {
      await this.sessionRepo.update(session.id, { revokedAt: new Date() });
    }
  }

  /** Setup MFA for PCR officer */
  async setupMfa(userId: string): Promise<{ qrCodeDataUrl: string; secret: string }> {
    const user = await this.userRepo.findOneOrFail({ where: { id: userId } });
    return this.otpService.generateTotpSecret(user.username);
  }

  /** Confirm MFA setup */
  async confirmMfaSetup(userId: string, dto: SetupMfaDto): Promise<void> {
    const valid = this.otpService.verifyTotp(dto.secret, dto.totp);
    if (!valid) throw new BadRequestException('Invalid TOTP — try again');
    await this.userRepo.update(userId, {
      mfaSecret: dto.secret, // store encrypted via Vault in production
      mfaEnabled: true,
    });
  }

  /** Validate JWT payload (used by JwtStrategy) */
  async validateJwtPayload(payload: { sub: string; role: UserRole }): Promise<User | null> {
    const user = await this.userRepo.findOne({ where: { id: payload.sub, isActive: true } });
    return user || null;
  }

  /** Register officer account (SYSTEM_ADMIN only) */
  async registerOfficer(dto: RegisterOfficerDto, createdBy: string): Promise<User> {
    const existing = await this.userRepo.findOne({ where: { username: dto.username } });
    if (existing) throw new ConflictException('Username already exists');

    const passwordHash = await bcrypt.hash(dto.password, 12);
    const user = this.userRepo.create({
      ...dto,
      passwordHash,
      isActive: true,
      mfaEnabled: false,
    });
    const saved = await this.userRepo.save(user);

    await this.auditService.log({
      action: 'SYSTEM_CONFIG_CHANGE' as any,
      actorId: createdBy,
      actorRole: UserRole.SYSTEM_ADMIN,
      subjectType: 'USER',
      subjectId: saved.id,
      details: { action: 'officer_created', role: dto.role, username: dto.username },
    });

    return saved;
  }

  // ─── Private helpers ───────────────────────────────────────

  private async createCitizenUser(phone: string, ipHash: string): Promise<User> {
    return this.dataSource.transaction(async (em) => {
      const passwordHash = await bcrypt.hash(uuidv4(), 12); // random, never used
      const user = em.create(User, {
        username: `citizen_${Date.now()}`,
        phone,
        role: UserRole.CITIZEN,
        passwordHash,
        isActive: true,
      });
      const savedUser = await em.save(user);

      // Create pseudonymised citizen record
      const citizenId = 'CIT' + Buffer.from(uuidv4().replace(/-/g, ''), 'hex')
        .toString('base64url').substring(0, 16).toUpperCase();
      const encryptedPhone = Buffer.from(phone); // in prod: encrypt via KMS

      const citizen = em.create(Citizen, {
        userId: savedUser.id,
        citizenId,
        encryptedPhone,
        verifiedAt: new Date(),
        verificationMethod: 'MOBILE_OTP',
      });
      await em.save(citizen);

      this.logger.log(`New citizen registered: ${citizenId}`);
      return savedUser;
    });
  }

  private async createSession(user: User, ipHash: string): Promise<{
    accessToken: string;
    refreshToken: string;
  }> {
    const accessToken = await this.tokenService.signAccessToken({
      sub: user.id,
      role: user.role,
    });
    const { token: refreshToken, hash } = await this.tokenService.generateRefreshToken();

    const session = this.sessionRepo.create({
      userId: user.id,
      refreshTokenHash: hash,
      ipAddress: ipHash as any,
      expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7d
    });
    await this.sessionRepo.save(session);

    return { accessToken, refreshToken };
  }

  private normalisePhone(phone: string): string {
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.startsWith('91') && cleaned.length === 12) return `+${cleaned}`;
    if (cleaned.length === 10) return `+91${cleaned}`;
    return `+${cleaned}`;
  }
}
