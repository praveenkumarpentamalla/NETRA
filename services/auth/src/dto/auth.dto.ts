import {
  IsString, IsNotEmpty, IsPhoneNumber, Length,
  IsEnum, IsEmail, IsOptional, MinLength, Matches,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { UserRole } from '../entities/user.entity';

export class SendOtpDto {
  @ApiProperty({ example: '+919876543210' })
  @IsPhoneNumber('IN')
  phone: string;
}

export class VerifyOtpDto {
  @ApiProperty({ example: '+919876543210' })
  @IsPhoneNumber('IN')
  phone: string;

  @ApiProperty({ example: '123456' })
  @IsString()
  @Length(6, 6)
  otp: string;
}

export class LoginDto {
  @ApiProperty({ example: 'officer_rajesh' })
  @IsString()
  @IsNotEmpty()
  username: string;

  @ApiProperty()
  @IsString()
  @MinLength(8)
  password: string;
}

export class VerifyMfaDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  mfaToken: string;

  @ApiProperty({ example: '123456' })
  @IsString()
  @Length(6, 6)
  totp: string;
}

export class RefreshTokenDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  refreshToken: string;
}

export class SetupMfaDto {
  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  secret: string;

  @ApiProperty({ example: '123456' })
  @IsString()
  @Length(6, 6)
  totp: string;
}

export class RegisterOfficerDto {
  @ApiProperty()
  @IsString()
  @Length(3, 100)
  @Matches(/^[a-z0-9_]+$/, { message: 'Username must be lowercase alphanumeric with underscores' })
  username: string;

  @ApiPropertyOptional()
  @IsEmail()
  @IsOptional()
  email?: string;

  @ApiProperty()
  @IsString()
  @MinLength(12)
  password: string;

  @ApiProperty({ enum: UserRole })
  @IsEnum(UserRole)
  role: UserRole;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  department?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  badgeNumber?: string;
}

export class RegisterCitizenDto {
  @ApiProperty()
  @IsPhoneNumber('IN')
  phone: string;
}
