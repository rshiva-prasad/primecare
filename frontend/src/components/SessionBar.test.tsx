import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { callsTo, mockFetch } from '../test/fetchMock'
import { signedIn, signedOut, user } from '../test/fixtures'
import { navigatedTo, renderProtectedPage, renderRoutes } from '../test/render'
import SessionBar from './SessionBar'

describe('SessionBar', () => {
  it('shows the signed-in email and logs out to /login', async () => {
    const fetchMock = mockFetch(signedIn)
    renderProtectedPage(<SessionBar />, '/confirmation')

    expect(await screen.findByText(user.email)).toBeInTheDocument()
    expect(screen.getByText(/Signed in as/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
    expect(await navigatedTo()).toBe('/login')
    expect(callsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(1)
  })

  it('keeps the session and shows an error when logout fails, then lets the user retry', async () => {
    const fetchMock = mockFetch({
      ...signedIn,
      'POST /api/auth/logout': [{ status: 502, raw: 'Bad gateway' }, { status: 204 }],
    })
    renderProtectedPage(<SessionBar />, '/confirmation')
    const userEv = userEvent.setup()

    await userEv.click(await screen.findByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "We couldn't log you out. Please check your connection and try again.",
    )
    expect(screen.getByText(user.email)).toBeInTheDocument()
    expect(screen.queryByTestId('location')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log out' })).toBeEnabled()

    await userEv.click(screen.getByRole('button', { name: 'Log out' }))
    expect(await navigatedTo()).toBe('/login')
    expect(callsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(2)
  })

  it('shows the logout error when the server is unreachable', async () => {
    mockFetch(signedIn)
    renderProtectedPage(<SessionBar />, '/confirmation')
    await screen.findByText(user.email)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("We couldn't log you out.")
    expect(screen.getByText(user.email)).toBeInTheDocument()
  })

  it('renders nothing without a user', async () => {
    const fetchMock = mockFetch(signedOut)
    renderRoutes(<Route path="/" element={<SessionBar />} />)
    await expect.poll(() => fetchMock.mock.calls.length).toBe(1)
    expect(screen.queryByText(/Signed in as/)).not.toBeInTheDocument()
  })
})
