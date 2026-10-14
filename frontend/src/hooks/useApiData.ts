import { useCallback, useEffect, useState } from 'react'
import { toApiError } from '../lib/api'
import type { ApiError } from '../lib/api'

export type ApiData<T> =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'success'; data: T; refreshError: ApiError | null }

/**
 * Loads data on mount and, when `pollIntervalMs` is set, again that long after each
 * response settles (so slow responses never overlap). Timers are cleared on unmount.
 * `load` must be stable (a module-level function or memoised callback).
 */
export function useApiData<T>(load: () => Promise<T>, pollIntervalMs?: number) {
  const [state, setState] = useState<ApiData<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined

    const run = () => {
      load()
        .then(
          (data) => {
            if (active) setState({ status: 'success', data, refreshError: null })
          },
          (reason: unknown) => {
            if (!active) return
            const error = toApiError(reason)
            // A failed background refresh keeps the last good data on screen, unless the
            // resource no longer exists (404).
            setState((previous) =>
              previous.status === 'success' && error.status !== 404
                ? { ...previous, refreshError: error }
                : { status: 'error', error },
            )
          },
        )
        .finally(() => {
          if (active && pollIntervalMs) timer = setTimeout(run, pollIntervalMs)
        })
    }

    run()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [load, pollIntervalMs, attempt])

  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((count) => count + 1)
  }, [])

  return { state, retry }
}
