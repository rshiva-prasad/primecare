import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, GENERIC_ERROR_MESSAGE } from '../lib/api'
import { useApiData } from './useApiData'

describe('useApiData', () => {
  it('starts loading and then exposes the data', async () => {
    const load = vi.fn().mockResolvedValue(['a'])
    const { result } = renderHook(() => useApiData(load))
    expect(result.current.state).toEqual({ status: 'loading' })
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: 'success', data: ['a'], refreshError: null }),
    )
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('exposes errors as ApiErrors and can retry', async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce('ok')
    const { result } = renderHook(() => useApiData(load))
    await waitFor(() => expect(result.current.state.status).toBe('error'))
    const state = result.current.state
    expect(state.status === 'error' && state.error.detail).toBe(GENERIC_ERROR_MESSAGE)

    act(() => result.current.retry())
    expect(result.current.state).toEqual({ status: 'loading' })
    await waitFor(() => expect(result.current.state.status).toBe('success'))
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('polls after each response, keeps data on refresh errors and stops on unmount', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const refreshError = new ApiError(503, 'Unavailable.')
    const load = vi
      .fn()
      .mockResolvedValueOnce(1)
      .mockRejectedValueOnce(refreshError)
      .mockResolvedValueOnce(2)
      .mockRejectedValueOnce(new ApiError(404, 'Gone.'))
    const { result, unmount } = renderHook(() => useApiData(load, 1000))

    await waitFor(() => expect(result.current.state).toMatchObject({ data: 1 }))

    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.state).toEqual({ status: 'success', data: 1, refreshError })

    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.state).toEqual({ status: 'success', data: 2, refreshError: null })

    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.state).toMatchObject({ status: 'error', error: { status: 404 } })
    expect(load).toHaveBeenCalledTimes(4)

    unmount()
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(load).toHaveBeenCalledTimes(4)
  })

  it('ignores a response that arrives after unmount', async () => {
    let resolve!: (value: string) => void
    const load = vi.fn(() => new Promise<string>((done) => (resolve = done)))
    const { result, unmount } = renderHook(() => useApiData(load, 1000))
    unmount()
    await act(async () => resolve('late'))
    expect(result.current.state).toEqual({ status: 'loading' })
  })
})
