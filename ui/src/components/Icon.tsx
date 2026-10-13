import type { SVGProps } from 'react'

export type IconName =
  | 'activity'
  | 'arrow-right'
  | 'book'
  | 'check'
  | 'chevron-down'
  | 'chevron-right'
  | 'clock'
  | 'code'
  | 'external'
  | 'folder'
  | 'globe'
  | 'grid'
  | 'layers'
  | 'library'
  | 'menu'
  | 'refresh'
  | 'search'
  | 'settings'
  | 'shield'
  | 'spark'
  | 'terminal'
  | 'x'

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName
  size?: number
}

export function Icon({ name, size = 18, strokeWidth = 1.8, ...props }: IconProps) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    ...props,
  }

  switch (name) {
    case 'activity':
      return <svg {...common}><path d="M3 12h4l2.2-7 4.1 14 2.4-7H21" /></svg>
    case 'arrow-right':
      return <svg {...common}><path d="M5 12h13" /><path d="m13 6 6 6-6 6" /></svg>
    case 'book':
      return <svg {...common}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" /><path d="M4 5.5v16" /><path d="M8 7h8" /><path d="M8 11h7" /></svg>
    case 'check':
      return <svg {...common}><path d="m5 12 4 4L19 6" /></svg>
    case 'chevron-down':
      return <svg {...common}><path d="m6 9 6 6 6-6" /></svg>
    case 'chevron-right':
      return <svg {...common}><path d="m9 6 6 6-6 6" /></svg>
    case 'clock':
      return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3 2" /></svg>
    case 'code':
      return <svg {...common}><path d="m8 8-4 4 4 4" /><path d="m16 8 4 4-4 4" /><path d="m14 4-4 16" /></svg>
    case 'external':
      return <svg {...common}><path d="M14 5h5v5" /><path d="m19 5-8 8" /><path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" /></svg>
    case 'folder':
      return <svg {...common}><path d="M3.5 6.5h6l1.8 2H20.5v9a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z" /><path d="M3.5 9h17" /></svg>
    case 'globe':
      return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M3.8 9h16.4M3.8 15h16.4M12 3.5c2 2.2 3 5 3 8.5s-1 6.3-3 8.5c-2-2.2-3-5-3-8.5s1-6.3 3-8.5z" /></svg>
    case 'grid':
      return <svg {...common}><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></svg>
    case 'layers':
      return <svg {...common}><path d="m12 4 8 4-8 4-8-4z" /><path d="m4 12 8 4 8-4" /><path d="m4 16 8 4 8-4" /></svg>
    case 'library':
      return <svg {...common}><path d="M5 20V8" /><path d="M10 20V4" /><path d="M15 20v-8" /><path d="M20 20V6" /><path d="M3 20h19" /><path d="m4 8 4-2 4 2 4-2 4 2" /></svg>
    case 'menu':
      return <svg {...common}><path d="M4 7h16M4 12h16M4 17h16" /></svg>
    case 'refresh':
      return <svg {...common}><path d="M20 11a8 8 0 0 0-14.8-4L3 9" /><path d="M3 4v5h5" /><path d="M4 13a8 8 0 0 0 14.8 4L21 15" /><path d="M21 20v-5h-5" /></svg>
    case 'search':
      return <svg {...common}><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></svg>
    case 'settings':
      return <svg {...common}><path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z" /><path d="m19.4 15 .1.1a1.7 1.7 0 0 1-2.4 2.4l-.1-.1a1.7 1.7 0 0 0-2.9 1.2v.2a1.7 1.7 0 0 1-3.4 0v-.2a1.7 1.7 0 0 0-2.9-1.2l-.1.1a1.7 1.7 0 0 1-2.4-2.4l.1-.1A1.7 1.7 0 0 0 6.2 12a1.7 1.7 0 0 0-1.2-2.9h-.2a1.7 1.7 0 0 1 0-3.4H5A1.7 1.7 0 0 0 6.2 3l-.1-.1a1.7 1.7 0 0 1 2.4-2.4l.1.1A1.7 1.7 0 0 0 11.5 1h.2a1.7 1.7 0 0 1 3.4 0v.2A1.7 1.7 0 0 0 18 2.4l.1-.1a1.7 1.7 0 0 1 2.4 2.4l-.1.1A1.7 1.7 0 0 0 19.4 7v.1A1.7 1.7 0 0 0 21 8.8V9a1.7 1.7 0 0 1 0 3.4h-.2a1.7 1.7 0 0 0-1.4 2.6Z" transform="translate(0 5) scale(.58)" /></svg>
    case 'shield':
      return <svg {...common}><path d="M12 3.5 19 6v5.3c0 4.2-2.8 7.6-7 9.2-4.2-1.6-7-5-7-9.2V6z" /><path d="m8.5 12 2.2 2.2 4.8-4.8" /></svg>
    case 'spark':
      return <svg {...common}><path d="m12 3 1.3 5.7L19 10l-5.7 1.3L12 17l-1.3-5.7L5 10l5.7-1.3z" /><path d="m19 16 .5 2.5L22 19l-2.5.5L19 22l-.5-2.5L16 19l2.5-.5z" /></svg>
    case 'terminal':
      return <svg {...common}><rect x="3.5" y="5" width="17" height="14" rx="2" /><path d="m7 10 2 2-2 2M12 14h4" /></svg>
    case 'x':
      return <svg {...common}><path d="m6 6 12 12M18 6 6 18" /></svg>
    default:
      return null
  }
}
