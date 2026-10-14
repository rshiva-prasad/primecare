import { describe, expect, it } from 'vitest'
import { describeError, hasErrors, pickFieldErrors } from './forms'

describe('form helpers', () => {
  it('hasErrors is true when any message is set', () => {
    expect(hasErrors({ a: '', b: '' })).toBe(false)
    expect(hasErrors({ a: '', b: 'Required.' })).toBe(true)
  })

  it('pickFieldErrors keeps known keys and blanks the rest', () => {
    expect(pickFieldErrors({ email: 'Bad.', other: 'Ignored.' }, ['email', 'mobile'])).toEqual({
      email: 'Bad.',
      mobile: '',
    })
  })

  it('describeError links an input to its message only when there is one', () => {
    expect(describeError('email-error', 'Bad.')).toEqual({
      'aria-invalid': true,
      'aria-describedby': 'email-error',
    })
    expect(describeError('email-error', '')).toEqual({})
  })
})
