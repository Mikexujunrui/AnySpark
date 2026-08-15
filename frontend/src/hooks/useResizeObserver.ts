import { useState, useEffect, useRef, type RefObject } from 'react'

interface Dimensions {
  w: number
  h: number
}

export function useResizeObserver(ref: RefObject<HTMLElement | null>): Dimensions {
  const [dimensions, setDimensions] = useState<Dimensions>({ w: 800, h: 500 })
  const observerRef = useRef<ResizeObserver | null>(null)

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