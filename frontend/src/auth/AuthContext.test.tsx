import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, NETWORK_ERROR_MESSAGE, getDoctors, getQueue } from '../lib/api'
import { callsTo, mockFetch } from '../test/fetchMock'
import { signedIn, signedOut, user } from '../test/fixtures'
import AuthProvider from './AuthContext'
import { useAuth } from './useAuth'

const credentials = { email: 'patient@example.com', password: 'synthetic-pass' }

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

function renderAuth() {
  return renderHook(() => useAuth(), { wrapper })
}

describe('AuthProvider', () => {
  it('restores an existing session from /api/auth/me', async () => {
    mockFetch(signedIn)
    const { result } = renderAuth()
    expect(result.current.status).toBe('loading')
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current.user).toEqual(user)
  })

  it('is anonymous when there is no session, without a session-ended message', async () => {
    mockFetch(signedOut)
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    expect(result.current.user).toBeNull()
    expect(result.current.sessionMessage).toBe('')
  })

  it('logs in and out', async () => {
    const fetchMock = mockFetch({
      ...signedOut,
      'POST /api/auth/login': { body: { user } },
      'POST /api/auth/logout': { status: 204 },
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))

    await act(() => result.current.login(credentials))
    expect(result.current).toMatchObject({ status: 'authenticated', user })

    await act(() => result.current.logout())
    expect(result.current).toMatchObject({ status: 'anonymous', user: null })
    expect(callsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(1)
  })

  it('propagates login failures and stays anonymous', async () => {
    mockFetch({
      ...signedOut,
      'POST /api/auth/login': { status: 401, body: { detail: 'Invalid email or password.' } },
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    await expect(result.current.login(credentials)).rejects.toBeInstanceOf(ApiError)
    expect(result.current.status).toBe('anonymous')
  })

  it('starts a session when registration signs the user in', async () => {
    mockFetch({
      ...signedOut,
      'POST /api/auth/register': { status: 201, body: { user, session_started: true } },
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    let response
    await act(async () => {
      response = await result.current.register(credentials)
    })
    expect(response).toEqual({ user, session_started: true })
    expect(result.current.status).toBe('authenticated')
  })

  it('stays anonymous when registration needs email confirmation', async () => {
    const pending = { user: null, session_started: false, detail: 'Check your email.' }
    mockFetch({ ...signedOut, 'POST /api/auth/register': { status: 202, body: pending } })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    await act(async () => {
      await expect(result.current.register(credentials)).resolves.toEqual(pending)
    })
    expect(result.current.status).toBe('anonymous')
  })

  it('keeps the session when the logout request cannot reach the server', async () => {
    mockFetch(signedIn)
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await act(async () => {
      await expect(result.current.logout()).rejects.toMatchObject({
        status: 0,
        detail: NETWORK_ERROR_MESSAGE,
      })
    })
    expect(result.current).toMatchObject({ status: 'authenticated', user })
  })

  it('keeps the session when the logout request fails upstream (502)', async () => {
    mockFetch({ ...signedIn, 'POST /api/auth/logout': { status: 502, raw: 'Bad gateway' } })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    await act(async () => {
      await expect(result.current.logout()).rejects.toMatchObject({ status: 502 })
    })
    expect(result.current).toMatchObject({ status: 'authenticated', user })
  })

  it('ends the session with the server message when any protected call returns 401', async () => {
    const detail = 'Your session has expired. Please log in again.'
    mockFetch({
      ...signedIn,
      'GET /api/doctors': { status: 401, body: { detail } },
      'GET /api/appointments/current/queue': { status: 401, body: { detail: 'Second 401.' } },
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    await act(async () => {
      await expect(getDoctors()).rejects.toBeInstanceOf(ApiError)
    })
    expect(result.current).toMatchObject({
      status: 'anonymous',
      user: null,
      sessionMessage: detail,
    })

    // A further 401 once already signed out keeps the first message.
    await act(async () => {
      await expect(getQueue()).rejects.toBeInstanceOf(ApiError)
    })
    expect(result.current.sessionMessage).toBe(detail)

    act(() => result.current.clearSessionMessage())
    expect(result.current.sessionMessage).toBe('')
    const cleared = result.current
    act(() => result.current.clearSessionMessage())
    expect(result.current).toBe(cleared)
  })

  it('clears the session message on the next login', async () => {
    mockFetch({
      ...signedIn,
      'GET /api/doctors': { status: 401, body: { detail: 'Your session has expired.' } },
      'POST /api/auth/login': { body: { user } },
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    await act(async () => {
      await expect(getDoctors()).rejects.toBeInstanceOf(ApiError)
    })
    expect(result.current.sessionMessage).toBe('Your session has expired.')
    await act(() => result.current.login(credentials))
    expect(result.current).toMatchObject({ status: 'authenticated', sessionMessage: '' })
  })

  it('renders its children', async () => {
    mockFetch(signedOut)
    render(<AuthProvider>child content</AuthProvider>)
    expect(screen.getByText('child content')).toBeInTheDocument()
    await waitFor(() => expect(fetch).toHaveBeenCalled())
  })
})

describe('useAuth', () => {
  it('throws outside an AuthProvider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => useAuth())).toThrow('useAuth must be used inside <AuthProvider>.')
  })
})
