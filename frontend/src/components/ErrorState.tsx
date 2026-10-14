interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="rounded-lg bg-red-50 px-3 py-3 text-sm text-red-600">
      <p>{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="mt-2 font-semibold underline">
          Try again
        </button>
      ) : null}
    </div>
  )
}

export default ErrorState
