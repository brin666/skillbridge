import type { SVGProps } from 'react'

interface HarnessIconProps extends SVGProps<SVGSVGElement> {
  id: string
  size?: number
}

// Compact vector marks for the Hub; no font-dependent characters or remote assets.
export function HarnessIcon({ id, size = 24, ...props }: HarnessIconProps) {
  const common = {
    width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: 1.65,
    strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
    'aria-hidden': true, focusable: false, ...props,
  }
  switch (id.toLowerCase()) {
    case 'codex':
      return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="4" /><path d="m7.5 9 3 3-3 3M13 15h4" /></svg>
    case 'hermes':
      return <svg {...common}><path d="M8.5 8v9M15.5 8v9M8.5 12h7M8.5 10 3 5v5l5.5 4M15.5 10 21 5v5l-5.5 4M6 19h12" /><path d="m3 8 5.5 4M21 8l-5.5 4" /></svg>
    case 'claude':
      return <svg {...common}>{Array.from({ length: 12 }, (_, index) => <path key={index} d="M12 3v5" transform={`rotate(${index * 30} 12 12)`} />)}<circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" /></svg>
    case 'dsh':
    case 'deepseek':
      return <svg {...common}><path d="M3 10c3-1 5-1 7 1 3 3 7 2 8-2l3-2-1 5c-1 5-5 7-10 5-4-1-6-3-7-7Z" /><path d="m15 9 2-4 1 5M7 9 5 6M7 13h.01" /></svg>
    case 'cursor':
      return <svg {...common}><path d="m5 3 14 9-7 1-3 7Z" /></svg>
    case 'gemini':
      return <svg {...common}><path d="M12 2c1 6 4 9 10 10-6 1-9 4-10 10-1-6-4-9-10-10 6-1 9-4 10-10Z" /></svg>
    default:
      return <svg {...common}><rect x="4" y="4" width="16" height="16" rx="5" /><path d="m9 9-3 3 3 3m6-6 3 3-3 3" /></svg>
  }
}
