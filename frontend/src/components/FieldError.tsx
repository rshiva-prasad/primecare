interface FieldErrorProps {
  id: string
  message: string
}

function FieldError({ id, message }: FieldErrorProps) {
  if (!message) {
    return null
  }
  return (
    <p id={id} className="mt-1 text-sm text-red-600">
      {message}
    </p>
  )
}

export default FieldError
