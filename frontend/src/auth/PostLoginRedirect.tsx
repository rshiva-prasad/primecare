import { Navigate } from 'react-router-dom'
import LoadingState from '../components/LoadingState'
import { useApiData } from '../hooks/useApiData'
import { getCurrentAppointment } from '../lib/api'

/**
 * Where a signed-in patient lands: their queue status when they already have an upcoming
 * appointment, otherwise Patient Details. Any lookup failure falls back to Patient Details,
 * and a 401 ends the session through the API layer, which returns them to the login form.
 */
function PostLoginRedirect() {
  const { state } = useApiData(getCurrentAppointment)

  if (state.status === 'loading') {
    return <LoadingState label="Opening your appointment..." fullPage />
  }
  return <Navigate to={state.status === 'success' ? '/queue-status' : '/patient-details'} replace />
}

export default PostLoginRedirect
