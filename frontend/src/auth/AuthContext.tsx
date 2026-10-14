import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as api from '../lib/api'
import type { Credentials, User } from '../types'
import { AuthContext } from './context'
import type { AuthContextValue, AuthStatus } from './context'

interface Session {
  status: AuthStatus
  user: User | null
  sessionMessage: string
}

const ANONYMOUS: Session = { status: 'anonymous', user: null, sessionMessage: '' }

/** A 401 ends the session. Only a session that was signed in gets a "why" message. */
function endSession(previous: Session, detail: string): Session {
  if (previous.status === 'authenticated') {
    return { ...ANONYMOUS, sessionMessage: detail }
  }
  return { ...previous, status: 'anonymous', user: null }
}

function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>({
    status: 'loading',
    user: null,
    sessionMessage: '',
  })

  useEffect(() => {
    let active = true
    const unsubscribe = api.onUnauthorized((detail) =>
      setSession((previous) => endSession(previous, detail)),
    )
    api.getMe().then(
      (user) => {
        if (active) setSession({ status: 'authenticated', user, sessionMessage: '' })
      },
      () => {
        if (active) setSession(ANONYMOUS)
      },
    )
    return () => {
      active = false
      unsubscribe()
    }
  }, [])

  const clearSessionMessage = useCallback(() => {
    setSession((previous) =>
      previous.sessionMessage ? { ...previous, sessionMessage: '' } : previous,
    )
  }, [])

  const login = useCallback(async (credentials: Credentials) => {
    const user = await api.login(credentials)
    setSession({ status: 'authenticated', user, sessionMessage: '' })
  }, [])

  const register = useCallback(async (credentials: Credentials) => {
    const result = await api.register(credentials)
    if (result.session_started && result.user) {
      setSession({ status: 'authenticated', user: result.user, sessionMessage: '' })
    }
    return result
  }, [])

  const logout = useCallback(async () => {
    // The session cookies are HttpOnly, so only the server's 204 clears them. If the request
    // fails, keep the session (and let the error reach the caller) rather than pretend the
    // user is signed out while the cookies would sign them straight back in.
    await api.logout()
    setSession(ANONYMOUS)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ ...session, clearSessionMessage, login, register, logout }),
    [session, clearSessionMessage, login, register, logout],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export default AuthProvider
