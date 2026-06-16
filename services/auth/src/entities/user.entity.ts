import {
  Entity, PrimaryGeneratedColumn, Column, CreateDateColumn,
  UpdateDateColumn, DeleteDateColumn, OneToMany, Index,
} from 'typeorm';

export enum UserRole {
  CITIZEN = 'CITIZEN',
  WATCHER = 'WATCHER',
  IO = 'IO',
  SHIFT_SUPERVISOR = 'SHIFT_SUPERVISOR',
  SENIOR_SP = 'SENIOR_SP',
  AUDITOR = 'AUDITOR',
  SYSTEM_ADMIN = 'SYSTEM_ADMIN',
}

@Entity('users')
export class User {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Index({ unique: true })
  @Column({ length: 100 })
  username: string;

  @Index({ unique: true, where: '"email" IS NOT NULL' })
  @Column({ length: 255, nullable: true })
  email?: string;

  @Index({ unique: true, where: '"phone" IS NOT NULL' })
  @Column({ length: 20, nullable: true })
  phone?: string;

  @Column({ type: 'enum', enum: UserRole, default: UserRole.CITIZEN })
  role: UserRole;

  @Column({ length: 200, nullable: true })
  department?: string;

  @Column({ name: 'badge_number', length: 50, nullable: true })
  badgeNumber?: string;

  @Column({ name: 'is_active', default: true })
  isActive: boolean;

  @Column({ name: 'mfa_enabled', default: false })
  mfaEnabled: boolean;

  @Column({ name: 'mfa_secret', nullable: true })
  mfaSecret?: string;

  @Column({ name: 'last_login_at', type: 'timestamptz', nullable: true })
  lastLoginAt?: Date;

  @Column({ name: 'password_hash' })
  passwordHash: string;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt: Date;

  @DeleteDateColumn({ name: 'deleted_at', type: 'timestamptz', nullable: true })
  deletedAt?: Date;
}
