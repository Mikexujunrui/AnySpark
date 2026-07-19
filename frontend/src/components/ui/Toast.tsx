import { useState, useEffect, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { listeners } from './toast-utils'

export default function Toast() {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((toast) => {
    setToasts(prev => [...prev, toast])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toast.id))
    }, toast.duration)
  }, [])

  useEffect(() => {
    listeners.add(addToast)
    return () => { listeners.delete(addToast) }
  }, [addToast])

  function remove(id) {
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  const colors = {
    info: 'border-zinc-600 bg-zinc-800 text-zinc-200',
    success: 'border-emerald-700 bg-emerald-950/80 text-emerald-300',
    error: 'border-red-700 bg-red-950/80 text-red-300',
    warning: 'border-amber-700 bg-amber-950/80 text-amber-300',
  }

  return (
    <div className="fixed top-4 right-4 z-[200] space-y-2 max-w-sm">
      <AnimatePresence>
        {toasts.map(t => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, x: 50, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 50, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className={`border rounded-xl px-4 py-3 text-sm shadow-lg ${colors[t.type] || colors.info}`}
          >
            <div className="flex items-center gap-2">
              <span className="flex-1">{t.message}</span>
              {t.undoAction && (
                <button
                  onClick={(e) => { e.stopPropagation(); t.undoAction(); remove(t.id) }}
                  className="text-xs font-medium underline hover:opacity-80 shrink-0"
                >撤销</button>
              )}
              <button onClick={() => remove(t.id)} className="text-zinc-500 hover:text-zinc-300 shrink-0 ml-1">×</button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
