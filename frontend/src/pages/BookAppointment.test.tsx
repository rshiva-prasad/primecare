import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { bodyOf, callsTo, deferred, mockFetch } from '../test/fetchMock'
import type { MockReply, MockRoutes } from '../test/fetchMock'
import { appointment, doctorsBody, signedIn, slots } from '../test/fixtures'
import { navigatedTo, renderProtectedPage } from '../test/render'
import BookAppointment from './BookAppointment'

const PERERA_SLOTS = 'GET /api/doctors/dr-perera/slots'
const SHARMA_SLOTS = 'GET /api/doctors/dr-sharma/slots'
const CURRENT = 'GET /api/appointments/current'
const NO_CURRENT: MockReply = { status: 404, body: { detail: 'No upcoming appointment found.' } }
const ALREADY_BOOKED = 'You already have an upcoming appointment.'
/** The clinic's dates as the server reports them (never the browser clock). */
const TODAY = doctorsBody.today
const MAX_DATE = doctorsBody.max_date

function renderPage(routes: MockRoutes = {}) {
  const fetchMock = mockFetch({
    ...signedIn,
    'GET /api/doctors': { body: doctorsBody },
    [CURRENT]: NO_CURRENT,
    [PERERA_SLOTS]: { body: { date: TODAY, slots } },
    ...routes,
  })
  renderProtectedPage(<BookAppointment />, '/book-appointment')
  return fetchMock
}

async function chooseDoctorAndTime(time = '14:30') {
  const userEv = userEvent.setup()
  await userEv.selectOptions(await screen.findByLabelText('Doctor'), 'dr-perera')
  await waitFor(() => expect(screen.getByLabelText('Consultation time')).toBeEnabled())
  await userEv.selectOptions(screen.getByLabelText('Consultation time'), time)
  return userEv
}

describe('BookAppointment', () => {
  it('loads doctors and the clinic date range from the API', async () => {
    const reply = deferred<MockReply>()
    renderPage({ 'GET /api/doctors': () => reply.promise })
    expect(await screen.findByText('Loading doctors...')).toBeInTheDocument()
    reply.resolve({ body: doctorsBody })

    expect(
      await screen.findByRole('option', { name: 'Dr. Sarah Perera - General Practitioner' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('option', { name: 'Dr. Anita Sharma - Dermatologist' }),
    ).toBeInTheDocument()
    const dateInput = screen.getByLabelText('Appointment date')
    expect(dateInput).toHaveAttribute('min', TODAY)
    expect(dateInput).toHaveAttribute('max', MAX_DATE)
    expect(dateInput).toHaveValue(TODAY)
    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Consultation time')).toBeDisabled()
    expect(
      screen.getByRole('option', { name: 'Select a doctor and date first' }),
    ).toBeInTheDocument()
  })

  it("uses the clinic's date from the server, not the browser clock", async () => {
    // In every time zone this instant is 12 or 13 October locally, while the clinic is on the 14th.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-12T12:00:00Z'))
    const fetchMock = renderPage()
    const userEv = userEvent.setup()

    const dateInput = await screen.findByLabelText('Appointment date')
    expect(dateInput).toHaveValue('2026-10-14')
    expect(dateInput).toHaveAttribute('min', '2026-10-14')
    await userEv.selectOptions(screen.getByLabelText('Doctor'), 'dr-perera')
    expect(callsTo(fetchMock, PERERA_SLOTS)[0][0]).toContain('date=2026-10-14')

    // The browser's "today" is already in the past for the clinic.
    fireEvent.change(dateInput, { target: { value: '2026-10-13' } })
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(screen.getByText('Appointment date cannot be in the past.')).toBeInTheDocument()
  })

  it('fetches slots for the chosen doctor and date', async () => {
    const reply = deferred<MockReply>()
    const fetchMock = renderPage({ [PERERA_SLOTS]: () => reply.promise })
    const userEv = userEvent.setup()
    await userEv.selectOptions(await screen.findByLabelText('Doctor'), 'dr-perera')
    expect(screen.getByRole('option', { name: 'Loading time slots...' })).toBeInTheDocument()

    reply.resolve({ body: { date: TODAY, slots } })
    expect(await screen.findByRole('option', { name: '02:30 PM' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Select a time slot' })).toBeInTheDocument()
    expect(callsTo(fetchMock, PERERA_SLOTS)[0][0]).toBe(
      `/api/doctors/dr-perera/slots?date=${TODAY}`,
    )
  })

  it('refetches slots when the date changes and clears the chosen time', async () => {
    const fetchMock = renderPage()
    await chooseDoctorAndTime()
    fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '2026-11-02' } })
    await waitFor(() => expect(callsTo(fetchMock, PERERA_SLOTS)).toHaveLength(2))
    expect(callsTo(fetchMock, PERERA_SLOTS)[1][0]).toContain('date=2026-11-02')
    expect(await screen.findByRole('option', { name: '02:30 PM' })).toBeInTheDocument()
    expect(screen.getByLabelText('Consultation time')).toHaveValue('')
  })

  it('stops fetching slots when the date is cleared', async () => {
    const fetchMock = renderPage()
    await chooseDoctorAndTime()
    fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '' } })
    expect(
      screen.getByRole('option', { name: 'Select a doctor and date first' }),
    ).toBeInTheDocument()
    expect(callsTo(fetchMock, PERERA_SLOTS)).toHaveLength(1)
  })

  it('shows an empty state when no slots are available', async () => {
    renderPage({ [PERERA_SLOTS]: { body: { date: TODAY, slots: [] } } })
    const userEv = userEvent.setup()
    await userEv.selectOptions(await screen.findByLabelText('Doctor'), 'dr-perera')
    expect(
      await screen.findByRole('option', { name: 'No time slots available for this date' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Consultation time')).toBeDisabled()
  })

  it('ignores slot responses for a previous selection', async () => {
    const slow = deferred<MockReply>()
    renderPage({
      [PERERA_SLOTS]: () => slow.promise,
      [SHARMA_SLOTS]: {
        body: { date: TODAY, slots: [{ time: '16:00', label: '04:00 PM' }] },
      },
    })
    const userEv = userEvent.setup()
    await userEv.selectOptions(await screen.findByLabelText('Doctor'), 'dr-perera')
    await userEv.selectOptions(screen.getByLabelText('Doctor'), 'dr-sharma')
    expect(await screen.findByRole('option', { name: '04:00 PM' })).toBeInTheDocument()

    slow.resolve({ body: { date: TODAY, slots } })
    await new Promise((done) => setTimeout(done, 0))
    expect(screen.queryByRole('option', { name: '02:30 PM' })).not.toBeInTheDocument()
  })

  it('shows slot errors and retries', async () => {
    const fetchMock = renderPage({
      [PERERA_SLOTS]: [
        { status: 503, body: { detail: 'The service is temporarily unavailable.' } },
        { body: { date: TODAY, slots } },
      ],
    })
    const userEv = userEvent.setup()
    await userEv.selectOptions(await screen.findByLabelText('Doctor'), 'dr-perera')
    expect(await screen.findByText('The service is temporarily unavailable.')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Time slots unavailable' })).toBeInTheDocument()

    await userEv.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('option', { name: '02:30 PM' })).toBeInTheDocument()
    expect(callsTo(fetchMock, PERERA_SLOTS)).toHaveLength(2)
  })

  it('validates the booking before calling the API', async () => {
    const fetchMock = renderPage()
    const userEv = userEvent.setup()
    await userEv.click(await screen.findByRole('button', { name: 'Confirm Appointment' }))
    expect(screen.getByText('Please select a doctor.')).toBeInTheDocument()
    expect(screen.getByText('Please select a consultation time.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '2000-01-01' } })
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(screen.getByText('Appointment date cannot be in the past.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '2027-01-13' } })
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(
      screen.getByText('Appointments can only be booked up to 90 days ahead.'),
    ).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: MAX_DATE } })
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(
      screen.queryByText('Appointments can only be booked up to 90 days ahead.'),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Appointment date cannot be in the past.')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '' } })
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(screen.getByText('Please select an appointment date.')).toBeInTheDocument()
    expect(callsTo(fetchMock, 'POST /api/appointments')).toHaveLength(0)
  })

  it('books the appointment and goes to the queue status', async () => {
    const fetchMock = renderPage({
      'POST /api/appointments': { status: 201, body: { appointment } },
    })
    const userEv = await chooseDoctorAndTime()
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(await navigatedTo()).toBe('/queue-status')
    expect(bodyOf(callsTo(fetchMock, 'POST /api/appointments')[0])).toEqual({
      doctor_id: 'dr-perera',
      date: TODAY,
      time: '14:30',
    })
  })

  it('reloads slots when the chosen slot was just taken (409)', async () => {
    const detail = 'That time slot has just been booked. Please choose another.'
    const fetchMock = renderPage({
      'POST /api/appointments': { status: 409, body: { detail } },
    })
    const userEv = await chooseDoctorAndTime()
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
    await waitFor(() => expect(callsTo(fetchMock, PERERA_SLOTS)).toHaveLength(2))
    expect(screen.getByLabelText('Consultation time')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Confirm Appointment' })).toBeEnabled()
  })

  it('reloads slots and clears the time when the server rejects the booking (400)', async () => {
    const detail = 'That time slot has already passed. Please choose a later time.'
    const fetchMock = renderPage({
      'POST /api/appointments': { status: 400, body: { detail } },
    })
    const userEv = await chooseDoctorAndTime()
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
    await waitFor(() => expect(callsTo(fetchMock, PERERA_SLOTS)).toHaveLength(2))
    expect(screen.getByLabelText('Consultation time')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Confirm Appointment' })).toBeEnabled()
  })

  it('clears the server error when the doctor or date changes', async () => {
    const detail = 'That time slot has just been booked. Please choose another.'
    renderPage({
      'POST /api/appointments': { status: 409, body: { detail } },
      [SHARMA_SLOTS]: { body: { date: TODAY, slots: [] } },
    })
    const userEv = await chooseDoctorAndTime()
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(detail)

    await userEv.selectOptions(screen.getByLabelText('Doctor'), 'dr-sharma')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      await screen.findByRole('option', { name: 'No time slots available for this date' }),
    ).toBeInTheDocument()

    await userEv.selectOptions(screen.getByLabelText('Doctor'), 'dr-perera')
    await waitFor(() => expect(screen.getByLabelText('Consultation time')).toBeEnabled())
    await userEv.selectOptions(screen.getByLabelText('Consultation time'), '09:00')
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(detail)

    fireEvent.change(screen.getByLabelText('Appointment date'), { target: { value: '2026-11-02' } })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('sends the patient to complete their details first (412)', async () => {
    renderPage({
      'POST /api/appointments': {
        status: 412,
        body: { detail: 'Please complete your patient details first.' },
      },
    })
    const userEv = await chooseDoctorAndTime()
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(await navigatedTo()).toBe('/patient-details')
  })

  it('shows field errors from the server and keeps the chosen slot (422)', async () => {
    const fetchMock = renderPage({
      'POST /api/appointments': {
        status: 422,
        body: {
          detail: 'Please correct the highlighted fields.',
          fields: { time: 'Enter a time as HH:MM.' },
        },
      },
    })
    const userEv = await chooseDoctorAndTime()
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))
    expect(await screen.findByText('Enter a time as HH:MM.')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Please correct the highlighted fields.')
    expect(screen.getByLabelText('Consultation time')).toHaveValue('14:30')
    expect(callsTo(fetchMock, PERERA_SLOTS)).toHaveLength(1)
  })

  it('shows an existing upcoming appointment instead of the booking form', async () => {
    renderPage({ [CURRENT]: { body: { appointment } } })
    const notice = 'You already have an upcoming appointment (token PC-024).'
    expect(await screen.findByText(notice)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(notice)
    expect(screen.queryByLabelText('Doctor')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm Appointment' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'View queue status' }))
    expect(await navigatedTo()).toBe('/queue-status')
  })

  it('switches to the existing-appointment notice when the server refuses a second booking', async () => {
    const fetchMock = renderPage({
      [CURRENT]: [NO_CURRENT, { body: { appointment } }],
      'POST /api/appointments': { status: 400, body: { detail: ALREADY_BOOKED } },
    })
    const userEv = await chooseDoctorAndTime()
    await userEv.click(screen.getByRole('button', { name: 'Confirm Appointment' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'You already have an upcoming appointment (token PC-024).',
    )
    expect(screen.queryByLabelText('Doctor')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(callsTo(fetchMock, CURRENT)).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'View queue status' })).toBeInTheDocument()
  })

  it('shows an error and retries when the existing appointment cannot be checked', async () => {
    renderPage({
      [CURRENT]: [
        { status: 503, body: { detail: 'The service is temporarily unavailable.' } },
        NO_CURRENT,
      ],
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The service is temporarily unavailable.',
    )
    expect(screen.queryByLabelText('Doctor')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByLabelText('Doctor')).toBeInTheDocument()
  })

  it('shows a doctors load error and retries', async () => {
    renderPage({
      'GET /api/doctors': [
        { status: 503, body: { detail: 'The service is temporarily unavailable.' } },
        { body: doctorsBody },
      ],
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The service is temporarily unavailable.',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByLabelText('Doctor')).toBeInTheDocument()
  })

  it('shows an empty state when no doctors are available', async () => {
    renderPage({ 'GET /api/doctors': { body: { ...doctorsBody, doctors: [] } } })
    expect(
      await screen.findByText('No doctors are available right now. Please check back later.'),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Doctor')).not.toBeInTheDocument()
  })
})
