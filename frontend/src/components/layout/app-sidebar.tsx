import { useAuth } from '@/context/auth-context'
import { useLayout } from '@/context/layout-provider'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from '@/components/ui/sidebar'
import { AppTitle } from './app-title'
import { sidebarData } from './data/sidebar-data'
import { NavGroup } from './nav-group'
import { NavUser } from './nav-user'

export function AppSidebar() {
  const { collapsible, variant } = useLayout()
  const { user } = useAuth()

  const sidebarUser = {
    name: user?.full_name || 'User',
    email: user?.email || '',
    avatar: '',
  }

  return (
    <Sidebar
      collapsible={collapsible}
      variant={variant}
      className='border-r border-orange-100 bg-white dark:border-white/10 dark:bg-slate-950'
    >
      <SidebarHeader className='border-b border-orange-100 p-4 dark:border-white/10'>
        <AppTitle />
      </SidebarHeader>
      <SidebarContent className='bg-white px-2 py-4 dark:bg-slate-950'>
        {sidebarData.navGroups.map((props) => (
          <NavGroup key={props.title} {...props} />
        ))}
      </SidebarContent>
      <SidebarFooter className='border-t border-orange-100 bg-white p-3 dark:border-white/10 dark:bg-slate-950'>
        <NavUser user={sidebarUser} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
