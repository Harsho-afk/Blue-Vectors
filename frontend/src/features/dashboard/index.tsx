import { useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  FolderOpen,
  Activity,
  CheckCircle,
  TrendingUp,
  Plus,
  Search,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search as SearchBar } from '@/components/search'
import { Skeleton } from '@/components/ui/skeleton'
import { ThemeSwitch } from '@/components/theme-switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Case {
  id: number
  investigator_id: number
  title: string
  status: string
  created_at: string
  closed_at: string | null
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function padId(id: number) {
  return `CASE-${String(id).padStart(4, '0')}`
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

  const openCases = cases.filter((c) => c.status === 'open')
  const closedCases = cases.filter((c) => c.status === 'closed')
  const sevenDaysAgo = new Date()
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)
  const thisWeek = cases.filter((c) => new Date(c.created_at) > sevenDaysAgo)

  return (
    <>
      <Header>
        <SearchBar className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main>
        <div className='mb-2 flex items-center justify-between space-y-2'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>Dashboard</h1>
            <p className='text-muted-foreground'>
              Overview of your investigations
            </p>
          </div>
          <Button onClick={() => navigate({ to: '/investigate' })}>
            <Plus />
            New Investigation
          </Button>
        </div>

        {error && (
          <div className='mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'>
            Failed to load cases: {error}
          </div>
        )}

        {/* Stat Cards */}
        <div className='mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
          {isLoading ? (
            <>
              {Array.from({ length: 4 }).map((_, i) => (
                <Card key={i}>
                  <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                    <Skeleton className='h-4 w-24' />
                    <Skeleton className='h-4 w-4' />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className='mb-1 h-7 w-16' />
                    <Skeleton className='h-3 w-32' />
                  </CardContent>
                </Card>
              ))}
            </>
          ) : (
            <>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    Total Cases
                  </CardTitle>
                  <FolderOpen className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>{cases.length}</div>
                  <p className='text-xs text-muted-foreground'>
                    All investigations
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    Active Investigations
                  </CardTitle>
                  <Activity className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>{openCases.length}</div>
                  <p className='text-xs text-muted-foreground'>Currently open</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    Closed Cases
                  </CardTitle>
                  <CheckCircle className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>
                    {closedCases.length}
                  </div>
                  <p className='text-xs text-muted-foreground'>Completed</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-sm font-medium'>
                    Opened This Week
                  </CardTitle>
                  <TrendingUp className='h-4 w-4 text-muted-foreground' />
                </CardHeader>
                <CardContent>
                  <div className='text-2xl font-bold'>{thisWeek.length}</div>
                  <p className='text-xs text-muted-foreground'>Last 7 days</p>
                </CardContent>
              </Card>
            </>
          )}
        </div>

        {/* Recent Investigations */}
        <Card className='mt-4'>
          <CardHeader>
            <CardTitle>Recent Investigations</CardTitle>
            <CardDescription>
              Your {Math.min(cases.length, 10)} most recent cases
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className='space-y-3'>
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className='h-10 w-full' />
                ))}
              </div>
            ) : cases.length === 0 ? (
              <div className='flex flex-col items-center justify-center py-12 text-center'>
                <Search className='mb-4 h-12 w-12 text-muted-foreground/50' />
                <h3 className='text-lg font-medium'>No investigations yet</h3>
                <p className='mt-1 text-sm text-muted-foreground'>
                  Start your first investigation to see it here.
                </p>
                <Button
                  className='mt-4'
                  onClick={() => navigate({ to: '/investigate' })}
                >
                  <Plus />
                  Start your first investigation
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Identifiers</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className='text-right'>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cases.slice(0, 10).map((c) => (
                    <TableRow
                      key={c.id}
                      className='cursor-pointer'
                      onClick={() =>
                        navigate({ to: '/cases/$id', params: { id: String(c.id) } })
                      }
                    >
                      <TableCell>
                        <div className='font-medium'>{c.title}</div>
                        <div className='text-xs text-muted-foreground'>
                          {padId(c.id)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            c.status === 'open' ? 'default' : 'secondary'
                          }
                        >
                          {c.status}
                        </Badge>
                      </TableCell>
                      <TableCell className='text-muted-foreground'>
                        —
                      </TableCell>
                      <TableCell>{formatDate(c.created_at)}</TableCell>
                      <TableCell className='text-right'>
                        <Button
                          variant='outline'
                          size='sm'
                          onClick={(e) => {
                            e.stopPropagation()
                            navigate({
                              to: '/cases/$id',
                              params: { id: String(c.id) },
                            })
                          }}
                        >
                          View
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
