import ErrorState from '../components/ErrorState'
import FieldError from '../components/FieldError'
import FormSection from '../components/FormSection'
import LoadingState from '../components/LoadingState'
import SessionBar from '../components/SessionBar'
import IconButton from '../components/ui/IconButton'
import { useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApiData } from '../hooks/useApiData'
import {
  bookAppointment,
  getCurrentAppointment,
  getDoctors,
  getSlots,
  toApiError,
} from '../lib/api'
import { describeError, hasErrors, pickFieldErrors } from '../lib/forms'
import type { Appointment, Doctor, DoctorsResponse, TimeSlot } from '../types'

type BookingField = 'doctor_id' | 'date' | 'time'
type BookingErrors = Record<BookingField, string>

type SlotsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; slots: TimeSlot[] }

const BOOKING_FIELDS: readonly BookingField[] = ['doctor_id', 'date', 'time']
const NO_ERRORS: BookingErrors = { doctor_id: '', date: '', time: '' }
/** The server's 400 detail when the patient already has an upcoming appointment. */
const ALREADY_BOOKED_MESSAGE = 'You already have an upcoming appointment.'

type BookingPage = DoctorsResponse & { current: Appointment | null }

/** Doctors and the clinic's bookable dates, plus any upcoming appointment (404 means none). */
async function loadBookingPage(): Promise<BookingPage> {
  const [doctorsData, current] = await Promise.all([
    getDoctors(),
    getCurrentAppointment().catch((error: unknown) => {
      if (toApiError(error).status === 404) return null
      throw error
    }),
  ])
  return { ...doctorsData, current }
}

const fieldClass =
  'mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500'

function slotPlaceholder(slots: SlotsState): string {
  switch (slots.status) {
    case 'idle':
      return 'Select a doctor and date first'
    case 'loading':
      return 'Loading time slots...'
    case 'error':
      return 'Time slots unavailable'
    case 'success':
      return slots.slots.length ? 'Select a time slot' : 'No time slots available for this date'
  }
}

interface BookingFormProps {
  doctors: Doctor[]
  /** The clinic's date and the latest bookable date, from the server (never the browser clock). */
  today: string
  maxDate: string
  onAlreadyBooked: () => void
}

function BookingForm({ doctors, today, maxDate, onAlreadyBooked }: BookingFormProps) {
  const navigate = useNavigate()
  const [doctorId, setDoctorId] = useState('')
  const [date, setDate] = useState(today)
  const [time, setTime] = useState('')
  const [slots, setSlots] = useState<SlotsState>({ status: 'idle' })
  const [errors, setErrors] = useState<BookingErrors>(NO_ERRORS)
  const [formError, setFormError] = useState('')
  const [booking, setBooking] = useState(false)
  // Only the latest slots request may update state, so quick changes never show stale slots.
  const slotsRequest = useRef(0)

  const loadSlots = (nextDoctorId: string, nextDate: string) => {
    const request = ++slotsRequest.current
    if (!nextDoctorId || !nextDate) {
      setSlots({ status: 'idle' })
      return
    }
    setSlots({ status: 'loading' })
    getSlots(nextDoctorId, nextDate).then(
      (result) => {
        if (request === slotsRequest.current) setSlots({ status: 'success', slots: result })
      },
      (error: unknown) => {
        if (request === slotsRequest.current) {
          setSlots({ status: 'error', message: toApiError(error).detail })
        }
      },
    )
  }

  const handleDoctorChange = (e: ChangeEvent<HTMLSelectElement>) => {
    setDoctorId(e.target.value)
    setTime('')
    setFormError('')
    loadSlots(e.target.value, date)
  }

  const handleDateChange = (e: ChangeEvent<HTMLInputElement>) => {
    setDate(e.target.value)
    setTime('')
    setFormError('')
    loadSlots(doctorId, e.target.value)
  }

  const validate = (): BookingErrors => {
    let dateError = ''
    if (!date) {
      dateError = 'Please select an appointment date.'
    } else if (date < today) {
      dateError = 'Appointment date cannot be in the past.'
    } else if (date > maxDate) {
      dateError = 'Appointments can only be booked up to 90 days ahead.'
    }
    return {
      doctor_id: doctorId ? '' : 'Please select a doctor.',
      date: dateError,
      time: time ? '' : 'Please select a consultation time.',
    }
  }

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (booking) {
      return
    }
    const nextErrors = validate()
    setErrors(nextErrors)
    setFormError('')
    if (hasErrors(nextErrors)) {
      return
    }

    setBooking(true)
    try {
      await bookAppointment({ doctor_id: doctorId, date, time })
      navigate('/queue-status')
    } catch (error) {
      const apiError = toApiError(error)
      if (apiError.status === 412) {
        navigate('/patient-details', { state: { notice: apiError.detail } })
        return
      }
      if (apiError.status === 400 && apiError.detail === ALREADY_BOOKED_MESSAGE) {
        onAlreadyBooked()
        return
      }
      setErrors(pickFieldErrors(apiError.fields, BOOKING_FIELDS))
      setFormError(apiError.detail)
      // The slot was taken (409) or is no longer bookable (400, e.g. it has passed).
      if (apiError.status === 400 || apiError.status === 409) {
        setTime('')
        loadSlots(doctorId, date)
      }
      setBooking(false)
    }
  }

  const availableSlots = slots.status === 'success' ? slots.slots : []

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <div>
        <label htmlFor="doctor" className="block text-sm font-medium text-slate-700">
          Doctor
        </label>
        <select
          id="doctor"
          value={doctorId}
          onChange={handleDoctorChange}
          className={fieldClass}
          {...describeError('doctor-error', errors.doctor_id)}
        >
          <option value="">Select a doctor</option>
          {doctors.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} - {d.specialty}
            </option>
          ))}
        </select>
        <FieldError id="doctor-error" message={errors.doctor_id} />
      </div>
      <div>
        <label htmlFor="appt-date" className="block text-sm font-medium text-slate-700">
          Appointment date
        </label>
        <input
          id="appt-date"
          type="date"
          value={date}
          min={today}
          max={maxDate}
          onChange={handleDateChange}
          className={fieldClass}
          {...describeError('appt-date-error', errors.date)}
        />
        <FieldError id="appt-date-error" message={errors.date} />
      </div>
      <div>
        <label htmlFor="appt-time" className="block text-sm font-medium text-slate-700">
          Consultation time
        </label>
        <select
          id="appt-time"
          value={time}
          onChange={(e) => setTime(e.target.value)}
          disabled={availableSlots.length === 0}
          className={fieldClass}
          {...describeError('appt-time-error', errors.time)}
        >
          <option value="">{slotPlaceholder(slots)}</option>
          {availableSlots.map((slot) => (
            <option key={slot.time} value={slot.time}>
              {slot.label}
            </option>
          ))}
        </select>
        <FieldError id="appt-time-error" message={errors.time} />
        {slots.status === 'error' && (
          <p className="mt-1 text-sm text-red-600">
            {slots.message}{' '}
            <button
              type="button"
              onClick={() => loadSlots(doctorId, date)}
              className="font-semibold underline"
            >
              Try again
            </button>
          </p>
        )}
      </div>
      {formError && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
          {formError}
        </p>
      )}
      <IconButton type="submit" label="Confirm Appointment" loading={booking} />
    </form>
  )
}

function ExistingAppointment({ appointment }: { appointment: Appointment }) {
  const navigate = useNavigate()

  return (
    <div className="space-y-4">
      <p
        role="status"
        className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
      >
        You already have an upcoming appointment (token {appointment.token}).
      </p>
      <IconButton label="View queue status" onClick={() => navigate('/queue-status')} />
    </div>
  )
}

function BookAppointment() {
  const { state, retry } = useApiData(loadBookingPage)

  let content
  if (state.status === 'loading') {
    content = <LoadingState label="Loading doctors..." />
  } else if (state.status === 'error') {
    content = <ErrorState message={state.error.detail} onRetry={retry} />
  } else if (state.data.current) {
    content = <ExistingAppointment appointment={state.data.current} />
  } else if (state.data.doctors.length) {
    // A booking rejected because one already exists reloads the page data, showing the notice.
    content = (
      <BookingForm
        doctors={state.data.doctors}
        today={state.data.today}
        maxDate={state.data.max_date}
        onAlreadyBooked={retry}
      />
    )
  } else {
    content = (
      <p className="text-center text-sm text-slate-500">
        No doctors are available right now. Please check back later.
      </p>
    )
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 px-4 py-10">
      <SessionBar />
      <h1 className="text-2xl font-bold text-slate-900">PrimeCare Clinic</h1>
      <FormSection
        title="Book appointment"
        subtitle="Choose your doctor, date and consultation time."
      >
        {content}
      </FormSection>
    </div>
  )
}

export default BookAppointment
