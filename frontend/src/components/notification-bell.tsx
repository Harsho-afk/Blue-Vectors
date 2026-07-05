import { useCallback, useEffect, useState } from 'react'
import {
  Bell,
  Check,
  CheckCheck,
  Loader2,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'

interface Alert {
  id: number
  case_id: number
  title: string
  message: string
  priority: string
  status: string
  created_at: string
}

export function NotificationBell() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const fetchAlerts = useCallback(() => {
    setLoading(true)
    fetch(`${API}/api/alerts?limit=20`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : { alerts: [], unread: 0 }))
      .then((data) => {
        setAlerts(data.alerts || [])
        setUnread(data.unread || 0)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchAlerts()
    const interval = setInterval(fetchAlerts, 30_000)
    return () => clearInterval(interval)
  }, [fetchAlerts])

  const markRead = (alertId: number) => {
    fetch(`${API}/api/alerts/${alertId}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'read' }),
    }).then(() => fetchAlerts())
  }

  const markAllRead = () => {
    fetch(`${API}/api/alerts/mark-all-read`, {
      method: 'POST',
      credentials: 'include',
    }).then(() => fetchAlerts())
  }

  const priorityDot: Record<string, string> = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    normal: 'bg-blue-500',
    low: 'bg-gray-400',
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant='ghost' size='icon' className='relative'>
          <Bell className='size-4' />
          {unread > 0 && (
            <span className='absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white'>
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-80 p-0' align='end'>
        <div className='flex items-center justify-between border-b px-4 py-3'>
          <h4 className='text-sm font-semibold'>Notifications</h4>
          {unread > 0 && (
            <Button
              variant='ghost'
              size='sm'
              className='h-6 text-xs'
              onClick={markAllRead}
            >
              <CheckCheck className='mr-1 size-3' />
              Mark all read
            </Button>
          )}
        </div>

        <ScrollArea className='max-h-80'>
          {loading && alerts.length === 0 ? (
            <div className='flex justify-center py-8'>
              <Loader2 className='size-4 animate-spin' />
            </div>
          ) : alerts.length === 0 ? (
            <div className='py-8 text-center text-sm text-muted-foreground'>
              No notifications yet
            </div>
          ) : (
            <div className='divide-y'>
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`flex items-start gap-3 px-4 py-3 transition-colors ${
                    alert.status === 'unread'
                      ? 'bg-accent/30'
                      : ''
                  }`}
                >
                  <span
                    className={`mt-1.5 size-2 shrink-0 rounded-full ${priorityDot[alert.priority] || priorityDot.normal}`}
                  />
                  <div className='min-w-0 flex-1'>
                    <p className='truncate text-sm font-medium'>
                      {alert.title}
                    </p>
                    <p className='mt-0.5 text-xs text-muted-foreground'>
                      {timeAgo(alert.created_at)}
                      {' · '}
                      Case #{alert.case_id}
                    </p>
                  </div>
                  {alert.status === 'unread' && (
                    <Button
                      variant='ghost'
                      size='icon'
                      className='size-6 shrink-0'
                      onClick={() => markRead(alert.id)}
                    >
                      <Check className='size-3' />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}
