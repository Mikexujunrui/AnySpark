/** Reusable empty state with icon, title, description, and optional action button. */
import Icon from './Icon.jsx'

export default function EmptyState({
  icon = 'file-text',
  title,
  description,
  action,
  actionLabel,
  size = 'md',
}) {
  const iconSizes = { sm: 28, md: 36, lg: 48 }

  return (
    <div className="flex flex-col items-center justify-center h-full text-zinc-500 gap-3 px-6 py-12">
      <div className="rounded-2xl bg-zinc-800/40 p-4 mb-1">
        <Icon name={icon} size={iconSizes[size] || 36} className="text-zinc-600" />
      </div>
      {title && <p className="text-zinc-400 font-medium text-sm">{title}</p>}
      {description && <p className="text-zinc-600 text-xs text-center max-w-xs leading-relaxed">{description}</p>}
      {action && actionLabel && (
        <button
          onClick={action}
          className="mt-2 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-4 py-2 rounded-lg transition-colors border border-zinc-700 hover:border-zinc-600"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}
