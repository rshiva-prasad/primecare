import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { Route } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProtectedRoute from '../auth/ProtectedRoute'
import { NETWORK_ERROR_MESSAGE, getDoctors } from '../lib/api'
import { bodyOf, callsTo, deferred, mockFetch } from '../test/fetchMock'
import type { MockReply, MockRoutes } from '../test/fetchMock'
import {
  appointment,
  hasUpcomingAppointment,
  noUpcomingAppointment,
  signedIn,
  signedOut,
  user,
} from '../test/fixtures'
import { navigatedTo, renderRoutes } from '../test/render'
import Login from './Login'

function renderLogin(routes: MockRoutes = {}) {
  const fetchMock = mockFetch({ ...signedOut, ...noUpcomingAppointment, ...routes })
  renderRoutes(<Route path="/login" element={<Login />} />, '/login')
  return fetchMock
}

async function fillLogin(email: string, password: string) {
  const userEv = userEvent.setup()
  if (email) await userEv.type(await screen.findByLabelText('Email'), email)
  if (password) await userEv.type(screen.getByLabelText('Password'), password)
  return userEv
}

/** A protected page whose first API call finds the session has ended. */
function ExpiringPage() {
  useEffect(() => {
    getDoctors().catch(() => {})
  }, [])
  return <p>Protected page</p>
}

describe('Login', () => {
  it('renders the A2 card without demo credentials', async () => {
    renderLogin()
    expect(await screen.findByRole('heading', { name: 'PrimeCare Clinic' })).toBeInTheDocument()
    expect(screen.getByText('Digital Queue Management')).toBeInTheDocument()
    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Confirm password')).not.toBeInTheDocument()
    // A first visit (no session yet) is not a "session ended" notice.
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('explains why a session ended mid-flow until the next submit', async () => {
    const detail = 'Your session has expired. Please log in again.'
    mockFetch({
      ...signedIn,
      'GET /api/doctors': { status: 401, body: { detail } },
      'POST /api/auth/login': { status: 401, body: { detail: 'Invalid email or password.' } },
    })
    renderRoutes(
      <>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/book-appointment" element={<ExpiringPage />} />
        </Route>
      </>,
      '/book-appointment',
    )

    expect(await screen.findByText(detail)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(detail)
    expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.queryByText('Protected page')).not.toBeInTheDocument()

    const userEv = await fillLogin('patient@example.com', 'wrong-pass')
    await userEv.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
    expect(screen.queryByText(detail)).not.toBeInTheDocument()
  })

  it('validates the fields before calling the API', async () => {
    const fetchMock = renderLogin()
    const userEv = userEvent.setup()
    await userEv.click(await screen.findByRole('button', { name: 'Log in' }))
    expect(screen.getByText('Email is required.')).toBeInTheDocument()
    expect(screen.getByText('Password is required.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')

    await userEv.type(screen.getByLabelText('Email'), 'not-an-email')
    await userEv.click(screen.getByRole('button', { name: 'Log in' }))
    expect(screen.getByText('Please enter a valid email address.')).toBeInTheDocument()
    expect(callsTo(fetchMock, 'POST /api/auth/login')).toHaveLength(0)
  })

  it('logs in and goes to patient details when there is no upcoming appointment', async () => {
    const fetchMock = renderLogin({ 'POST /api/auth/login': { body: { user } } })
    const userEv = await fillLogin('  patient@example.com ', 'synthetic-pass')
    await userEv.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await navigatedTo()).toBe('/patient-details')
    expect(bodyOf(callsTo(fetchMock, 'POST /api/auth/login')[0])).toEqual({
      email: 'patient@example.com',
      password: 'synthetic-pass',
    })
  })

  it('submits with the Enter key and shows a loading button', async () => {
    const reply = deferred<MockReply>()
    const fetchMock = renderLogin({ 'POST /api/auth/login': () => reply.promise })
    const userEv = await fillLogin('patient@example.com', 'synthetic-pass{Enter}')
    const button = screen.getByRole('button', { name: 'Log in' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEv.keyboard('{Enter}')
    reply.resolve({ body: { user } })
    expect(await navigatedTo()).toBe('/patient-details')
    expect(callsTo(fetchMock, 'POST /api/auth/login')).toHaveLength(1)
  })

  it('shows server errors in the form error box', async () => {
    renderLogin({
      'POST /api/auth/login': { status: 401, body: { detail: 'Invalid email or password.' } },
    })
    const userEv = await fillLogin('patient@example.com', 'wrong-pass')
    await userEv.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled()
  })

  it('shows server field errors under the inputs', async () => {
    renderLogin({
      'POST /api/auth/login': {
        status: 422,
        body: {
          detail: 'Please correct the highlighted fields.',
          fields: { email: 'Enter a valid email address.', password: 'Password is too short.' },
        },
      },
    })
    const userEv = await fillLogin('patient@example.com', 'x')
    await userEv.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(screen.getByText('Password is too short.')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Please correct the highlighted fields.')
  })

  it('shows a friendly message when the server is unreachable', async () => {
    renderLogin()
    const userEv = await fillLogin('patient@example.com', 'synthetic-pass')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await userEv.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(NETWORK_ERROR_MESSAGE)
  })

  it('redirects users who are already signed in', async () => {
    mockFetch({ ...signedIn, ...noUpcomingAppointment })
    renderRoutes(<Route path="/login" element={<Login />} />, '/login')
    expect(await navigatedTo()).toBe('/patient-details')
  })

  describe('where a signed-in patient lands', () => {
    it('takes a returning patient with an upcoming appointment straight to queue status', async () => {
      const fetchMock = renderLogin({
        ...hasUpcomingAppointment,
        'POST /api/auth/login': { body: { user } },
      })
      const userEv = await fillLogin('patient@example.com', 'synthetic-pass')
      await userEv.click(screen.getByRole('button', { name: 'Log in' }))
      expect(await navigatedTo()).toBe('/queue-status')
      expect(callsTo(fetchMock, 'GET /api/appointments/current')).toHaveLength(1)
    })

    it('sends an already signed-in patient with an appointment to queue status', async () => {
      mockFetch({ ...signedIn, ...hasUpcomingAppointment })
      renderRoutes(<Route path="/login" element={<Login />} />, '/login')
      expect(await navigatedTo()).toBe('/queue-status')
    })

    it('shows a loading state while it looks up the appointment', async () => {
      const reply = deferred<MockReply>()
      mockFetch({ ...signedIn, 'GET /api/appointments/current': () => reply.promise })
      renderRoutes(<Route path="/login" element={<Login />} />, '/login')
      expect(await screen.findByText('Opening your appointment...')).toBeInTheDocument()
      reply.resolve({ body: { appointment } })
      expect(await navigatedTo()).toBe('/queue-status')
    })

    it('falls back to patient details when the lookup fails', async () => {
      mockFetch({
        ...signedIn,
        'GET /api/appointments/current': { status: 503, body: { detail: 'Unavailable.' } },
      })
      renderRoutes(<Route path="/login" element={<Login />} />, '/login')
      expect(await navigatedTo()).toBe('/patient-details')
    })

    it('returns to the login form if the session ends during the lookup', async () => {
      const detail = 'Your session has expired. Please log in again.'
      mockFetch({ ...signedIn, 'GET /api/appointments/current': { status: 401, body: { detail } } })
      renderRoutes(<Route path="/login" element={<Login />} />, '/login')
      expect(await screen.findByText(detail)).toBeInTheDocument()
      expect(screen.getByRole('status')).toHaveTextContent(detail)
      expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
      expect(screen.queryByTestId('location')).not.toBeInTheDocument()
    })
  })

  describe('create account mode', () => {
    async function openRegister(routes: MockRoutes = {}) {
      const fetchMock = renderLogin(routes)
      const userEv = userEvent.setup()
      await userEv.click(await screen.findByRole('button', { name: 'Create an account' }))
      return { fetchMock, userEv }
    }

    it('adds a confirm password field and validates it', async () => {
      const { fetchMock, userEv } = await openRegister()
      expect(screen.getByText('Create your patient account')).toBeInTheDocument()
      await userEv.type(screen.getByLabelText('Email'), 'new@example.com')
      await userEv.type(screen.getByLabelText('Password'), 'short')
      await userEv.click(screen.getByRole('button', { name: 'Create account' }))
      expect(screen.getByText('Password must be at least 8 characters.')).toBeInTheDocument()
      expect(screen.getByText('Please confirm your password.')).toBeInTheDocument()

      await userEv.clear(screen.getByLabelText('Password'))
      await userEv.type(screen.getByLabelText('Password'), 'long-enough-1')
      await userEv.type(screen.getByLabelText('Confirm password'), 'long-enough-2')
      await userEv.click(screen.getByRole('button', { name: 'Create account' }))
      expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
      expect(callsTo(fetchMock, 'POST /api/auth/register')).toHaveLength(0)
    })

    it('creates an account and continues to patient details', async () => {
      const { fetchMock, userEv } = await openRegister({
        'POST /api/auth/register': { status: 201, body: { user, session_started: true } },
      })
      await userEv.type(screen.getByLabelText('Email'), 'new@example.com')
      await userEv.type(screen.getByLabelText('Password'), 'long-enough-1')
      await userEv.type(screen.getByLabelText('Confirm password'), 'long-enough-1')
      await userEv.click(screen.getByRole('button', { name: 'Create account' }))
      expect(await navigatedTo()).toBe('/patient-details')
      expect(bodyOf(callsTo(fetchMock, 'POST /api/auth/register')[0])).toEqual({
        email: 'new@example.com',
        password: 'long-enough-1',
      })
    })

    it('shows the confirmation message and switches to login mode on 202', async () => {
      const detail = 'Check your email to confirm your account, then log in.'
      const { userEv } = await openRegister({
        'POST /api/auth/register': {
          status: 202,
          body: { user: null, session_started: false, detail },
        },
      })
      await userEv.type(screen.getByLabelText('Email'), 'new@example.com')
      await userEv.type(screen.getByLabelText('Password'), 'long-enough-1')
      await userEv.type(screen.getByLabelText('Confirm password'), 'long-enough-1')
      await userEv.click(screen.getByRole('button', { name: 'Create account' }))

      expect(await screen.findByRole('status')).toHaveTextContent(detail)
      expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
      expect(screen.queryByLabelText('Confirm password')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Email')).toHaveValue('new@example.com')
      expect(screen.getByLabelText('Password')).toHaveValue('')
    })

    it('falls back to a default confirmation message', async () => {
      const { userEv } = await openRegister({
        'POST /api/auth/register': { status: 202, body: { user: null, session_started: false } },
      })
      await userEv.type(screen.getByLabelText('Email'), 'new@example.com')
      await userEv.type(screen.getByLabelText('Password'), 'long-enough-1')
      await userEv.type(screen.getByLabelText('Confirm password'), 'long-enough-1')
      await userEv.click(screen.getByRole('button', { name: 'Create account' }))
      expect(await screen.findByRole('status')).toHaveTextContent(
        'Check your email to confirm your account, then log in.',
      )
    })

    it('shows registration errors and can switch back to login', async () => {
      const detail =
        'Unable to create an account with those details. If you already have an account, please log in.'
      const { userEv } = await openRegister({
        'POST /api/auth/register': { status: 400, body: { detail } },
      })
      await userEv.type(screen.getByLabelText('Email'), 'new@example.com')
      await userEv.type(screen.getByLabelText('Password'), 'long-enough-1')
      await userEv.type(screen.getByLabelText('Confirm password'), 'long-enough-1')
      await userEv.click(screen.getByRole('button', { name: 'Create account' }))
      expect(await screen.findByRole('alert')).toHaveTextContent(detail)

      await userEv.click(screen.getByRole('button', { name: 'Log in' }))
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Confirm password')).not.toBeInTheDocument()
      expect(screen.getByText('Digital Queue Management')).toBeInTheDocument()
    })
  })
})
