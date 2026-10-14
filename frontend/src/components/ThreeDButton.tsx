interface ThreeDButtonProps {
  label: string
  onClick?: () => void
  variant: 'primary' | 'secondary'
  type?: 'button' | 'submit'
  disabled?: boolean
  loading?: boolean
}

function ThreeDButton({
  label,
  onClick,
  variant,
  type = 'button',
  disabled = false,
  loading = false,
}: ThreeDButtonProps) {
  const isDisabled = disabled || loading

  const baseClass =
    'w-full rounded-lg px-4 py-2.5 font-semibold transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 active:translate-y-[2px]'

  const variantClass =
    variant === 'primary'
      ? 'border-b-4 border-teal-800 bg-teal-600 text-white shadow-md hover:bg-teal-700 active:border-b-0 active:shadow-sm'
      : 'border-b-4 border-slate-300 bg-white text-slate-700 shadow-md hover:bg-slate-50 active:border-b-0 active:shadow-sm'

  const disabledClass = isDisabled
    ? 'cursor-not-allowed opacity-60 active:translate-y-0'
    : 'cursor-pointer'

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      aria-disabled={isDisabled}
      aria-busy={loading}
      className={`${baseClass} ${variantClass} ${disabledClass}`}
    >
      {loading ? (
        <span className="flex items-center justify-center gap-2">
          <span
            aria-hidden="true"
            className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          {label}
        </span>
      ) : (
        label
      )}
    </button>
  )
}

export default ThreeDButton
