import FieldError from '../components/FieldError'
import LoadingState from '../components/LoadingState'
import ThreeDButton from '../components/ThreeDButton'
import { useState } from 'react'
import type { FormEvent } from 'react'
import PostLoginRedirect from '../auth/PostLoginRedirect'
import { useAuth } from '../auth/useAuth'
import { toApiError } from '../lib/api'
import { describeError, hasErrors } from '../lib/forms'
import {
  validateEmail,
  validateLoginPassword,
  validateNewPassword,
  validatePasswordConfirmation,
} from '../lib/validation'

type Mode = 'login' | 'register'

interface LoginErrors {
  email: string
  password: string
  confirmPassword: string
}

const NO_ERRORS: LoginErrors = { email: '', password: '', confirmPassword: '' }
const CONFIRM_EMAIL_MESSAGE = 'Check your email to confirm your account, then log in.'

const inputClass =
  'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600'

function Login() {
  const { status, sessionMessage, clearSessionMessage, login, register } = useAuth()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [errors, setErrors] = useState<LoginErrors>(NO_ERRORS)
  const [formError, setFormError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const isRegister = mode === 'register'

  if (status === 'loading') {
    return <LoadingState label="Checking your session..." fullPage />
  }
  if (status === 'authenticated') {
    return <PostLoginRedirect />
  }

  const changeMode = (next: Mode) => {
    setMode(next)
    setPassword('')
    setConfirmPassword('')
    setErrors(NO_ERRORS)
    setFormError('')
  }

  const validate = (): LoginErrors => ({
    email: validateEmail(email),
    password: isRegister ? validateNewPassword(password) : validateLoginPassword(password),
    confirmPassword: isRegister ? validatePasswordConfirmation(password, confirmPassword) : '',
  })

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (submitting) {
      return
    }
    const nextErrors = validate()
    setErrors(nextErrors)
    setFormError('')
    setNotice('')
    clearSessionMessage()
    if (hasErrors(nextErrors)) {
      return
    }

    setSubmitting(true)
    const credentials = { email: email.trim(), password }
    try {
      if (!isRegister) {
        // On success the auth state changes and the redirect below takes over.
        await login(credentials)
        return
      }
      const result = await register(credentials)
      if (!result.session_started) {
        changeMode('login')
        setNotice(result.detail ?? CONFIRM_EMAIL_MESSAGE)
        setSubmitting(false)
      }
    } catch (error) {
      const apiError = toApiError(error)
      setErrors({
        email: apiError.fields.email ?? '',
        password: apiError.fields.password ?? '',
        confirmPassword: '',
      })
      setFormError(apiError.detail)
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-teal-600 text-xl font-bold text-white">
            P
          </div>
          <h1 className="mt-4 text-2xl font-bold text-slate-900">PrimeCare Clinic</h1>
          <p className="mt-1 text-sm text-slate-500">
            {isRegister ? 'Create your patient account' : 'Digital Queue Management'}
          </p>
        </div>

        {(notice || sessionMessage) && (
          <div
            role="status"
            className="mt-6 rounded-lg border border-green-200 bg-green-50 p-4 text-center text-sm text-green-700"
          >
            {notice || sessionMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              {...describeError('email-error', errors.email)}
            />
            <FieldError id="email-error" message={errors.email} />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              placeholder={isRegister ? 'At least 8 characters' : 'Enter your password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              {...describeError('password-error', errors.password)}
            />
            <FieldError id="password-error" message={errors.password} />
          </div>

          {isRegister && (
            <div>
              <label
                htmlFor="confirm-password"
                className="block text-sm font-medium text-slate-700"
              >
                Confirm password
              </label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                placeholder="Re-enter your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={inputClass}
                {...describeError('confirm-password-error', errors.confirmPassword)}
              />
              <FieldError id="confirm-password-error" message={errors.confirmPassword} />
            </div>
          )}

          {formError && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              {formError}
            </p>
          )}

          <ThreeDButton
            type="submit"
            label={isRegister ? 'Create account' : 'Log in'}
            variant="primary"
            loading={submitting}
          />
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          {isRegister ? 'Already have an account?' : 'New to PrimeCare?'}{' '}
          <button
            type="button"
            onClick={() => {
              changeMode(isRegister ? 'login' : 'register')
              setNotice('')
            }}
            disabled={submitting}
            className="font-semibold text-teal-700 underline hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRegister ? 'Log in' : 'Create an account'}
          </button>
        </p>
      </div>
    </div>
  )
}

export default Login
