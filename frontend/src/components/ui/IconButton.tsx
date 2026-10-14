import { ArrowRight } from 'lucide-react'

interface IconButtonProps {
  label: string
  onClick?: () => void
  type?: 'button' | 'submit'
  disabled?: boolean
  loading?: boolean
}

function IconButton({
  label,
  onClick,
  type = 'button',
  disabled = false,
  loading = false,
}: IconButtonProps) {
  const isDisabled = disabled || loading

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      aria-busy={loading}
      className={`group inline-flex w-full items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-colors hover:bg-teal-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 active:bg-teal-800 ${isDisabled ? 'cursor-not-allowed opacity-60' : ''}`}
    >
      {label}
      {loading ? (
        <span
          aria-hidden="true"
          className="ms-1 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      ) : (
        <ArrowRight
          size={16}
          strokeWidth={2}
          aria-hidden="true"
          className="-me-1 ms-1 opacity-80 transition-transform duration-200 group-hover:translate-x-0.5"
        />
      )}
    </button>
  )
}

export default IconButton
