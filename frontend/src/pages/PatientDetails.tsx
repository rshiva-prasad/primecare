import ErrorState from '../components/ErrorState'
import FieldError from '../components/FieldError'
import FormSection from '../components/FormSection'
import LoadingState from '../components/LoadingState'
import SessionBar from '../components/SessionBar'
import ThreeDButton from '../components/ThreeDButton'
import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { useApiData } from '../hooks/useApiData'
import { getPatient, savePatient, toApiError } from '../lib/api'
import { describeError, hasErrors, pickFieldErrors } from '../lib/forms'
import { validateEmail, validateMobile, validateName } from '../lib/validation'
import type { Patient } from '../types'

type PatientField = keyof Patient
type PatientErrors = Record<PatientField, string>

const PATIENT_FIELDS: readonly PatientField[] = ['first_name', 'last_name', 'mobile', 'email']
const NO_ERRORS: PatientErrors = { first_name: '', last_name: '', mobile: '', email: '' }

const inputClass =
  'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600'

function validatePatient(values: Patient): PatientErrors {
  return {
    first_name: validateName(values.first_name, 'First name'),
    last_name: validateName(values.last_name, 'Last name'),
    mobile: validateMobile(values.mobile),
    email: validateEmail(values.email),
  }
}

/** A notice passed via navigation state, e.g. when booking needs details first. */
function readNotice(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'notice' in state) {
    return typeof state.notice === 'string' ? state.notice : ''
  }
  return ''
}

interface PatientFormProps {
  initial: Patient
  notice: string
}

function PatientForm({ initial, notice }: PatientFormProps) {
  const navigate = useNavigate()
  const [values, setValues] = useState<Patient>(initial)
  const [errors, setErrors] = useState<PatientErrors>(NO_ERRORS)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const update = (field: PatientField) => (e: ChangeEvent<HTMLInputElement>) => {
    const { value } = e.target
    setValues((current) => ({ ...current, [field]: value }))
  }

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (saving) {
      return
    }
    const nextErrors = validatePatient(values)
    setErrors(nextErrors)
    setFormError('')
    if (hasErrors(nextErrors)) {
      return
    }

    setSaving(true)
    try {
      await savePatient({
        first_name: values.first_name.trim(),
        last_name: values.last_name.trim(),
        mobile: values.mobile.trim(),
        email: values.email.trim(),
      })
      navigate('/book-appointment')
    } catch (error) {
      const apiError = toApiError(error)
      setErrors(pickFieldErrors(apiError.fields, PATIENT_FIELDS))
      setFormError(apiError.detail)
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      {notice && (
        <p
          role="status"
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
        >
          {notice}
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="firstName" className="block text-sm font-medium text-slate-700">
            First name
          </label>
          <input
            id="firstName"
            type="text"
            autoComplete="given-name"
            placeholder="John"
            value={values.first_name}
            onChange={update('first_name')}
            className={inputClass}
            {...describeError('firstName-error', errors.first_name)}
          />
          <FieldError id="firstName-error" message={errors.first_name} />
        </div>
        <div>
          <label htmlFor="lastName" className="block text-sm font-medium text-slate-700">
            Last name
          </label>
          <input
            id="lastName"
            type="text"
            autoComplete="family-name"
            placeholder="Doe"
            value={values.last_name}
            onChange={update('last_name')}
            className={inputClass}
            {...describeError('lastName-error', errors.last_name)}
          />
          <FieldError id="lastName-error" message={errors.last_name} />
        </div>
      </div>
      <div>
        <label htmlFor="mobile" className="block text-sm font-medium text-slate-700">
          Mobile number
        </label>
        <input
          id="mobile"
          type="tel"
          autoComplete="tel"
          placeholder="077 123 4567"
          value={values.mobile}
          onChange={update('mobile')}
          className={inputClass}
          {...describeError('mobile-error', errors.mobile)}
        />
        <FieldError id="mobile-error" message={errors.mobile} />
      </div>
      <div>
        <label htmlFor="patient-email" className="block text-sm font-medium text-slate-700">
          Email address
        </label>
        <input
          id="patient-email"
          type="email"
          autoComplete="email"
          placeholder="john.doe@example.com"
          value={values.email}
          onChange={update('email')}
          className={inputClass}
          {...describeError('patient-email-error', errors.email)}
        />
        <FieldError id="patient-email-error" message={errors.email} />
      </div>
      {formError && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
          {formError}
        </p>
      )}
      <ThreeDButton type="submit" label="Continue" variant="primary" loading={saving} />
    </form>
  )
}

function PatientDetails() {
  const { user } = useAuth()
  const location = useLocation()
  const { state, retry } = useApiData(getPatient)

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 px-4 py-10">
      <SessionBar />
      <h1 className="text-2xl font-bold text-slate-900">PrimeCare Clinic</h1>
      <FormSection
        title="Patient details"
        subtitle="Your details will be used for your appointment and queue token."
      >
        {state.status === 'loading' && <LoadingState label="Loading your details..." />}
        {state.status === 'error' && <ErrorState message={state.error.detail} onRetry={retry} />}
        {state.status === 'success' && (
          <PatientForm
            initial={
              state.data ?? { first_name: '', last_name: '', mobile: '', email: user?.email ?? '' }
            }
            notice={readNotice(location.state)}
          />
        )}
      </FormSection>
    </div>
  )
}

export default PatientDetails
