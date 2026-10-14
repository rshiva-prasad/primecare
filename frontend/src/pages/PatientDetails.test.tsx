import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { bodyOf, callsTo, deferred, mockFetch } from '../test/fetchMock'
import type { MockReply, MockRoutes } from '../test/fetchMock'
import { patient, signedIn, user } from '../test/fixtures'
import { navigatedTo, renderProtectedPage } from '../test/render'
import PatientDetails from './PatientDetails'

function renderPage(routes: MockRoutes, state?: unknown) {
  const fetchMock = mockFetch({ ...signedIn, ...routes })
  renderProtectedPage(<PatientDetails />, '/patient-details', state)
  return fetchMock
}

describe('PatientDetails', () => {
  it('shows a loading state, then prefills an existing record', async () => {
    const reply = deferred<MockReply>()
    renderPage({ 'GET /api/patients/me': () => reply.promise })
    expect(await screen.findByText('Loading your details...')).toBeInTheDocument()
    reply.resolve({ body: { patient } })
    expect(await screen.findByLabelText('First name')).toHaveValue('Jane')
    expect(screen.getByLabelText('Last name')).toHaveValue('Citizen')
    expect(screen.getByLabelText('Mobile number')).toHaveValue('0400 000 000')
    expect(screen.getByLabelText('Email address')).toHaveValue('jane.citizen@example.com')
    expect(screen.getByText(/Signed in as/)).toHaveTextContent(user.email)
  })

  it('defaults the email to the account email when there is no record', async () => {
    renderPage({ 'GET /api/patients/me': { body: { patient: null } } })
    expect(await screen.findByLabelText('Email address')).toHaveValue(user.email)
    expect(screen.getByLabelText('First name')).toHaveValue('')
  })

  it('validates the fields before saving', async () => {
    const fetchMock = renderPage({ 'GET /api/patients/me': { body: { patient: null } } })
    const userEv = userEvent.setup()
    await userEv.clear(await screen.findByLabelText('Email address'))
    await userEv.type(screen.getByLabelText('Mobile number'), '12ab')
    await userEv.click(screen.getByRole('button', { name: 'Continue' }))

    expect(screen.getByText('First name is required.')).toBeInTheDocument()
    expect(screen.getByText('Last name is required.')).toBeInTheDocument()
    expect(screen.getByText('Please enter a valid mobile number.')).toBeInTheDocument()
    expect(screen.getByText('Email is required.')).toBeInTheDocument()
    expect(callsTo(fetchMock, 'PUT /api/patients/me')).toHaveLength(0)
  })

  it('saves trimmed details and continues to booking', async () => {
    const fetchMock = renderPage({
      'GET /api/patients/me': { body: { patient: null } },
      'PUT /api/patients/me': { body: { patient } },
    })
    const userEv = userEvent.setup()
    await userEv.type(await screen.findByLabelText('First name'), ' Jane ')
    await userEv.type(screen.getByLabelText('Last name'), 'Citizen')
    await userEv.type(screen.getByLabelText('Mobile number'), '0400 000 000')
    await userEv.click(screen.getByRole('button', { name: 'Continue' }))

    expect(await navigatedTo()).toBe('/book-appointment')
    expect(bodyOf(callsTo(fetchMock, 'PUT /api/patients/me')[0])).toEqual({
      first_name: 'Jane',
      last_name: 'Citizen',
      mobile: '0400 000 000',
      email: user.email,
    })
  })

  it('shows server field errors under the matching inputs', async () => {
    renderPage({
      'GET /api/patients/me': { body: { patient } },
      'PUT /api/patients/me': {
        status: 422,
        body: {
          detail: 'Please correct the highlighted fields.',
          fields: { mobile: 'Enter a valid mobile number.', last_name: 'Too long.' },
        },
      },
    })
    const userEv = userEvent.setup()
    await userEv.click(await screen.findByRole('button', { name: 'Continue' }))

    expect(await screen.findByText('Enter a valid mobile number.')).toBeInTheDocument()
    expect(screen.getByText('Too long.')).toBeInTheDocument()
    expect(screen.getByLabelText('Mobile number')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('Please correct the highlighted fields.')
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
  })

  it('shows a load error and retries', async () => {
    renderPage({
      'GET /api/patients/me': [
        { status: 503, body: { detail: 'The service is temporarily unavailable.' } },
        { body: { patient } },
      ],
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The service is temporarily unavailable.',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByLabelText('First name')).toHaveValue('Jane')
  })

  it('shows a notice passed from the booking screen', async () => {
    renderPage(
      { 'GET /api/patients/me': { body: { patient: null } } },
      { notice: 'Please complete your patient details first.' },
    )
    expect(await screen.findByText('Please complete your patient details first.')).toHaveAttribute(
      'role',
      'status',
    )
  })

  it('ignores malformed navigation state', async () => {
    renderPage({ 'GET /api/patients/me': { body: { patient: null } } }, { notice: 42 })
    await screen.findByLabelText('First name')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
