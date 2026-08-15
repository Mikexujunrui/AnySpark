export default function Toggle({ checked, onChange, label = '', hint = '', disabled = false }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className="flex items-center gap-2.5 group disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <span
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200 ${
          checked ? 'bg-accent' : 'bg-zinc-700 group-hover:bg-zinc-600'
        }`}
      >
        <span
          className="inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform duration-200"
          style={{ transform: checked ? 'translateX(18px)' : 'translateX(3px)' }}
        />
      </span>
      {label && (
        <span className="flex flex-col text-left">
          <span className="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors">{label}</span>
          {hint && <span className="text-[11px] text-zinc-500">{hint}</span>}
        </span>
      )}
    </button>
  )
}
