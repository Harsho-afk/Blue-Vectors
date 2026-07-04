import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Bell,
  BriefcaseBusiness,
  CheckCircle2,
  CircleDot,
  Clock3,
  FolderOpen,
  Plus,
  Search,
  Sparkles,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ThemeSwitch } from '@/components/theme-switch'

interface Case {
  id: number
  investigator_id: number
  title: string
  status: string
  created_at: string
  closed_at: string | null
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function StatCard({
  label,
  value,
  icon: Icon,
  accent = 'orange',
}: {
  label: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  accent?: 'orange' | 'green' | 'blue' | 'slate'
}) {
  const styles = {
    orange:
      'bg-orange-50 text-orange-600 ring-orange-100 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/20',
    green:
      'bg-emerald-50 text-emerald-600 ring-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20',
    blue: 'bg-sky-50 text-sky-600 ring-sky-100 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/20',
    slate:
      'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-700/40 dark:text-slate-300 dark:ring-slate-600',
  }

  return (
    <div className='rounded-xl border border-orange-100 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:border-white/10 dark:bg-slate-900'>
      <div className='flex items-center justify-between gap-4'>
        <div>
          <p className='text-sm font-medium text-slate-500 dark:text-slate-400'>
            {label}
          </p>
          <div className='mt-2 text-3xl font-bold text-slate-950 dark:text-white'>
            {value}
          </div>
        </div>
        <div className={cn('rounded-xl p-3 ring-1', styles[accent])}>
          <Icon className='size-5' />
        </div>
      </div>
    </div>
  )
}

function EmptyModule() {
  return (
    <section
      aria-label='Empty dashboard module'
      className='min-h-[220px] rounded-xl border border-dashed border-orange-200 bg-white/70 shadow-sm dark:border-slate-700 dark:bg-slate-900/70'
    />
  )
}

export function Dashboard() {
  const [cases, setCases] = useState<Case[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetch(`${API}/api/cases`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data) => setCases(data.cases || []))
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false))
  }, [])

  const stats = useMemo(() => {
    const open = cases.filter((c) => c.status === 'open').length
    const closed = cases.filter((c) => c.status === 'closed').length
    const inProgress = cases.filter(
      (c) => c.status !== 'open' && c.status !== 'closed'
    ).length

    return {
      total: isLoading ? '...' : cases.length,
      open: isLoading ? '...' : open,
      inProgress: isLoading ? '...' : inProgress,
      closed: isLoading ? '...' : closed,
    }
  }, [cases, isLoading])

  return (
    <div className='min-h-svh bg-orange-50/60 text-slate-950 dark:bg-slate-950 dark:text-white'>
      <Header className='border-b border-orange-100 bg-white/90 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/85'>
        <div className='flex min-w-0 flex-1 items-center gap-3'>
          <div className='flex min-w-0 flex-1 items-center gap-3 rounded-full border border-orange-100 bg-orange-50 px-4 py-2 dark:border-white/10 dark:bg-slate-900'>
            <Search className='size-4 shrink-0 text-orange-500' />
            <input
              className='min-w-0 flex-1 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500'
              placeholder='Search ARIA cases'
            />
          </div>
          <Button
            size='icon'
            variant='outline'
            className='rounded-full border-orange-100 bg-white text-slate-700 hover:bg-orange-50 dark:border-white/10 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800'
          >
            <Bell className='size-4' />
          </Button>
          <ThemeSwitch />
        </div>
      </Header>

      <Main fluid className='workspace-grid px-4 py-6 sm:px-8'>
        <section className='overflow-hidden rounded-2xl border border-orange-100 bg-white shadow-sm dark:border-white/10 dark:bg-slate-900'>
          <div className='grid gap-6 p-6 lg:grid-cols-[1fr_auto] lg:items-center'>
            <div>
              <div className='mb-4 inline-flex items-center gap-2 rounded-full bg-orange-100 px-3 py-1 text-sm font-semibold text-orange-700 dark:bg-orange-500/10 dark:text-orange-300'>
                <Sparkles className='size-4' />
                ARIA
              </div>
              <h1 className='max-w-3xl text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl dark:text-white'>
                Investigation dashboard
              </h1>
              <p className='mt-3 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-400'>
                Create investigations, review active cases, and keep the
                workspace ready for new intelligence modules.
              </p>
              {error && (
                <p className='mt-3 text-sm text-red-600 dark:text-red-400'>
                  Case API unavailable: {error}
                </p>
              )}
            </div>
            <div className='flex flex-wrap gap-3'>
              <Button
                className='bg-orange-500 text-white shadow-sm hover:bg-orange-600'
                onClick={() => navigate({ to: '/investigate' })}
              >
                <Plus className='size-4' />
                New investigation
              </Button>
              <Button
                variant='outline'
                className='border-orange-200 bg-white text-orange-700 hover:bg-orange-50 dark:border-orange-500/30 dark:bg-slate-900 dark:text-orange-300 dark:hover:bg-orange-500/10'
                onClick={() => navigate({ to: '/cases' })}
              >
                <FolderOpen className='size-4' />
                Cases
              </Button>
            </div>
          </div>
        </section>

        <div className='mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
          <StatCard
            label='Total cases'
            value={stats.total}
            icon={BriefcaseBusiness}
          />
          <StatCard
            label='Open cases'
            value={stats.open}
            icon={Clock3}
            accent='blue'
          />
          <StatCard
            label='In progress'
            value={stats.inProgress}
            icon={CircleDot}
            accent='slate'
          />
          <StatCard
            label='Closed cases'
            value={stats.closed}
            icon={CheckCircle2}
            accent='green'
          />
        </div>

        <div className='mt-6 grid gap-5 xl:grid-cols-[1.15fr_0.85fr]'>
          <section className='rounded-xl border border-orange-100 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-900'>
            <div className='mb-4 flex items-center justify-between gap-4'>
              <h2 className='text-lg font-semibold text-slate-950 dark:text-white'>
                Recent cases
              </h2>
              <Button
                variant='ghost'
                className='text-orange-700 hover:bg-orange-50 hover:text-orange-800 dark:text-orange-300 dark:hover:bg-orange-500/10'
                onClick={() => navigate({ to: '/cases' })}
              >
                View all
              </Button>
            </div>
            <div className='overflow-hidden rounded-lg border border-slate-100 dark:border-white/10'>
              <div className='grid grid-cols-[1.4fr_0.7fr_0.8fr] bg-orange-50 px-4 py-3 text-xs font-semibold tracking-wide text-slate-500 uppercase dark:bg-slate-800 dark:text-slate-400'>
                <span>Case</span>
                <span>Status</span>
                <span>Created</span>
              </div>
              {cases.slice(0, 5).map((c) => (
                <button
                  key={c.id}
                  className='grid w-full grid-cols-[1.4fr_0.7fr_0.8fr] border-t border-slate-100 px-4 py-3 text-left text-sm hover:bg-orange-50 dark:border-white/10 dark:hover:bg-slate-800'
                  onClick={() =>
                    navigate({ to: '/cases/$id', params: { id: String(c.id) } })
                  }
                >
                  <span className='truncate font-medium text-slate-900 dark:text-slate-100'>
                    {c.title}
                  </span>
                  <span className='text-slate-500 capitalize dark:text-slate-400'>
                    {c.status}
                  </span>
                  <span className='text-slate-500 dark:text-slate-400'>
                    {formatDate(c.created_at)}
                  </span>
                </button>
              ))}
              {!isLoading && cases.length === 0 && (
                <div className='flex min-h-[150px] flex-col items-center justify-center gap-3 text-center text-slate-500 dark:text-slate-400'>
                  <BriefcaseBusiness className='size-10 text-orange-400' />
                  <p>No cases yet.</p>
                  <Button
                    className='bg-orange-500 text-white hover:bg-orange-600'
                    onClick={() => navigate({ to: '/investigate' })}
                  >
                    Create first investigation
                  </Button>
                </div>
              )}
            </div>
          </section>

          <EmptyModule />
        </div>

        <div className='mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3'>
          <EmptyModule />
          <EmptyModule />
          <EmptyModule />
        </div>
      </Main>
    </div>
  )
}
