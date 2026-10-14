import { createContext } from 'react'
import type { Credentials, RegisterResponse, User } from '../types'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export interface AuthContextValue {
  status: AuthStatus
  user: User | null
  /** Why a signed-in session just ended (the server's 401 detail); '' when there is none. */
  sessionMessage: string
  clearSessionMessage: () => void
  login: (credentials: Credentials) => Promise<void>
  register: (credentials: Credentials) => Promise<RegisterResponse>
  /** Rejects (and keeps the session) when the server could not confirm the logout. */
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
