import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import FieldError from './FieldError'
import FormSection from './FormSection'
import LoadingState from './LoadingState'
import ThreeDButton from './ThreeDButton'
import IconButton from './ui/IconButton'

describe('FormSection', () => {
  it('renders a labelled section with the default icon', () => {
    render(
      <FormSection title="Patient details" subtitle="Tell us about you.">
        <p>Body</p>
      </FormSection>,
    )
    const section = screen.getByRole('region', { name: 'Patient details' })
    expect(section).toHaveTextContent('Tell us about you.')
    expect(section).toHaveTextContent('P')
    expect(screen.getByText('Body')).toBeInTheDocument()
  })

  it('renders a custom icon and no subtitle', () => {
    render(
      <FormSection title="Book appointment" icon={<span>IC</span>}>
        <p>Body</p>
      </FormSection>,
    )
    expect(screen.getByText('IC')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Book appointment' })).toBeInTheDocument()
  })
})

describe('ThreeDButton', () => {
  it('calls onClick and defaults to type="button"', async () => {
    const onClick = vi.fn()
    render(<ThreeDButton label="Log in" variant="primary" onClick={onClick} />)
    const button = screen.getByRole('button', { name: 'Log in' })
    expect(button).toHaveAttribute('type', 'button')
    expect(button.className).toContain('bg-teal-600')
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('supports submit, secondary, disabled and loading states', () => {
    const { rerender } = render(
      <ThreeDButton label="Continue" variant="secondary" type="submit" disabled />,
    )
    const button = screen.getByRole('button', { name: 'Continue' })
    expect(button).toHaveAttribute('type', 'submit')
    expect(button.className).toContain('bg-white')
    expect(button).toBeDisabled()

    rerender(<ThreeDButton label="Continue" variant="primary" loading />)
    expect(screen.getByRole('button', { name: 'Continue' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
  })
})

describe('IconButton', () => {
  it('calls onClick and shows the arrow icon', async () => {
    const onClick = vi.fn()
    render(<IconButton label="View queue status" onClick={onClick} />)
    const button = screen.getByRole('button', { name: 'View queue status' })
    expect(button).toHaveAttribute('type', 'button')
    expect(button.querySelector('svg')).not.toBeNull()
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('swaps the arrow for a spinner and disables itself while loading', () => {
    render(<IconButton label="Confirm Appointment" type="submit" loading />)
    const button = screen.getByRole('button', { name: 'Confirm Appointment' })
    expect(button).toHaveAttribute('type', 'submit')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button.querySelector('svg')).toBeNull()
  })

  it('can be disabled without loading', () => {
    render(<IconButton label="Go" disabled />)
    expect(screen.getByRole('button', { name: 'Go' })).toBeDisabled()
  })
})

describe('feedback components', () => {
  it('LoadingState renders inline or full page', () => {
    const { rerender, container } = render(<LoadingState label="Loading doctors..." />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading doctors...')
    expect(container.querySelector('.min-h-screen')).toBeNull()
    rerender(<LoadingState label="Checking..." fullPage />)
    expect(container.querySelector('.min-h-screen')).not.toBeNull()
  })

  it('ErrorState shows the message and an optional retry', async () => {
    const onRetry = vi.fn()
    const { rerender } = render(<ErrorState message="Server down." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Server down.')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()

    rerender(<ErrorState message="Server down." onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('EmptyState shows its copy and action', async () => {
    const onAction = vi.fn()
    render(
      <EmptyState
        title="No upcoming appointment found."
        message="Book one."
        actionLabel="Book an appointment"
        onAction={onAction}
      />,
    )
    expect(screen.getByText('No upcoming appointment found.')).toBeInTheDocument()
    expect(screen.getByText('Book one.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Book an appointment' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('FieldError renders only when there is a message', () => {
    const { container, rerender } = render(<FieldError id="x-error" message="" />)
    expect(container).toBeEmptyDOMElement()
    rerender(<FieldError id="x-error" message="Required." />)
    expect(screen.getByText('Required.')).toHaveAttribute('id', 'x-error')
  })
})
