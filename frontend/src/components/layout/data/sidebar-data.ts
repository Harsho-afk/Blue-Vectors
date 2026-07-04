import { FolderOpen, LayoutDashboard, Search } from 'lucide-react'
import { type SidebarData } from '../types'

export const sidebarData: SidebarData = {
  user: {
    name: 'User',
    email: '',
    avatar: '',
  },
  teams: [],
  navGroups: [
    {
      title: 'General',
      items: [
        {
          title: 'Dashboard',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          title: 'New Investigation',
          url: '/investigate',
          icon: Search,
        },
        {
          title: 'Cases',
          url: '/cases',
          icon: FolderOpen,
        },
      ],
    },
  ],
}
