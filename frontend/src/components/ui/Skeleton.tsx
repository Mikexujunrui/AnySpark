export function SkeletonLine({ className = '' }) {
  return <div className={`h-3 bg-zinc-800 rounded animate-pulse ${className}`} />
}

export function SkeletonCard({ className = '' }) {
  return (
    <div className={`rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3 ${className}`}>
      <SkeletonLine className="w-3/4 h-4" />
      <SkeletonLine className="w-full" />
      <SkeletonLine className="w-5/6" />
      <SkeletonLine className="w-1/2" />
    </div>
  )
}

export function SkeletonList({ count = 5, className = '' }) {
  return (
    <div className={`space-y-2 p-6 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-zinc-800 animate-pulse shrink-0" />
          <div className="flex-1 space-y-1.5">
            <SkeletonLine className="w-2/3 h-3" />
            <SkeletonLine className="w-1/3 h-2" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function SkeletonGrid({ count = 6, className = '' }) {
  return (
    <div className={`grid grid-cols-2 md:grid-cols-3 gap-4 p-6 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

export function SkeletonSidebar({ count = 6, className = '' }) {
  return (
    <div className={`h-full flex ${className}`}>
      <div className="w-56 border-r border-zinc-800 bg-zinc-950/50 shrink-0">
        <div className="p-3 border-b border-zinc-800 space-y-2">
          <SkeletonLine className="w-20 h-3" />
          <SkeletonLine className="w-full h-7 rounded-lg" />
        </div>
        <div className="p-2 space-y-1">
          {Array.from({ length: count }).map((_, i) => (
            <div key={i} className="px-3 py-2 space-y-1.5">
              <SkeletonLine className="w-3/4 h-3" />
              <SkeletonLine className="w-1/2 h-2" />
            </div>
          ))}
        </div>
      </div>
      <div className="flex-1 p-6 space-y-4 animate-pulse">
        <div className="h-6 bg-zinc-800 rounded w-1/3" />
        <div className="space-y-2">
          <div className="h-3 bg-zinc-800/60 rounded w-full" />
          <div className="h-3 bg-zinc-800/60 rounded w-full" />
          <div className="h-3 bg-zinc-800/60 rounded w-5/6" />
          <div className="h-3 bg-zinc-800/60 rounded w-full" />
          <div className="h-3 bg-zinc-800/60 rounded w-4/6" />
        </div>
      </div>
    </div>
  )
}

export function SkeletonCharGrid({ count = 8, className = '' }) {
  return (
    <div className={`flex-1 overflow-y-auto p-6 ${className}`}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 animate-pulse">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-zinc-800" />
              <div className="flex-1 space-y-1.5">
                <SkeletonLine className="w-2/3 h-3" />
                <SkeletonLine className="w-1/2 h-2" />
              </div>
            </div>
            <SkeletonLine className="w-full h-2" />
            <SkeletonLine className="w-4/5 h-2 mt-1.5" />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function LoadingState({ text = '加载中...', className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center py-16 text-zinc-500 ${className}`}>
      <div className="w-6 h-6 border-2 border-zinc-700 border-t-accent rounded-full animate-spin mb-3" />
      <span className="text-sm">{text}</span>
    </div>
  )
}
