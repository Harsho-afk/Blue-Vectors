import { Link } from '@tanstack/react-router'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'

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
          <Link
            to='/'
            onClick={() => setOpenMobile(false)}
            className='flex flex-1 items-center gap-3 text-start text-sm leading-tight'
          >
            <img
              src='/images/aria-logo.png'
              alt='ARIA logo'
              className='h-14 w-14 shrink-0 object-contain'
            />
            <span className='grid min-w-0 group-data-[collapsible=icon]:hidden'>
              <span className='truncate text-base font-extrabold tracking-widest text-slate-950 uppercase dark:text-white'>
                ARIA
              </span>
              <span className='font-mono text-[0.6rem] font-semibold tracking-[0.15em] text-orange-500 uppercase dark:text-orange-400'>
                Intelligence Platform
              </span>
            </span>
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>

      <div className='mx-2 my-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 group-data-[collapsible=icon]:hidden dark:border-slate-700 dark:bg-slate-800/50'>
        <p className='text-[0.7rem] leading-relaxed text-slate-500 dark:text-slate-400'>
          Adaptive risk intelligence for{' '}
          <span className='font-semibold text-orange-500 dark:text-orange-400'>investigations</span>
          ,{' '}
          <span className='font-semibold text-orange-500 dark:text-orange-400'>cases</span>
          , and{' '}
          <span className='font-semibold text-orange-500 dark:text-orange-400'>evidence</span>.
        </p>
      </div>
    </SidebarMenu>
  )
}
