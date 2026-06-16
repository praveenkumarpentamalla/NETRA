import {
  Controller, Post, Get, Body, Req, UseGuards,
  HttpCode, HttpStatus, Headers, Delete,
} from '@nestjs/common';
import {
  ApiTags, ApiOperation, ApiResponse, ApiBearerAuth, ApiSecurity,
} from '@nestjs/swagger';
import { Throttle } from '@nestjs/throttler';
import { Request } from 'express';
import * as crypto from 'crypto';

import { AuthService } from '../services/auth.service';
import { JwtAuthGuard } from '../guards/jwt-auth.guard';
import { RolesGuard } from '../guards/roles.guard';
import { Roles } from '../guards/roles.decorator';
import { UserRole } from '../entities/user.entity';
import {
  SendOtpDto, VerifyOtpDto, LoginDto, VerifyMfaDto,
  RefreshTokenDto, SetupMfaDto, RegisterOfficerDto,
} from '../dto/auth.dto';

@ApiTags('Authentication')
@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  // ─── Citizen OTP flow ──────────────────────────────────────

  @Post('citizen/otp/send')
  @Throttle({ default: { limit: 3, ttl: 60000 } }) // 3 OTPs per minute
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Send OTP to citizen mobile number' })
  @ApiResponse({ status: 200, description: 'OTP sent' })
  @ApiResponse({ status: 429, description: 'Too many requests' })
  async sendOtp(@Body() dto: SendOtpDto) {
    return this.authService.sendOtp(dto.phone);
  }

  @Post('citizen/otp/verify')
  @Throttle({ default: { limit: 5, ttl: 60000 } })
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Verify OTP and get tokens (creates account if new)' })
  async verifyOtp(@Body() dto: VerifyOtpDto, @Req() req: Request) {
    const ipHash = crypto
      .createHash('sha256')
      .update(req.ip || 'unknown')
      .digest('hex');
    return this.authService.verifyOtpAndLogin(dto, ipHash);
  }

  // ─── Officer login flow ────────────────────────────────────

  @Post('officer/login')
  @Throttle({ default: { limit: 10, ttl: 60000 } })
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Officer login with username/password' })
  async officerLogin(@Body() dto: LoginDto, @Req() req: Request) {
    const ipHash = crypto.createHash('sha256').update(req.ip || '').digest('hex');
    return this.authService.officerLogin(dto, ipHash);
  }

  @Post('officer/mfa/verify')
  @Throttle({ default: { limit: 5, ttl: 60000 } })
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Complete MFA verification' })
  async verifyMfa(@Body() dto: VerifyMfaDto, @Req() req: Request) {
    const ipHash = crypto.createHash('sha256').update(req.ip || '').digest('hex');
    return this.authService.verifyMfaAndLogin(dto, ipHash);
  }

  // ─── Token management ──────────────────────────────────────

  @Post('token/refresh')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({ summary: 'Refresh access token' })
  async refresh(@Body() dto: RefreshTokenDto, @Req() req: Request) {
    const ipHash = crypto.createHash('sha256').update(req.ip || '').digest('hex');
    return this.authService.refreshToken(dto, ipHash);
  }

  @Delete('token/logout')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Logout and revoke refresh token' })
  async logout(
    @Req() req: Request,
    @Body() dto: RefreshTokenDto,
  ) {
    return this.authService.logout((req as any).user.id, dto.refreshToken);
  }

  // ─── MFA setup ─────────────────────────────────────────────

  @Post('mfa/setup')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Generate TOTP QR code for MFA setup' })
  async setupMfa(@Req() req: Request) {
    return this.authService.setupMfa((req as any).user.id);
  }

  @Post('mfa/confirm')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @HttpCode(HttpStatus.NO_CONTENT)
  @ApiOperation({ summary: 'Confirm MFA setup with TOTP code' })
  async confirmMfa(@Req() req: Request, @Body() dto: SetupMfaDto) {
    return this.authService.confirmMfaSetup((req as any).user.id, dto);
  }

  // ─── Officer management (System Admin only) ────────────────

  @Post('officers')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles(UserRole.SYSTEM_ADMIN)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Register a new officer account' })
  async registerOfficer(@Body() dto: RegisterOfficerDto, @Req() req: Request) {
    return this.authService.registerOfficer(dto, (req as any).user.id);
  }

  // ─── Health / me ───────────────────────────────────────────

  @Get('me')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Get current user profile' })
  async me(@Req() req: Request) {
    const user = (req as any).user;
    return {
      id: user.id,
      username: user.username,
      role: user.role,
      department: user.department,
      mfaEnabled: user.mfaEnabled,
    };
  }
}
