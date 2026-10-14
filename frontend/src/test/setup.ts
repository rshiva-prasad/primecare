import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Vitest globals are off, so Testing Library cannot register its own cleanup hook.
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})
