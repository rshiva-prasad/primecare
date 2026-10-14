import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { callsTo, deferred, mockFetch } from '../test/fetchMock'
import type { MockReply, MockRoutes } from '../test/fetchMock'
import { appointment, signedIn } from '../test/fixtures'
import { navigatedTo, renderProtectedPage } from '../test/render'
import Confirmation from './Confirmation'

const CURRENT = 'GET /api/appointments/current'

function renderPage(routes: MockRoutes) {
  const fetchMock = mockFetch({ ...signedIn, ...routes })
  renderProtectedPage(<Confirmation />, '/confirmation')
  return fetchMock
}

describe('Confirmation', () => {
  it('shows a loading state, then the booked appointment', async () => {
    const reply = deferred<MockReply>()
    renderPage({ [CURRENT]: () => reply.promise })
    expect(await screen.findByText('Loading your appointment...')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Your appointment' })).toBeInTheDocument()
    reply.resolve({ body: { appointment } })

    expect(
      await screen.findByRole('heading', { name: 'Appointment confirmed' }),
    ).toBeInTheDocument()
    expect(screen.getByText('PC-024')).toBeInTheDocument()
    expect(screen.getByText('Dr. Sarah Perera')).toBeInTheDocument()
    expect(screen.getByText('General Practitioner')).toBeInTheDocument()
    expect(screen.getByText('15 October 2026')).toBeInTheDocument()
    expect(screen.getByText('10:00 AM')).toBeInTheDocument()
    expect(screen.getByText('Waiting for consultation')).toBeInTheDocument()
    expect(screen.queryByText('Back to dashboard')).not.toBeInTheDocument()
  })

  it('links to the queue status', async () => {
    renderPage({ [CURRENT]: { body: { appointment } } })
    await userEvent.click(await screen.findByRole('button', { name: 'View queue status' }))
    expect(await navigatedTo()).toBe('/queue-status')
  })

  it('logs out from the secondary button', async () => {
    const fetchMock = renderPage({ [CURRENT]: { body: { appointment } } })
    await screen.findByText('PC-024')
    const [, secondaryLogout] = screen.getAllByRole('button', { name: 'Log out' })
    await userEvent.click(secondaryLogout)
    expect(await navigatedTo()).toBe('/login')
    expect(callsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(1)
  })

  it('keeps the session and shows an error under the button when logout fails', async () => {
    const fetchMock = renderPage({
      [CURRENT]: { body: { appointment } },
      'POST /api/auth/logout': [{ status: 503, body: { detail: 'Unavailable.' } }, { status: 204 }],
    })
    await screen.findByText('PC-024')
    const userEv = userEvent.setup()
    const [, secondaryLogout] = screen.getAllByRole('button', { name: 'Log out' })
    await userEv.click(secondaryLogout)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "We couldn't log you out. Please check your connection and try again.",
    )
    // Shown next to the button that was used, not in the session bar.
    expect(secondaryLogout.parentElement).toContainElement(screen.getByRole('alert'))
    expect(screen.getByText('PC-024')).toBeInTheDocument()
    expect(screen.queryByTestId('location')).not.toBeInTheDocument()

    await userEv.click(secondaryLogout)
    expect(await navigatedTo()).toBe('/login')
    expect(callsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(2)
  })

  it('shows an empty state when there is no upcoming appointment', async () => {
    renderPage({ [CURRENT]: { status: 404, body: { detail: 'No upcoming appointment found.' } } })
    expect(await screen.findByText('No upcoming appointment found.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Book an appointment' }))
    expect(await navigatedTo()).toBe('/book-appointment')
  })

  it('shows errors and retries', async () => {
    renderPage({
      [CURRENT]: [{ status: 503, body: { detail: 'Unavailable.' } }, { body: { appointment } }],
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable.')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('PC-024')).toBeInTheDocument()
  })
})
