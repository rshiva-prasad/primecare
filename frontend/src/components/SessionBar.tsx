import { useAuth } from '../auth/useAuth'
import { useLogout } from '../auth/useLogout'

function SessionBar() {
  const { user } = useAuth()
  const { logout, loggingOut, error } = useLogout()

  if (!user) {
    return null
  }
  return (
    <p className="w-full max-w-md text-right text-xs text-slate-500">
      Signed in as <span className="font-medium text-slate-700">{user.email}</span>
      <span aria-hidden="true"> · </span>
      <button
        type="button"
        onClick={logout}
        disabled={loggingOut}
        className="font-semibold text-teal-700 underline hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        Log out
      </button>
      {error && (
        <span role="alert" className="mt-1 block text-red-600">
          {error}
        </span>
      )}
    </p>
  )
}

export default SessionBar
