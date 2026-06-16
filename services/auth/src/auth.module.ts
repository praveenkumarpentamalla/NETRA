import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { PassportModule } from '@nestjs/passport';
import { ThrottlerModule } from '@nestjs/throttler';

import { AuthController } from './controllers/auth.controller';
import { AuthService } from './services/auth.service';
import { OtpService } from './services/otp.service';
import { TokenService } from './services/token.service';
import { AuditService } from './services/audit.service';

import { JwtStrategy } from './strategies/jwt.strategy';
import { LocalStrategy } from './strategies/local.strategy';

import { User } from './entities/user.entity';
import { UserSession } from './entities/user-session.entity';
import { Citizen } from './entities/citizen.entity';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    ThrottlerModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (cfg: ConfigService) => [{
        ttl: cfg.get('RATE_LIMIT_TTL', 60),
        limit: cfg.get('RATE_LIMIT_MAX', 100),
      }],
    }),
    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (cfg: ConfigService) => ({
        type: 'postgres',
        host: cfg.get('POSTGRES_HOST'),
        port: cfg.get<number>('POSTGRES_PORT', 5432),
        username: cfg.get('POSTGRES_USER'),
        password: cfg.get('POSTGRES_PASSWORD'),
        database: cfg.get('POSTGRES_DB'),
        entities: [User, UserSession, Citizen],
        synchronize: false, // use migrations
        ssl: cfg.get('NODE_ENV') === 'production' ? { rejectUnauthorized: true } : false,
      }),
    }),
    TypeOrmModule.forFeature([User, UserSession, Citizen]),
    PassportModule.register({ defaultStrategy: 'jwt' }),
    JwtModule.registerAsync({
      inject: [ConfigService],
      useFactory: (cfg: ConfigService) => ({
        secret: cfg.get('JWT_SECRET'),
        signOptions: { expiresIn: cfg.get('JWT_EXPIRES_IN', '1h') },
      }),
    }),
  ],
  controllers: [AuthController],
  providers: [
    AuthService,
    OtpService,
    TokenService,
    AuditService,
    JwtStrategy,
    LocalStrategy,
  ],
  exports: [AuthService, TokenService],
})
export class AuthModule {}
