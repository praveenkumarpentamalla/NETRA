import {
  Injectable, CanActivate, ExecutionContext,
  SetMetadata, applyDecorators, UseGuards,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { AuthGuard } from '@nestjs/passport';
import { UserRole } from '../entities/user.entity';

export const ROLES_KEY = 'roles';
export const Roles = (...roles: UserRole[]) => SetMetadata(ROLES_KEY, roles);

@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {}

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(ctx: ExecutionContext): boolean {
    const required = this.reflector.getAllAndOverride<UserRole[]>(ROLES_KEY, [
      ctx.getHandler(),
      ctx.getClass(),
    ]);
    if (!required || required.length === 0) return true;

    const { user } = ctx.switchToHttp().getRequest();
    if (!user) return false;

    // SYSTEM_ADMIN can access everything
    if (user.role === UserRole.SYSTEM_ADMIN) return true;

    return required.includes(user.role);
  }
}

/**
 * Role hierarchy for convenience:
 * SENIOR_SP > SHIFT_SUPERVISOR > IO > WATCHER > CITIZEN
 */
export const ROLE_HIERARCHY: Record<UserRole, number> = {
  [UserRole.CITIZEN]: 0,
  [UserRole.WATCHER]: 1,
  [UserRole.IO]: 2,
  [UserRole.SHIFT_SUPERVISOR]: 3,
  [UserRole.SENIOR_SP]: 4,
  [UserRole.AUDITOR]: 2, // special: read-only access at IO level
  [UserRole.SYSTEM_ADMIN]: 99,
};

export function hasMinRole(userRole: UserRole, minRole: UserRole): boolean {
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[minRole];
}
