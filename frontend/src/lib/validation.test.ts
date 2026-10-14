import { describe, expect, it } from 'vitest'
import {
  validateEmail,
  validateLoginPassword,
  validateMobile,
  validateName,
  validateNewPassword,
  validatePasswordConfirmation,
} from './validation'

describe('validateEmail', () => {
  it('accepts a valid address, ignoring surrounding spaces', () => {
    expect(validateEmail('  patient@example.com ')).toBe('')
  })

  it('requires a value', () => {
    expect(validateEmail('   ')).toBe('Email is required.')
  })

  it.each(['patient', 'patient@example', 'pa tient@example.com', `${'a'.repeat(250)}@x.co`])(
    'rejects %s',
    (value) => {
      expect(validateEmail(value)).toBe('Please enter a valid email address.')
    },
  )
})

describe('validateName', () => {
  it('accepts a name and reports the field label when missing', () => {
    expect(validateName('Jane', 'First name')).toBe('')
    expect(validateName(' ', 'Last name')).toBe('Last name is required.')
  })

  it('limits names to 80 characters', () => {
    expect(validateName('a'.repeat(80), 'First name')).toBe('')
    expect(validateName('a'.repeat(81), 'First name')).toBe(
      'First name must be 80 characters or fewer.',
    )
  })
})

describe('validateMobile', () => {
  it.each(['0400 000 000', '+61 (2) 9000-0000', '1234567'])('accepts %s', (value) => {
    expect(validateMobile(value)).toBe('')
  })

  it('requires a value', () => {
    expect(validateMobile('')).toBe('Mobile number is required.')
  })

  it.each(['12345', 'phone me', '(((((()))))', '+'.repeat(2) + '1234567', '1'.repeat(21)])(
    'rejects %s',
    (value) => {
      expect(validateMobile(value)).toBe('Please enter a valid mobile number.')
    },
  )
})

describe('passwords', () => {
  it('only requires a value when logging in', () => {
    expect(validateLoginPassword('')).toBe('Password is required.')
    expect(validateLoginPassword('x')).toBe('')
  })

  it('enforces 8 to 72 characters for new passwords', () => {
    expect(validateNewPassword('')).toBe('Password is required.')
    expect(validateNewPassword('short')).toBe('Password must be at least 8 characters.')
    expect(validateNewPassword('a'.repeat(8))).toBe('')
    expect(validateNewPassword('a'.repeat(73))).toBe('Password must be 72 characters or fewer.')
  })

  it('requires a matching confirmation', () => {
    expect(validatePasswordConfirmation('abcdefgh', '')).toBe('Please confirm your password.')
    expect(validatePasswordConfirmation('abcdefgh', 'abcdefgx')).toBe('Passwords do not match.')
    expect(validatePasswordConfirmation('abcdefgh', 'abcdefgh')).toBe('')
  })
})
