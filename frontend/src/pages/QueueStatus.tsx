import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import SessionBar from '../components/SessionBar'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApiData } from '../hooks/useApiData'
import { getQueue } from '../lib/api'
import type { Queue } from '../types'

export const QUEUE_POLL_INTERVAL_MS = 15_000

interface QueueDetailsProps {
  queue: Queue
  refreshFailed: boolean
}

function QueueDetails({ queue, refreshFailed }: QueueDetailsProps) {
  const navigate = useNavigate()
  const [showNote, setShowNote] = useState(true)
  const { appointment } = queue
  const progress = queue.progress_percent

  return (
    <>
      <div className="mt-6 rounded-xl bg-teal-600 p-5 text-center text-white shadow-sm">
        <p className="text-xs font-medium uppercase tracking-widest text-teal-100">Queue token</p>
        <p className="mt-1 text-4xl font-extrabold tracking-tight">{queue.token}</p>
        <span className="mt-3 inline-block rounded-full bg-white/20 px-3 py-1 text-xs font-semibold">
          {queue.status_label}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center">
          <p className="text-xs font-medium text-slate-500">Current position</p>
          <p className="mt-1 text-3xl font-extrabold text-slate-900">{queue.position ?? '–'}</p>
          <p className="mt-1 text-xs text-slate-500">{queue.ahead} ahead of you</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center">
          <p className="text-xs font-medium text-slate-500">
            {queue.is_today ? 'Est. waiting time' : 'Est. wait on the day'}
          </p>
          <p className="mt-1 text-3xl font-extrabold text-slate-900">
            {queue.estimated_wait_minutes}
          </p>
          <p className="mt-1 text-xs text-slate-500">minutes approx.</p>
        </div>
      </div>
      <div className="mt-4 rounded-xl border border-slate-200 p-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-500">{queue.serving_label}</span>
          <span className="font-bold text-teal-700">{queue.now_serving ?? '–'}</span>
        </div>
        <div
          role="progressbar"
          aria-label="Queue progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
          className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100"
        >
          <div className="h-full rounded-full bg-teal-600" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {queue.is_today
            ? `${progress}% through the queue - please stay nearby.`
            : 'Your queue position updates on the day of your appointment.'}
        </p>
      </div>
      <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm">
        <p className="font-semibold text-slate-900">Appointment information</p>
        <dl className="mt-2 space-y-1.5 text-slate-600">
          <div className="flex justify-between gap-3">
            <dt>Doctor</dt>
            <dd className="text-right font-medium text-slate-900">
              {appointment.doctor.name} - {appointment.doctor.specialty}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>Date</dt>
            <dd className="font-medium text-slate-900">{appointment.date_label}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>Time</dt>
            <dd className="font-medium text-slate-900">{appointment.time_label}</dd>
          </div>
        </dl>
      </div>
      {refreshFailed && (
        <p role="status" className="mt-4 text-center text-xs text-amber-700">
          We couldn&apos;t refresh your queue status just now. Retrying automatically.
        </p>
      )}
      {showNote && (
        <div className="mt-4 flex items-start justify-between gap-3 rounded-lg border border-teal-100 bg-teal-50 p-3 text-sm text-teal-800">
          <p>This page updates automatically every 15 seconds.</p>
          <button
            type="button"
            onClick={() => setShowNote(false)}
            className="font-semibold underline"
          >
            Dismiss
          </button>
        </div>
      )}
      <button
        type="button"
        onClick={() => navigate('/confirmation')}
        className="mt-4 w-full rounded-lg bg-teal-600 px-4 py-2.5 font-semibold text-white transition hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:ring-offset-2"
      >
        View confirmation
      </button>
    </>
  )
}

function QueueStatus() {
  const navigate = useNavigate()
  const { state, retry } = useApiData(getQueue, QUEUE_POLL_INTERVAL_MS)

  let content
  if (state.status === 'loading') {
    content = <LoadingState label="Loading your queue status..." />
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
    content = <QueueDetails queue={state.data} refreshFailed={state.refreshError !== null} />
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
          <h2 className="mt-2 text-lg font-semibold text-slate-800">Your queue status</h2>
          <p className="mt-1 text-sm text-slate-500">
            No need to ask staff - monitor your position here digitally.
          </p>
        </div>
        {content}
      </div>
    </div>
  )
}

export default QueueStatus
