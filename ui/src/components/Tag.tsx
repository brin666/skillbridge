import type { ReactNode } from 'react'

interface TagProps {
  children: ReactNode
  tone?: 'default' | 'accent' | 'success' | 'muted'
}

export function Tag({ children, tone = 'default' }: TagProps) {
  return <span className={`tag tag--${tone}`}>{children}</span>
}
