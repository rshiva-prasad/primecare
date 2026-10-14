import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import SessionBar from '../components/SessionBar'
import IconButton from '../components/ui/IconButton'
import { useNavigate } from 'react-router-dom'
import { useLogout } from '../auth/useLogout'
import { useApiData } from '../hooks/useApiData'
import { getCurrentAppointment } from '../lib/api'
import type { Appointment } from '../types'

interface AppointmentSummaryProps {
  appointment: Appointment
}

function AppointmentSummary({ appointment }: AppointmentSummaryProps) {
  const navigate = useNavigate()
  const { logout, loggingOut, error } = useLogout()

  return (
    <>
      <div className="mt-6 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-100">
          <svg
            className="h-7 w-7 text-green-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="mt-3 font-semibold text-green-700">
          Your appointment has been booked successfully.
        </p>
        <p className="mt-1 text-sm text-slate-500">
          You can monitor your queue position digitally - no need to keep asking staff.
        </p>
      </div>
      <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
        <div className="text-center">
          <p className="text-xs font-medium uppercase tracking-widest text-slate-500">
            Queue token
          </p>
          <p className="mt-1 text-3xl font-extrabold text-slate-900">{appointment.token}</p>
        </div>
        <dl className="mt-4 space-y-2 text-slate-600">
          <div className="flex justify-between gap-3">
            <dt>Doctor</dt>
            <dd className="text-right font-medium text-slate-900">{appointment.doctor.name}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>Specialty</dt>
            <dd className="font-medium text-slate-900">{appointment.doctor.specialty}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>Date</dt>
            <dd className="font-medium text-slate-900">{appointment.date_label}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>Time</dt>
            <dd className="font-medium text-slate-900">{appointment.time_label}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>Status</dt>
            <dd>
              <span className="inline-block rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                {appointment.status_label}
              </span>
            </dd>
          </div>
        </dl>
      </div>
      <div className="mt-5 space-y-3">
        <IconButton label="View queue status" onClick={() => navigate('/queue-status')} />
        <button
          type="button"
          onClick={logout}
          disabled={loggingOut}
          className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2.5 font-semibold text-slate-700 transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Log out
        </button>
        {error && (
          <p role="alert" className="text-center text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    </>
  )
}

function Confirmation() {
  const navigate = useNavigate()
  const { state, retry } = useApiData(getCurrentAppointment)

  let content
  if (state.status === 'loading') {
    content = <LoadingState label="Loading your appointment..." />
  } else if (state.status === 'error' && state.error.status === 404) {
    content = (
      <EmptyState
        title={state.error.detail}
        message="Book an appointment to receive your queue token."
        actionLabel="Book an appointment"
        onAction={() => navigate('/book-appointment')}
      />
    )
  } else if (state.status === 'error') {
    content = (
      <div className="mt-6">
        <ErrorState message={state.error.detail} onRetry={retry} />
      </div>
    )
  } else {
    content = <AppointmentSummary appointment={state.data} />
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 px-4 py-10">
      <SessionBar />
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-teal-600 text-xl font-bold text-white">
            P
          </div>
          <h1 className="mt-4 text-2xl font-bold text-slate-900">PrimeCare Clinic</h1>
          <h2 className="mt-2 text-lg font-semibold text-slate-800">
            {state.status === 'success' ? 'Appointment confirmed' : 'Your appointment'}
          </h2>
        </div>
        {content}
      </div>
    </div>
  )
}

export default Confirmation
