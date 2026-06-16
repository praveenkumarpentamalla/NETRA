import {
  Entity, PrimaryGeneratedColumn, Column,
  CreateDateColumn, UpdateDateColumn, OneToOne, JoinColumn, Index,
} from 'typeorm';
import { User } from './user.entity';

@Entity('citizens')
export class Citizen {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @OneToOne(() => User)
  @JoinColumn({ name: 'user_id' })
  user: User;

  @Column({ name: 'user_id' })
  userId: string;

  @Index({ unique: true })
  @Column({ name: 'citizen_id', length: 20 })
  citizenId: string; // pseudonymous — shown to PCR

  @Column({ name: 'encrypted_phone', type: 'bytea' })
  encryptedPhone: Buffer; // real phone — never shown to PCR

  @Column({ name: 'encrypted_name', type: 'bytea', nullable: true })
  encryptedName?: Buffer;

  @Column({ name: 'verified_at', type: 'timestamptz', nullable: true })
  verifiedAt?: Date;

  @Column({ name: 'verification_method', default: 'MOBILE_OTP' })
  verificationMethod: string;

  @Column({ name: 'aadhaar_linked', default: false })
  aadhaarLinked: boolean;

  @Column({ name: 'participation_score', default: 0 })
  participationScore: number;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt: Date;
}
