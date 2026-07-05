import { Link } from '@tanstack/react-router'
import { Menu, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
import { Button } from '../ui/button'

export function AppTitle() {
  const { setOpenMobile } = useSidebar()
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          size='lg'
          className='gap-0 py-0 hover:bg-transparent active:bg-transparent'
          asChild
        >
          <div>
            <Link
              to='/'
              onClick={() => setOpenMobile(false)}
              className='flex flex-1 items-center gap-3 text-start text-sm leading-tight'
            >
              {/* Logo image — no background, no crop */}
              <img
                src='/images/aria-logo.png'
                alt='ARIA logo'
                className='h-14 w-14 shrink-0 object-contain'
              />

              {/* Brand text */}
              <span className='grid min-w-0 group-data-[collapsible=icon]:hidden'>
                <span className='truncate text-base font-extrabold tracking-widest text-slate-950 uppercase dark:text-white'>
                  ARIA
                </span>
                <span className='truncate font-mono text-[0.6rem] font-semibold tracking-[0.28em] text-orange-500 uppercase dark:text-orange-400'>
                  Intelligence Platform
                </span>
              </span>
            </Link>
            <ToggleSidebar />
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>

      {/* Tagline — hidden when sidebar is icon-only */}
      <div className='mx-2 my-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 group-data-[collapsible=icon]:hidden dark:border-slate-700 dark:bg-slate-800/50'>
        <p className='text-[0.7rem] leading-relaxed text-slate-500 dark:text-slate-400'>
          Adaptive risk intelligence for{' '}
          <span className='font-semibold text-orange-500 dark:text-orange-400'>
            investigations
          </span>
          ,{' '}
          <span className='font-semibold text-orange-500 dark:text-orange-400'>
            cases
          </span>
          , and{' '}
          <span className='font-semibold text-orange-500 dark:text-orange-400'>
            evidence
          </span>
          .
        </p>
      </div>
    </SidebarMenu>
  )
}

function ToggleSidebar({
  className,
  onClick,
  ...props
}: React.ComponentProps<typeof Button>) {
  const { toggleSidebar } = useSidebar()

  return (
    <Button
      data-sidebar='trigger'
      data-slot='sidebar-trigger'
      variant='ghost'
      size='icon'
      className={cn('aspect-square size-8 max-md:scale-125', className)}
      onClick={(event) => {
        onClick?.(event)
        toggleSidebar()
      }}
      {...props}
    >
      <X className='md:hidden' />
      <Menu className='max-md:hidden' />
      <span className='sr-only'>Toggle Sidebar</span>
    </Button>
  )
}
