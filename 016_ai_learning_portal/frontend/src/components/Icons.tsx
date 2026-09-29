// 画面で使う線画アイコン(文字色を継承する)
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function base(size: number, props: SVGProps<SVGSVGElement>) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    ...props,
  }
}

export const PlayIcon = ({ size = 14, ...p }: IconProps) => (
  <svg {...base(size, p)} fill="currentColor" stroke="none">
    <polygon points="6 4 20 12 6 20 6 4" />
  </svg>
)

export const StopIcon = ({ size = 14, ...p }: IconProps) => (
  <svg {...base(size, p)} fill="currentColor" stroke="none">
    <rect x="6" y="6" width="12" height="12" rx="1.5" />
  </svg>
)

export const CheckIcon = ({ size = 14, ...p }: IconProps) => (
  <svg {...base(size, p)} strokeWidth={2.5}>
    <polyline points="4 12 10 18 20 6" />
  </svg>
)

export const ResetIcon = ({ size = 14, ...p }: IconProps) => (
  <svg {...base(size, p)}>
    <path d="M4 11a8 8 0 1 1 2.3 5.7" />
    <polyline points="4 4 4 11 11 11" />
  </svg>
)
