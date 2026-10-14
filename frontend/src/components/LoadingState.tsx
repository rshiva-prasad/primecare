interface LoadingStateProps {
  label: string
  fullPage?: boolean
}

function LoadingState({ label, fullPage = false }: LoadingStateProps) {
  const indicator = (
    <div
      role="status"
      className="flex items-center justify-center gap-2 py-6 text-sm text-slate-500"
    >
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-spin rounded-full border-2 border-teal-600 border-t-transparent"
      />
      {label}
    </div>
  )

  if (!fullPage) {
    return indicator
  }
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      {indicator}
    </div>
  )
}

export default LoadingState
