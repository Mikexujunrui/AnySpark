import { useState, useEffect, useRef } from 'react'

export function useResizeObserver(ref) {
  const [dimensions, setDimensions] = useState({ w: 800, h: 500 })
  const observerRef = useRef(null)

  useEffect(() => {
    const element = ref?.current
    if (!element) return

    observerRef.current = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setDimensions({ w: Math.floor(width) || 800, h: Math.floor(height) || 500 })
      }
    })

    observerRef.current.observe(element)

    return () => {
      observerRef.current?.disconnect()
    }
  }, [ref])

  return dimensions
}
