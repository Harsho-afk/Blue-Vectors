import { useEffect, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Plus, Search } from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { Input } from '@/components/ui/input'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search as SearchBar } from '@/components/search'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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

export const Route = createFileRoute('/_authenticated/cases/')({
  component: Cases,
})

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

function Cases() {
  const [cases, setCases] = useState<Case[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
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

  const filtered = cases.filter((c) => {
    const matchesSearch = c.title
      .toLowerCase()
      .includes(search.toLowerCase())
    const matchesStatus =
      statusFilter === 'all' || c.status === statusFilter
    return matchesSearch && matchesStatus
  })

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
            <h1 className='text-2xl font-bold tracking-tight'>Cases</h1>
            <p className='text-muted-foreground'>
              All investigations in your workspace
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

        {/* Toolbar */}
        <div className='mt-4 flex items-center gap-3'>
          <div className='relative flex-1'>
            <Search className='absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
            <Input
              placeholder='Search cases...'
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className='pl-8'
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className='w-[160px]'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>All Statuses</SelectItem>
              <SelectItem value='open'>Open</SelectItem>
              <SelectItem value='closed'>Closed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Count */}
        {!isLoading && cases.length > 0 && (
          <p className='mt-3 text-xs text-muted-foreground'>
            Showing {filtered.length} of {cases.length} cases
          </p>
        )}

        {/* Table */}
        <Card className='mt-3'>
          <CardContent className='p-0'>
            {isLoading ? (
              <div className='space-y-3 p-6'>
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
            ) : filtered.length === 0 ? (
              <div className='flex flex-col items-center justify-center py-12 text-center'>
                <p className='text-sm text-muted-foreground'>
                  No cases match your search.
                </p>
                <Button
                  variant='outline'
                  size='sm'
                  className='mt-3'
                  onClick={() => {
                    setSearch('')
                    setStatusFilter('all')
                  }}
                >
                  Clear filters
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Closed</TableHead>
                    <TableHead className='text-right'>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((c) => (
                    <TableRow
                      key={c.id}
                      className='cursor-pointer'
                      onClick={() =>
                        navigate({
                          to: '/cases/$id',
                          params: { id: String(c.id) },
                        })
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
                      <TableCell>{formatDate(c.created_at)}</TableCell>
                      <TableCell>
                        {c.closed_at ? (
                          formatDate(c.closed_at)
                        ) : (
                          <span className='text-muted-foreground'>—</span>
                        )}
                      </TableCell>
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
