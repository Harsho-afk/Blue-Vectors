import { type SVGProps } from 'react'
import { cn } from '@/lib/utils'

export function IconYoutube({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      role='img'
      viewBox='0 0 24 24'
      xmlns='http://www.w3.org/2000/svg'
      width='24'
      height='24'
      className={cn('[&>path]:stroke-current', className)}
      fill='none'
      stroke='currentColor'
      strokeWidth='2'
      strokeLinecap='round'
      strokeLinejoin='round'
      {...props}
    >
      <title>YouTube</title>
      <path strokeWidth='0' d='M0 0h24v24H0z' fill='none' />
      <path d='M10 9l5 3l-5 3z' fill='currentColor' stroke='none' />
      <path d='M21 12c0 -2.6 -.3 -4.2 -.8 -4.9a2.8 2.8 0 0 0 -1.9 -1.1c-2.2 -.3 -6.3 -.4 -9.3 -.4s-7.1 .1 -9.3 .4a2.8 2.8 0 0 0 -1.9 1.1c-.5 .7 -.8 2.3 -.8 4.9s.3 4.2 .8 4.9a2.8 2.8 0 0 0 1.9 1.1c2.2 .3 6.3 .4 9.3 .4s7.1 -.1 9.3 -.4a2.8 2.8 0 0 0 1.9 -1.1c.5 -.7 .8 -2.3 .8 -4.9z' />
    </svg>
  )
}