import { vi } from 'vitest'

export interface MockReply {
  status?: number
  body?: unknown
  /** Raw (non-JSON) response text. */
  raw?: string
}

type RouteHandler = (init: RequestInit | undefined, url: URL) => MockReply | Promise<MockReply>
export type MockRoute = MockReply | MockReply[] | RouteHandler
export type MockRoutes = Record<string, MockRoute>

export function jsonResponse(status: number, body?: unknown): Response {
  if (body === undefined) {
    return new Response(null, { status })
  }
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/**
 * Stubs global fetch with a route table keyed by "METHOD /path" (query string ignored).
 * An array replies in order and then repeats its last entry. Unknown routes reply 500.
 */
export function mockFetch(routes: MockRoutes) {
  const counters = new Map<string, number>()

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const key = `${init?.method ?? 'GET'} ${url.pathname}`
    const route = routes[key]
    if (!route) {
      return jsonResponse(500, { detail: `Unmocked request: ${key}` })
    }

    let reply: MockReply
    if (typeof route === 'function') {
      reply = await route(init, url)
    } else if (Array.isArray(route)) {
      const count = counters.get(key) ?? 0
      counters.set(key, count + 1)
      reply = route[Math.min(count, route.length - 1)]
    } else {
      reply = route
    }

    if (reply.raw !== undefined) {
      return new Response(reply.raw, { status: reply.status ?? 200 })
    }
    return jsonResponse(reply.status ?? 200, reply.body)
  })

  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Calls made to "METHOD /path", as [url, init] pairs. */
export function callsTo(fetchMock: ReturnType<typeof mockFetch>, key: string) {
  return fetchMock.mock.calls.filter(([input, init]) => {
    const url = new URL(String(input), 'http://localhost')
    return `${init?.method ?? 'GET'} ${url.pathname}` === key
  })
}

/** Parsed JSON body of a recorded call. */
export function bodyOf(call: [RequestInfo | URL, RequestInit?]): unknown {
  return JSON.parse(String(call[1]?.body))
}

/** A promise with its resolve function exposed, for holding a request in flight. */
export function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
