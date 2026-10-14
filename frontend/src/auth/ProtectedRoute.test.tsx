import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockFetch } from '../test/fetchMock'
import { signedIn, signedOut } from '../test/fixtures'
import { navigatedTo, renderProtectedPage } from '../test/render'

describe('ProtectedRoute', () => {
  it('shows a loading state while the session is checked', async () => {
    mockFetch(signedIn)
    renderProtectedPage(<p>Secret page</p>, '/queue-status')
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session...')
    expect(await screen.findByText('Secret page')).toBeInTheDocument()
  })

  it('redirects anonymous users to /login', async () => {
    mockFetch(signedOut)
    renderProtectedPage(<p>Secret page</p>, '/queue-status')
    expect(await navigatedTo()).toBe('/login')
    expect(screen.queryByText('Secret page')).not.toBeInTheDocument()
  })
})
