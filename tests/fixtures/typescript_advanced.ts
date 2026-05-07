// Test fixture for upstream PR — exercises every new extraction path.
//
// Expected nodes after this PR:
//   - IUserRepository       (interface)
//   - UserStatus            (enum) + Active, Inactive (members)
//   - UserId                (type_alias)
//   - USER_REPOSITORY       (const, value=call_expression)
//   - DEFAULT_ROLES         (const, value=array)
//   - USER_CONFIG           (const, value=object)
//   - UserService           (class — already extracted by current code)
//   - UserModule            (class — already extracted)
//
// Expected edges after this PR:
//   - UserService.create() --instantiates--> User
//   - UserService.bulkCreate() --instantiates--> Array
//   - UserModule --provides--> UserService
//   - UserModule --provides--> USER_REPOSITORY (via { provide, useClass } detection — optional)
//   - UserModule --exports--> UserService

import { Module, Injectable } from '@nestjs/common';
import type { User } from './user.entity';

export interface IUserRepository {
  findById(id: string): Promise<User | null>;
  save(user: User): Promise<void>;
}

export enum UserStatus {
  Active = 'ACTIVE',
  Inactive = 'INACTIVE',
  Suspended = 'SUSPENDED',
}

export type UserId = string;

export const USER_REPOSITORY = Symbol('USER_REPOSITORY');

export const DEFAULT_ROLES = ['admin', 'editor', 'user'] as const;

export const USER_CONFIG = {
  maxRetries: 3,
  timeoutMs: 5000,
  features: {
    twoFactor: true,
    sso: false,
  },
};

@Injectable()
export class UserService {
  constructor(private repo: IUserRepository) {}

  create(name: string): User {
    return new User(name);
  }

  bulkCreate(names: string[]): User[] {
    return names.map((n) => new User(n));
  }
}

@Module({
  providers: [
    UserService,
    { provide: USER_REPOSITORY, useClass: PrismaUserRepository },
  ],
  exports: [UserService],
})
export class UserModule {}
