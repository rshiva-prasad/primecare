import { describe, expect, it, vi } from 'vitest'
import { appointment, doctorsBody, patient, queue, slots, user } from '../test/fixtures'
import { bodyOf, callsTo, mockFetch } from '../test/fetchMock'
import {
  ApiError,
  GENERIC_ERROR_MESSAGE,
  NETWORK_ERROR_MESSAGE,
  bookAppointment,
  getCurrentAppointment,
  getDoctors,
  getHealth,
  getMe,
  getPatient,
  getQueue,
  getSlots,
  login,
  logout,
  onUnauthorized,
  parseApiError,
  register,
  savePatient,
  toApiError,
} from './api'

const credentials = { email: 'patient@example.com', password: 'synthetic-pass' }

async function rejectionOf(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError)
    return error as ApiError
  }
  throw new Error('Expected the promise to reject')
}

describe('ApiError helpers', () => {
  it('exposes status, detail and fields', () => {
    const error = new ApiError(422, 'Fix it.', { email: 'Bad email.' })
    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('ApiError')
    expect(error.message).toBe('Fix it.')
    expect(error.status).toBe(422)
    expect(error.fields).toEqual({ email: 'Bad email.' })
    expect(new ApiError(500, 'x').fields).toEqual({})
  })

  it('toApiError passes ApiErrors through and wraps anything else', () => {
    const original = new ApiError(400, 'Nope.')
    expect(toApiError(original)).toBe(original)
    const wrapped = toApiError(new TypeError('boom'))
    expect(wrapped.status).toBe(0)
    expect(wrapped.detail).toBe(GENERIC_ERROR_MESSAGE)
  })

  it('parseApiError keeps only well-formed detail and string fields', () => {
    const error = parseApiError(422, {
      detail: 'Please correct the highlighted fields.',
      fields: { email: 'Enter a valid email.', password: 42 },
    })
    expect(error.detail).toBe('Please correct the highlighted fields.')
    expect(error.fields).toEqual({ email: 'Enter a valid email.' })
  })

  it.each([
    ['a non-object body', 'oops'],
    ['an array body', ['detail']],
    ['a missing body', undefined],
    ['a non-string detail', { detail: [{ msg: 'x' }] }],
    ['a blank detail', { detail: '   ' }],
  ])('parseApiError falls back to a generic message for %s', (_label, body) => {
    const error = parseApiError(500, body)
    expect(error.status).toBe(500)
    expect(error.detail).toBe(GENERIC_ERROR_MESSAGE)
    expect(error.fields).toEqual({})
  })
})

describe('request handling', () => {
  it('sends same-origin GET requests without a body', async () => {
    const fetchMock = mockFetch({
      'GET /api/health': { body: { status: 'ok', supabase_configured: false } },
    })
    await expect(getHealth()).resolves.toEqual({ status: 'ok', supabase_configured: false })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/health')
    expect(init).toMatchObject({ method: 'GET', credentials: 'same-origin', body: undefined })
    expect(init?.headers).toEqual({ Accept: 'application/json' })
  })

  it('sends JSON bodies with a JSON content type', async () => {
    const fetchMock = mockFetch({ 'POST /api/auth/login': { body: { user } } })
    await expect(login(credentials)).resolves.toEqual(user)
    const call = fetchMock.mock.calls[0]
    expect(call[1]?.headers).toEqual({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    })
    expect(bodyOf(call)).toEqual(credentials)
  })

  it('logout posts an empty JSON object and resolves on 204', async () => {
    const fetchMock = mockFetch({ 'POST /api/auth/logout': { status: 204 } })
    await expect(logout()).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][1]?.body).toBe('{}')
  })

  it('maps network failures to a friendly error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await rejectionOf(getDoctors())
    expect(error.status).toBe(0)
    expect(error.detail).toBe(NETWORK_ERROR_MESSAGE)
  })

  it('parses JSON error bodies', async () => {
    mockFetch({
      'POST /api/appointments': {
        status: 409,
        body: { detail: 'That time slot has just been booked. Please choose another.' },
      },
    })
    const error = await rejectionOf(
      bookAppointment({ doctor_id: 'dr-perera', date: '2026-10-15', time: '10:00' }),
    )
    expect(error.status).toBe(409)
    expect(error.detail).toBe('That time slot has just been booked. Please choose another.')
  })

  it('uses a generic message for non-JSON error bodies', async () => {
    mockFetch({ 'GET /api/doctors': { status: 502, raw: '<html>Bad gateway</html>' } })
    const error = await rejectionOf(getDoctors())
    expect(error.status).toBe(502)
    expect(error.detail).toBe(GENERIC_ERROR_MESSAGE)
  })

  it('rejects a successful response that is not JSON', async () => {
    mockFetch({ 'GET /api/doctors': { status: 200, raw: '<!doctype html>' } })
    const error = await rejectionOf(getDoctors())
    expect(error.status).toBe(200)
    expect(error.detail).toBe(GENERIC_ERROR_MESSAGE)
  })
})

describe('401 notifications', () => {
  const expired = {
    status: 401,
    body: { detail: 'Your session has expired. Please log in again.' },
  }

  it('notifies subscribers when a protected call returns 401, until unsubscribed', async () => {
    mockFetch({ 'GET /api/auth/me': expired })
    const listener = vi.fn()
    const unsubscribe = onUnauthorized(listener)

    const error = await rejectionOf(getMe())
    expect(error.detail).toBe('Your session has expired. Please log in again.')
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith('Your session has expired. Please log in again.')

    unsubscribe()
    await rejectionOf(getMe())
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('does not treat login or register 401s as an ended session', async () => {
    mockFetch({ 'POST /api/auth/login': expired, 'POST /api/auth/register': expired })
    const listener = vi.fn()
    const unsubscribe = onUnauthorized(listener)
    await rejectionOf(login(credentials))
    await rejectionOf(register(credentials))
    expect(listener).not.toHaveBeenCalled()
    unsubscribe()
  })

  it('does not notify for other error statuses', async () => {
    mockFetch({ 'GET /api/doctors': { status: 503, body: { detail: 'Unavailable.' } } })
    const listener = vi.fn()
    const unsubscribe = onUnauthorized(listener)
    await rejectionOf(getDoctors())
    expect(listener).not.toHaveBeenCalled()
    unsubscribe()
  })
})

describe('endpoints', () => {
  it('register returns the full response body', async () => {
    const pending = {
      user: null,
      session_started: false,
      detail: 'Check your email to confirm your account, then log in.',
    }
    const fetchMock = mockFetch({ 'POST /api/auth/register': { status: 202, body: pending } })
    await expect(register(credentials)).resolves.toEqual(pending)
    expect(bodyOf(callsTo(fetchMock, 'POST /api/auth/register')[0])).toEqual(credentials)
  })

  it('unwraps the current user', async () => {
    mockFetch({ 'GET /api/auth/me': { body: { user } } })
    await expect(getMe()).resolves.toEqual(user)
  })

  it('reads and saves the patient record', async () => {
    const fetchMock = mockFetch({
      'GET /api/patients/me': { body: { patient: null } },
      'PUT /api/patients/me': { body: { patient } },
    })
    await expect(getPatient()).resolves.toBeNull()
    await expect(savePatient(patient)).resolves.toEqual(patient)
    expect(bodyOf(callsTo(fetchMock, 'PUT /api/patients/me')[0])).toEqual(patient)
  })

  it('lists doctors with the clinic date range', async () => {
    mockFetch({ 'GET /api/doctors': { body: doctorsBody } })
    await expect(getDoctors()).resolves.toEqual({
      doctors: doctorsBody.doctors,
      today: '2026-10-14',
      max_date: '2027-01-12',
    })
  })

  it('encodes the doctor id and date when fetching slots', async () => {
    const fetchMock = mockFetch({
      'GET /api/doctors/dr%20odd%2Fid/slots': { body: { date: '2026-10-15', slots } },
    })
    await expect(getSlots('dr odd/id', '2026-10-15')).resolves.toEqual(slots)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/doctors/dr%20odd%2Fid/slots?date=2026-10-15')
  })

  it('books an appointment', async () => {
    const booking = { doctor_id: 'dr-perera', date: '2026-10-15', time: '10:00' }
    const fetchMock = mockFetch({
      'POST /api/appointments': { status: 201, body: { appointment } },
    })
    await expect(bookAppointment(booking)).resolves.toEqual(appointment)
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual(booking)
  })

  it('fetches the current appointment and queue', async () => {
    mockFetch({
      'GET /api/appointments/current': { body: { appointment } },
      'GET /api/appointments/current/queue': { body: { queue } },
    })
    await expect(getCurrentAppointment()).resolves.toEqual(appointment)
    await expect(getQueue()).resolves.toEqual(queue)
  })
})
