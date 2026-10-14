import { render, screen } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import AuthProvider from '../auth/AuthContext'
import ProtectedRoute from '../auth/ProtectedRoute'

type Entry = string | { pathname: string; state?: unknown }

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="location">{location.pathname}</p>
}

/** Renders routes inside the real AuthProvider; unmatched paths render a location probe. */
export function renderRoutes(routes: ReactNode, initialEntry: Entry = '/') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthProvider>
        <Routes>
          {routes}
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

/** Renders a page behind ProtectedRoute at `path`, as the app does. */
export function renderProtectedPage(page: ReactElement, path: string, state?: unknown) {
  return renderRoutes(
    <Route element={<ProtectedRoute />}>
      <Route path={path} element={page} />
    </Route>,
    { pathname: path, state },
  )
}

/** Waits for navigation away from the page under test and returns the new path. */
export async function navigatedTo(): Promise<string | null> {
  return (await screen.findByTestId('location')).textContent
}
