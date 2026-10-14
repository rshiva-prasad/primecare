import type { ReactNode } from 'react'

interface FormSectionProps {
  title: string
  subtitle?: string
  icon?: ReactNode
  children: ReactNode
}

function FormSection({ title, subtitle, icon, children }: FormSectionProps) {
  return (
    <section
      aria-label={title}
      className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
    >
      <header className="text-center">
        <div
          aria-hidden={icon ? undefined : true}
          className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-teal-600 text-xl font-bold text-white"
        >
          {icon ?? 'P'}
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-800">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
      </header>
      <div className="mt-6">{children}</div>
    </section>
  )
}

export default FormSection
