import { createContext } from 'react';
import type { User } from '../../api/platform.ts';

export type AuthStatus = 'loading' | 'signed-in' | 'signed-out';

export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  signIn: (email: string, password: string, remember: boolean) => Promise<User>;
  signOut: () => Promise<void>;
  setUser: (user: User) => void;
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
