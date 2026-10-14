import { act, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { callsTo, deferred, mockFetch } from '../test/fetchMock'
import type { MockReply, MockRoutes } from '../test/fetchMock'
import { queue, signedIn } from '../test/fixtures'
import { navigatedTo, renderProtectedPage } from '../test/render'
import QueueStatus, { QUEUE_POLL_INTERVAL_MS } from './QueueStatus'

const QUEUE = 'GET /api/appointments/current/queue'

function renderPage(routes: MockRoutes) {
  const fetchMock = mockFetch({ ...signedIn, ...routes })
  const view = renderProtectedPage(<QueueStatus />, '/queue-status')
  return { fetchMock, ...view }
}

describe('QueueStatus', () => {
  it('shows a loading state, then the live queue', async () => {
    const reply = deferred<MockReply>()
    renderPage({ [QUEUE]: () => reply.promise })
    expect(await screen.findByText('Loading your queue status...')).toBeInTheDocument()
    reply.resolve({ body: { queue } })

    expect(await screen.findByText('PC-024')).toBeInTheDocument()
    expect(screen.getAllByText('Waiting for consultation')).toHaveLength(1)
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('3 ahead of you')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('Est. waiting time')).toBeInTheDocument()
    expect(screen.getByText('Now serving')).toBeInTheDocument()
    expect(screen.getByText('PC-020')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Queue progress' })).toHaveAttribute(
      'aria-valuenow',
      '50',
    )
    expect(screen.getByText('50% through the queue - please stay nearby.')).toBeInTheDocument()
    expect(screen.getByText('Dr. Sarah Perera - General Practitioner')).toBeInTheDocument()
    expect(screen.getByText('15 October 2026')).toBeInTheDocument()
    expect(screen.getByText('10:00 AM')).toBeInTheDocument()
    expect(
      screen.getByText('This page updates automatically every 15 seconds.'),
    ).toBeInTheDocument()
  })

  it('uses the server serving label and placeholders for empty values', async () => {
    renderPage({
      [QUEUE]: {
        body: {
          queue: {
            ...queue,
            position: null,
            ahead: 0,
            now_serving: null,
            serving_label: 'First in line',
            is_today: false,
          },
        },
      },
    })
    expect(await screen.findByText('First in line')).toBeInTheDocument()
    expect(screen.queryByText('Now serving')).not.toBeInTheDocument()
    expect(screen.getAllByText('–')).toHaveLength(2)
    expect(screen.getByText('0 ahead of you')).toBeInTheDocument()
  })

  it('does not ask a patient booked for another day to stay nearby', async () => {
    renderPage({
      [QUEUE]: {
        body: {
          queue: {
            ...queue,
            estimated_wait_minutes: 0,
            serving_label: 'First in line',
            is_today: false,
            progress_percent: 0,
          },
        },
      },
    })
    expect(
      await screen.findByText('Your queue position updates on the day of your appointment.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/please stay nearby/)).not.toBeInTheDocument()
    expect(screen.getByText('Est. wait on the day')).toBeInTheDocument()
    expect(screen.queryByText('Est. waiting time')).not.toBeInTheDocument()
    expect(screen.getByText('minutes approx.')).toBeInTheDocument()
  })

  it('polls every 15 seconds and stops after unmount', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { fetchMock, unmount } = renderPage({
      [QUEUE]: [{ body: { queue } }, { body: { queue: { ...queue, now_serving: 'PC-021' } } }],
    })
    expect(await screen.findByText('PC-020')).toBeInTheDocument()
    expect(callsTo(fetchMock, QUEUE)).toHaveLength(1)

    await act(() => vi.advanceTimersByTimeAsync(QUEUE_POLL_INTERVAL_MS - 1000))
    expect(callsTo(fetchMock, QUEUE)).toHaveLength(1)

    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(callsTo(fetchMock, QUEUE)).toHaveLength(2)
    expect(await screen.findByText('PC-021')).toBeInTheDocument()

    await act(() => vi.advanceTimersByTimeAsync(QUEUE_POLL_INTERVAL_MS))
    expect(callsTo(fetchMock, QUEUE)).toHaveLength(3)

    unmount()
    await act(() => vi.advanceTimersByTimeAsync(QUEUE_POLL_INTERVAL_MS * 3))
    expect(callsTo(fetchMock, QUEUE)).toHaveLength(3)
  })

  it('keeps the last queue on screen when a refresh fails', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderPage({
      [QUEUE]: [{ body: { queue } }, { status: 503, body: { detail: 'Unavailable.' } }],
    })
    expect(await screen.findByText('PC-024')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(QUEUE_POLL_INTERVAL_MS))
    expect(
      await screen.findByText(
        "We couldn't refresh your queue status just now. Retrying automatically.",
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('PC-024')).toBeInTheDocument()
  })

  it('shows an empty state with a booking link when there is no appointment', async () => {
    renderPage({ [QUEUE]: { status: 404, body: { detail: 'No upcoming appointment found.' } } })
    expect(await screen.findByText('No upcoming appointment found.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Book an appointment' }))
    expect(await navigatedTo()).toBe('/book-appointment')
  })

  it('shows errors and retries', async () => {
    renderPage({
      [QUEUE]: [{ status: 503, body: { detail: 'Unavailable.' } }, { body: { queue } }],
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable.')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('PC-024')).toBeInTheDocument()
  })

  it('dismisses the note and links to the confirmation', async () => {
    renderPage({ [QUEUE]: { body: { queue } } })
    const userEv = userEvent.setup()
    await userEv.click(await screen.findByRole('button', { name: 'Dismiss' }))
    expect(
      screen.queryByText('This page updates automatically every 15 seconds.'),
    ).not.toBeInTheDocument()
    await userEv.click(screen.getByRole('button', { name: 'View confirmation' }))
    expect(await navigatedTo()).toBe('/confirmation')
  })
})
