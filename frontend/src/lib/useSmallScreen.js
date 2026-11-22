// Phone-sized screens (under Tailwind's `sm`, 640px): coding and whiteboard rounds
// are hidden or simplified there (T-150).
import { useEffect, useState } from 'react'

const QUERY = '(max-width: 639px)'
export const HANDS_ON = ['coding', 'system_design']

export function isSmallScreen() {
  return typeof window !== 'undefined' && Boolean(window.matchMedia?.(QUERY).matches)
}

export function useSmallScreen() {
  const [small, setSmall] = useState(isSmallScreen)
  useEffect(() => {
    const mq = window.matchMedia?.(QUERY)
    if (!mq) return
    const onChange = () => setSmall(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])
  return small
}
