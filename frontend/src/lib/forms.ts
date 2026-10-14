import type { FieldErrors } from '../types'

export function hasErrors(errors: object): boolean {
  return Object.values(errors).some(Boolean)
}

/** Server field errors for the given keys, with '' for keys the server did not flag. */
export function pickFieldErrors<K extends string>(
  fields: FieldErrors,
  keys: readonly K[],
): Record<K, string> {
  const picked = {} as Record<K, string>
  for (const key of keys) {
    picked[key] = fields[key] ?? ''
  }
  return picked
}

/** ARIA attributes that link an input to its error message when there is one. */
export function describeError(errorId: string, message: string) {
  return message ? { 'aria-invalid': true, 'aria-describedby': errorId } : {}
}
