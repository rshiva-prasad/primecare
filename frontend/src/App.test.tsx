import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'
import AppRoutes from './AppRoutes'
import AuthProvider from './auth/AuthContext'
import { mockFetch } from './test/fetchMock'
import { patient, signedIn, signedOut } from './test/fixtures'

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('App routes', () => {
  it.each([
    '/',
    '/does-not-exist',
    '/patient-details',
    '/book-appointment',
    '/queue-status',
    '/confirmation',
  ])('sends anonymous visitors from %s to the login screen', async (path) => {
    mockFetch(signedOut)
    renderAt(path)
    expect(await screen.findByRole('button', { name: 'Log in' })).toBeInTheDocument()
  })

  it('lets signed-in users reach protected pages', async () => {
    mockFetch({ ...signedIn, 'GET /api/patients/me': { body: { patient } } })
    renderAt('/patient-details')
    expect(await screen.findByLabelText('First name')).toHaveValue('Jane')
  })

  it('renders inside a browser router', async () => {
    mockFetch(signedOut)
    window.history.pushState({}, '', '/')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'PrimeCare Clinic' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
  })
})
