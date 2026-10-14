// Client-side rules mirror the backend validators; the server stays the source of truth.

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
export const MOBILE_PATTERN = /^\+?[0-9 ()-]{7,20}$/
export const MIN_PASSWORD_LENGTH = 8
export const MAX_PASSWORD_LENGTH = 72
export const MAX_NAME_LENGTH = 80
export const MAX_EMAIL_LENGTH = 254
const MIN_MOBILE_DIGITS = 7

// Each validator returns an error message, or '' when the value is valid.

export function validateEmail(value: string): string {
  const email = value.trim()
  if (!email) {
    return 'Email is required.'
  }
  if (email.length > MAX_EMAIL_LENGTH || !EMAIL_PATTERN.test(email)) {
    return 'Please enter a valid email address.'
  }
  return ''
}

export function validateName(value: string, label: string): string {
  const name = value.trim()
  if (!name) {
    return `${label} is required.`
  }
  if (name.length > MAX_NAME_LENGTH) {
    return `${label} must be ${MAX_NAME_LENGTH} characters or fewer.`
  }
  return ''
}

export function validateMobile(value: string): string {
  const mobile = value.trim()
  if (!mobile) {
    return 'Mobile number is required.'
  }
  const digits = mobile.replace(/\D/g, '').length
  if (!MOBILE_PATTERN.test(mobile) || digits < MIN_MOBILE_DIGITS) {
    return 'Please enter a valid mobile number.'
  }
  return ''
}

export function validateLoginPassword(value: string): string {
  return value ? '' : 'Password is required.'
}

export function validateNewPassword(value: string): string {
  if (!value) {
    return 'Password is required.'
  }
  if (value.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`
  }
  if (value.length > MAX_PASSWORD_LENGTH) {
    return `Password must be ${MAX_PASSWORD_LENGTH} characters or fewer.`
  }
  return ''
}

export function validatePasswordConfirmation(password: string, confirmation: string): string {
  if (!confirmation) {
    return 'Please confirm your password.'
  }
  return confirmation === password ? '' : 'Passwords do not match.'
}
