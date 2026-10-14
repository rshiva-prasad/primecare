import { Navigate, Outlet } from 'react-router-dom'
import LoadingState from '../components/LoadingState'
import { useAuth } from './useAuth'

function ProtectedRoute() {
  const { status } = useAuth()

  if (status === 'loading') {
    return <LoadingState label="Checking your session..." fullPage />
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

export default ProtectedRoute
