import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
}

export default function Modal({ open, onClose, title, children, size = 'md', closeOnOverlay = true, panelClassName = '' }) {
  const overlayRef = useRef(null)
  const panelRef = useRef(null)
  const prevFocus = useRef(null)

  useEffect(() => {
    if (!open) return
    prevFocus.current = document.activeElement
    const panel = panelRef.current
    if (panel) {
      const sel = 'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])'
      const focusable = panel.querySelector(sel)
      ;(focusable || panel).focus()
    }
    function onKey(e) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose?.()
      }
      if (e.key === 'Tab' && panel) {
        const sel = 'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])'
        const list = [...panel.querySelectorAll(sel)].filter(n => !n.disabled && n.offsetParent !== null)
        if (list.length === 0) return
        const first = list[0]
        const last = list[list.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey, true)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey, true)
      document.body.style.overflow = prevOverflow
      if (prevFocus.current && typeof prevFocus.current.focus === 'function') {
        prevFocus.current.focus()
      }
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={overlayRef}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] bg-black/70 flex items-center justify-center p-4"
          onClick={(e) => { if (closeOnOverlay && e.target === overlayRef.current) onClose?.() }}
        >
          <motion.div
            ref={panelRef}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className={`bg-zinc-900 border border-zinc-700 rounded-2xl w-full ${SIZES[size] || SIZES.md} shadow-2xl outline-none ${panelClassName}`}
            onClick={e => e.stopPropagation()}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
