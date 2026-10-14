// Synthetic test data only.
import type { Appointment, Doctor, Patient, Queue, TimeSlot, User } from '../types'
import type { MockRoutes } from './fetchMock'

export const user: User = {
  id: '00000000-0000-4000-8000-000000000001',
  email: 'patient@example.com',
}

export const patient: Patient = {
  first_name: 'Jane',
  last_name: 'Citizen',
  mobile: '0400 000 000',
  email: 'jane.citizen@example.com',
}

export const doctors: Doctor[] = [
  { id: 'dr-perera', name: 'Dr. Sarah Perera', specialty: 'General Practitioner' },
  { id: 'dr-sharma', name: 'Dr. Anita Sharma', specialty: 'Dermatologist' },
]

/** GET /api/doctors body: the clinic's date and the latest bookable date (today + 90 days). */
export const doctorsBody = { doctors, today: '2026-10-14', max_date: '2027-01-12' }

export const slots: TimeSlot[] = [
  { time: '09:00', label: '09:00 AM' },
  { time: '14:30', label: '02:30 PM' },
]

export const appointment: Appointment = {
  id: '00000000-0000-4000-8000-000000000099',
  token: 'PC-024',
  doctor: doctors[0],
  date: '2026-10-15',
  date_label: '15 October 2026',
  time: '10:00',
  time_label: '10:00 AM',
  status: 'waiting',
  status_label: 'Waiting for consultation',
  created_at: '2026-10-13T00:00:00Z',
}

export const queue: Queue = {
  token: 'PC-024',
  position: 4,
  ahead: 3,
  total_in_queue: 8,
  estimated_wait_minutes: 30,
  now_serving: 'PC-020',
  serving_label: 'Now serving',
  is_today: true,
  progress_percent: 50,
  status: 'waiting',
  status_label: 'Waiting for consultation',
  appointment,
}

export const signedIn: MockRoutes = {
  'GET /api/auth/me': { body: { user } },
  'POST /api/auth/logout': { status: 204 },
}

export const signedOut: MockRoutes = {
  'GET /api/auth/me': { status: 401, body: { detail: 'Please log in to continue.' } },
}

/** The signed-in patient has an upcoming appointment. */
export const hasUpcomingAppointment: MockRoutes = {
  'GET /api/appointments/current': { body: { appointment } },
}

/** The signed-in patient has no upcoming appointment. */
export const noUpcomingAppointment: MockRoutes = {
  'GET /api/appointments/current': {
    status: 404,
    body: { detail: 'No upcoming appointment found.' },
  },
}
