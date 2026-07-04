import { Link } from '@tanstack/react-router'
import { Menu, Sparkles, X } from 'lucide-react'
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
              <span className='flex size-11 shrink-0 items-center justify-center rounded-xl bg-orange-100 text-orange-600 dark:bg-orange-500/10 dark:text-orange-300'>
                <Sparkles className='size-6' />
              </span>
              <span className='grid min-w-0'>
                <span className='truncate font-bold tracking-wide text-slate-950 uppercase dark:text-white'>
                  ARIA
                </span>
                <span className='truncate font-mono text-[0.65rem] tracking-[0.22em] text-orange-500 uppercase dark:text-orange-300'>
                  Intelligence Workspace
                </span>
              </span>
            </Link>
            <ToggleSidebar />
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <p className='px-2 pt-3 text-xs leading-relaxed text-slate-500 group-data-[collapsible=icon]:hidden dark:text-slate-400'>
        Adaptive risk intelligence for investigations, cases, and evidence.
      </p>
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
