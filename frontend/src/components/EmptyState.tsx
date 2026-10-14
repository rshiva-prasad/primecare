import IconButton from './ui/IconButton'

interface EmptyStateProps {
  title: string
  message: string
  actionLabel: string
  onAction: () => void
}

function EmptyState({ title, message, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-5 text-center">
      <p className="font-semibold text-slate-900">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{message}</p>
      <div className="mt-4">
        <IconButton label={actionLabel} onClick={onAction} />
      </div>
    </div>
  )
}

export default EmptyState
