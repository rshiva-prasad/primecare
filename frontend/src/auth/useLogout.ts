import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './useAuth'

export const LOGOUT_ERROR_MESSAGE =
  "We couldn't log you out. Please check your connection and try again."

export function useLogout() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [loggingOut, setLoggingOut] = useState(false)
  const [error, setError] = useState('')

  const handleLogout = useCallback(async () => {
    setLoggingOut(true)
    setError('')
    try {
      await logout()
    } catch {
      // Still signed in (the server never cleared the cookies): stay here so the user can retry.
      setError(LOGOUT_ERROR_MESSAGE)
      setLoggingOut(false)
      return
    }
    navigate('/login', { replace: true })
  }, [logout, navigate])

  return { logout: handleLogout, loggingOut, error }
}
