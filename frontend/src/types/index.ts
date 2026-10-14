// API shapes shared with the FastAPI backend (see the API overview in the README).

export interface User {
  id: string
  email: string
}

export interface Credentials {
  email: string
  password: string
}

export interface Patient {
  first_name: string
  last_name: string
  mobile: string
  email: string
}

export interface Doctor {
  id: string
  name: string
  specialty: string
}

export interface TimeSlot {
  time: string
  label: string
}

export type AppointmentStatus = 'waiting' | 'in_consultation' | 'completed' | 'cancelled'

export interface Appointment {
  id: string
  token: string
  doctor: Doctor
  date: string
  date_label: string
  time: string
  time_label: string
  status: AppointmentStatus
  status_label: string
  created_at: string
}

export interface Queue {
  token: string
  position: number | null
  ahead: number
  total_in_queue: number
  estimated_wait_minutes: number
  now_serving: string | null
  serving_label: 'Now serving' | 'First in line'
  is_today: boolean
  progress_percent: number
  status: AppointmentStatus
  status_label: string
  appointment: Appointment
}

export interface BookingRequest {
  doctor_id: string
  date: string
  time: string
}

export type FieldErrors = Record<string, string>

export interface HealthResponse {
  status: 'ok'
  supabase_configured: boolean
}

export interface UserResponse {
  user: User
}

export interface RegisterResponse {
  user: User | null
  session_started: boolean
  detail?: string
}

export interface PatientResponse {
  patient: Patient | null
}

export interface DoctorsResponse {
  doctors: Doctor[]
  /** The clinic's calendar date (YYYY-MM-DD), decided server-side. */
  today: string
  /** Latest bookable date (YYYY-MM-DD): today + 90 days. */
  max_date: string
}

export interface SlotsResponse {
  date: string
  slots: TimeSlot[]
}

export interface AppointmentResponse {
  appointment: Appointment
}

export interface QueueResponse {
  queue: Queue
}
