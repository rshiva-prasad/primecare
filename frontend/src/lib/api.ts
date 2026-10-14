import type {
  Appointment,
  AppointmentResponse,
  BookingRequest,
  Credentials,
  DoctorsResponse,
  FieldErrors,
  HealthResponse,
  Patient,
  PatientResponse,
  Queue,
  QueueResponse,
  RegisterResponse,
  SlotsResponse,
  TimeSlot,
  User,
  UserResponse,
} from '../types'

export const NETWORK_ERROR_MESSAGE =
  'Unable to reach PrimeCare right now. Please check your connection and try again.'
export const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.'

export class ApiError extends Error {
  readonly status: number
  readonly detail: string
  readonly fields: FieldErrors

  constructor(status: number, detail: string, fields: FieldErrors = {}) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.fields = fields
  }
}

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(0, GENERIC_ERROR_MESSAGE)
}

/** Receives the server's 401 detail, e.g. "Your session has expired. Please log in again." */
type Listener = (detail: string) => void

const unauthorizedListeners = new Set<Listener>()

/** Subscribe to "session ended" (401) notifications. Returns an unsubscribe function. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener)
  return () => {
    unauthorizedListeners.delete(listener)
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Builds an ApiError from an error response body, never trusting its shape. */
export function parseApiError(status: number, body: unknown): ApiError {
  if (!isRecord(body)) {
    return new ApiError(status, GENERIC_ERROR_MESSAGE)
  }
  const detail =
    typeof body.detail === 'string' && body.detail.trim() ? body.detail : GENERIC_ERROR_MESSAGE
  const fields: FieldErrors = {}
  if (isRecord(body.fields)) {
    for (const [name, message] of Object.entries(body.fields)) {
      if (typeof message === 'string') {
        fields[name] = message
      }
    }
  }
  return new ApiError(status, detail, fields)
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return JSON.parse(await response.text())
  } catch {
    return undefined
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT'
  body?: unknown
  /** Login/register 401s are credential failures, not an ended session. */
  notifyUnauthorized?: boolean
}

async function request<T>(
  path: string,
  { method = 'GET', body, notifyUnauthorized = true }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, NETWORK_ERROR_MESSAGE)
  }

  if (response.status === 204) {
    return undefined as T
  }
  const data = await readJson(response)
  if (!response.ok) {
    const error = parseApiError(response.status, data)
    if (response.status === 401 && notifyUnauthorized) {
      unauthorizedListeners.forEach((listener) => listener(error.detail))
    }
    throw error
  }
  if (data === undefined) {
    throw new ApiError(response.status, GENERIC_ERROR_MESSAGE)
  }
  return data as T
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export function register(credentials: Credentials): Promise<RegisterResponse> {
  return request<RegisterResponse>('/auth/register', {
    method: 'POST',
    body: credentials,
    notifyUnauthorized: false,
  })
}

export async function login(credentials: Credentials): Promise<User> {
  const data = await request<UserResponse>('/auth/login', {
    method: 'POST',
    body: credentials,
    notifyUnauthorized: false,
  })
  return data.user
}

export async function logout(): Promise<void> {
  await request<void>('/auth/logout', { method: 'POST', body: {} })
}

export async function getMe(): Promise<User> {
  const data = await request<UserResponse>('/auth/me')
  return data.user
}

export async function getPatient(): Promise<Patient | null> {
  const data = await request<PatientResponse>('/patients/me')
  return data.patient
}

export async function savePatient(patient: Patient): Promise<Patient> {
  const data = await request<{ patient: Patient }>('/patients/me', { method: 'PUT', body: patient })
  return data.patient
}

/** Doctors plus the clinic's date range for booking (`today`..`max_date`). */
export function getDoctors(): Promise<DoctorsResponse> {
  return request<DoctorsResponse>('/doctors')
}

export async function getSlots(doctorId: string, date: string): Promise<TimeSlot[]> {
  const query = new URLSearchParams({ date })
  const data = await request<SlotsResponse>(
    `/doctors/${encodeURIComponent(doctorId)}/slots?${query.toString()}`,
  )
  return data.slots
}

export async function bookAppointment(booking: BookingRequest): Promise<Appointment> {
  const data = await request<AppointmentResponse>('/appointments', {
    method: 'POST',
    body: booking,
  })
  return data.appointment
}

export async function getCurrentAppointment(): Promise<Appointment> {
  const data = await request<AppointmentResponse>('/appointments/current')
  return data.appointment
}

export async function getQueue(): Promise<Queue> {
  const data = await request<QueueResponse>('/appointments/current/queue')
  return data.queue
}
