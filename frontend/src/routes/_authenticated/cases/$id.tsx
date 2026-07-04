import { useCallback, useEffect, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import {
  Activity,
  ArrowLeft,
  Calendar,
  ChevronDown,
  Download,
  ExternalLink,
  GitMerge,
  Loader2,
  MapPin,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import { API } from '@/lib/aria-api'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ConfigDrawer } from '@/components/config-drawer'
import { CorrelationResults } from '@/components/correlation-results'
import { Header } from '@/components/layout/header'
import { Input } from '@/components/ui/input'
import { Main } from '@/components/layout/main'
import { OsintPanel } from '@/components/osint-panel'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search as SearchBar } from '@/components/search'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ThemeSwitch } from '@/components/theme-switch'

export const Route = createFileRoute('/_authenticated/cases/$id')({
  component: CaseDetail,
})

// ── Types ──

interface CaseInfo {
  id: number
  investigator_id: number
  title: string
  status: string
  created_at: string
  closed_at: string | null
}

interface Identifier {
  id: number
  case_id: number
  identifier_type: string
  value: string
  platform_hint: string | null
  created_at: string
}

interface Post {
  id: number
  account_id: number
  external_id: string
  text: string
  timestamp: string
  metadata: Record<string, unknown>
}

interface Account {
  id: number
  case_id: number
  platform: string
  username: string
  display_name: string | null
  bio: string | null
  location: string | null
  created_at: string | null
  profile_image_url: string | null
  karma?: number
  follower_count?: number
  following_count?: number
  posts: Post[]
}

interface CorrelationResult {
  id: number
  case_id: number
  account_a_id: number
  account_b_id: number
  confidence: number
  shap_json: Record<string, unknown>
  created_at: string
}

// ── Helpers ──

const IDENTIFIER_TYPES = [
  { value: 'username', label: 'Username' },
  { value: 'email', label: 'Email' },
  { value: 'phone', label: 'Phone' },
  { value: 'profile_url', label: 'Profile URL' },
] as const

const PLATFORMS = [
  { value: 'reddit', label: 'Reddit' },
  { value: 'twitter', label: 'Twitter' },
  { value: 'github', label: 'GitHub' },
  { value: 'instagram', label: 'Instagram' },
] as const

const PLACEHOLDERS: Record<string, string> = {
  username: 'e.g. johndoe',
  email: 'e.g. johndoe@example.com',
  phone: 'e.g. +1234567890',
  profile_url: 'e.g. https://reddit.com/u/johndoe',
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatTimestamp(ts: string | number) {
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
  if (isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function padId(id: number) {
  return `CASE-${String(id).padStart(4, '0')}`
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function platformHandle(platform: string, username: string) {
  switch (platform) {
    case 'twitter':
    case 'instagram':
      return `@${username}`
    case 'github':
      return `github.com/${username}`
    default:
      return `u/${username}`
  }
}

// ── Add-Identifier Row Type ──

interface IdRow {
  identifier_type: string
  value: string
  platform_hint: string
}

const EMPTY_ROW: IdRow = {
  identifier_type: 'username',
  value: '',
  platform_hint: '',
}

// ── Component ──

function CaseDetail() {
  const { id } = Route.useParams()
  const navigate = useNavigate()

  // Data state
  const [caseData, setCaseData] = useState<CaseInfo | null>(null)
  const [identifiers, setIdentifiers] = useState<Identifier[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [correlationResults, setCorrelationResults] = useState<
    CorrelationResult[]
  >([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Action state
  const [collecting, setCollecting] = useState<Record<number, boolean>>({})
  const [isCorrelating, setIsCorrelating] = useState(false)
  const [activeTab, setActiveTab] = useState('identifiers')

  // Add-identifier form
  const [showAddForm, setShowAddForm] = useState(false)
  const [addRows, setAddRows] = useState<IdRow[]>([{ ...EMPTY_ROW }])
  const [addingIds, setAddingIds] = useState(false)

  // Profiles tab state
  const [postView, setPostView] = useState<
    Record<number, { filter: string; expanded: boolean }>
  >({})
  const [expandedPosts, setExpandedPosts] = useState<Set<number>>(new Set())
  const [networkSearch, setNetworkSearch] = useState('')
  const [networkTab, setNetworkTab] = useState<Record<number, string>>({})

  // ── Fetch functions ──

  const fetchCase = useCallback(() => {
    fetch(`${API}/api/cases/${id}`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok)
          throw new Error(
            r.status === 404 ? 'Case not found' : `HTTP ${r.status}`
          )
        return r.json()
      })
      .then((data) => {
        setCaseData(data.case)
        setIdentifiers(data.identifiers || [])
        setAccounts(data.accounts || [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false))
  }, [id])

  const fetchResults = useCallback(() => {
    fetch(`${API}/api/cases/${id}/results`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : Promise.resolve({ results: [] })))
      .then((data) => setCorrelationResults(data.results || []))
      .catch(() => {})
  }, [id])

  useEffect(() => {
    fetchCase()
    fetchResults()
  }, [fetchCase, fetchResults])

  // ── Action handlers ──

  const handleCollect = async (identifier: {
    id: number
    platform_hint?: string | null
    value: string
    identifier_type?: string
  }) => {
    if (identifier.identifier_type && identifier.identifier_type !== 'username')
      return
    const platform = identifier.platform_hint || 'reddit'
    const key = identifier.id
    setCollecting((prev) => ({ ...prev, [key]: true }))
    setError(null)

    try {
      const res = await fetch(`${API}/api/cases/${id}/collect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ platform, username: identifier.value }),
      })
      if (!res.ok) {
        const err = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(err)
      }
      fetchCase()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Collection failed')
    } finally {
      setCollecting((prev) => ({ ...prev, [key]: false }))
    }
  }

  const handleAddIdentifiers = async () => {
    const cleaned = addRows
      .filter((r) => r.value.trim())
      .map((r) => ({
        identifier_type: r.identifier_type,
        value: r.value.trim(),
        platform_hint:
          r.identifier_type === 'username' &&
          r.platform_hint &&
          r.platform_hint !== 'none'
            ? r.platform_hint
            : null,
      }))
    if (cleaned.length === 0) return

    setAddingIds(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/cases/${id}/identifiers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(cleaned),
      })
      if (!res.ok) {
        const err = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(err)
      }
      setAddRows([{ ...EMPTY_ROW }])
      setShowAddForm(false)
      fetchCase()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add identifiers')
    } finally {
      setAddingIds(false)
    }
  }

  const handleCorrelate = async () => {
    setIsCorrelating(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/cases/${id}/correlate`, {
        method: 'POST',
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        setCorrelationResults(data.results || [])
      } else {
        const err = await res.json().catch(() => ({}))
        setError(
          (err as Record<string, string>).detail || 'Correlation failed'
        )
      }
    } catch (e) {
      setError(
        'Correlation failed: ' +
          (e instanceof Error ? e.message : 'Unknown error')
      )
    } finally {
      setIsCorrelating(false)
    }
  }

  const handleDeleteCase = async () => {
    try {
      const res = await fetch(`${API}/api/cases/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`)
      navigate({ to: '/cases' })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete case')
    }
  }

  // ── Add-identifier row helpers ──

  const updateRow = (i: number, field: keyof IdRow, val: string) => {
    setAddRows((prev) =>
      prev.map((row, j) => (j === i ? { ...row, [field]: val } : row))
    )
  }

  // ── Post view helpers ──

  const getPostView = (accId: number) =>
    postView[accId] || { filter: 'all', expanded: false }

  const setFilter = (accId: number, filter: string) => {
    setPostView((prev) => ({
      ...prev,
      [accId]: { ...getPostView(accId), filter },
    }))
  }

  const toggleFeedExpanded = (accId: number) => {
    setPostView((prev) => ({
      ...prev,
      [accId]: {
        ...getPostView(accId),
        expanded: !getPostView(accId).expanded,
      },
    }))
  }

  const togglePostExpand = (postId: number) => {
    setExpandedPosts((prev) => {
      const next = new Set(prev)
      if (next.has(postId)) next.delete(postId)
      else next.add(postId)
      return next
    })
  }

  // ── Loading state ──

  if (isLoading) {
    return (
      <>
        <Header>
          <SearchBar className='me-auto' />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </Header>
        <Main>
          <Skeleton className='mb-2 h-5 w-24' />
          <Skeleton className='mb-1 h-8 w-64' />
          <Skeleton className='mb-4 h-4 w-48' />
          <Skeleton className='mb-4 h-10 w-full max-w-md' />
          <div className='grid gap-4 lg:grid-cols-2'>
            <Skeleton className='h-64' />
            <Skeleton className='h-64' />
          </div>
        </Main>
      </>
    )
  }

  // ── Not found state ──

  if (!caseData) {
    return (
      <>
        <Header>
          <SearchBar className='me-auto' />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </Header>
        <Main>
          <Card className='mx-auto mt-12 max-w-md'>
            <CardHeader className='text-center'>
              <CardTitle>Case not found</CardTitle>
              <CardDescription>
                {error || 'This case does not exist or was deleted.'}
              </CardDescription>
            </CardHeader>
            <CardContent className='flex justify-center'>
              <Button
                variant='outline'
                onClick={() => navigate({ to: '/cases' })}
              >
                <ArrowLeft className='h-4 w-4' />
                Back to Cases
              </Button>
            </CardContent>
          </Card>
        </Main>
      </>
    )
  }

  return (
    <>
      <Header>
        <SearchBar className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main>
        {/* ── Case Header ── */}
        <div className='mb-4'>
          <Button
            variant='link'
            className='mb-1 h-auto p-0 text-muted-foreground'
            onClick={() => navigate({ to: '/cases' })}
          >
            <ArrowLeft className='h-3 w-3' />
            Cases
          </Button>

          <div className='flex items-start justify-between'>
            <div className='min-w-0 flex-1'>
              <h1 className='truncate text-2xl font-bold tracking-tight'>
                {caseData.title}
              </h1>
              <div className='mt-1 flex items-center gap-2 text-sm text-muted-foreground'>
                <code className='text-xs'>{padId(caseData.id)}</code>
                <Separator orientation='vertical' className='h-4' />
                <Badge
                  variant={
                    caseData.status === 'open' ? 'default' : 'secondary'
                  }
                >
                  {caseData.status}
                </Badge>
                <Separator orientation='vertical' className='h-4' />
                <span className='flex items-center gap-1'>
                  <Calendar className='h-3 w-3' />
                  {formatDate(caseData.created_at)}
                </span>
              </div>
            </div>

            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant='destructive' size='sm'>
                  <Trash2 className='h-4 w-4' />
                  Delete Case
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete this case?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete &quot;{caseData.title}&quot; and
                    all associated data including identifiers, collected
                    accounts, posts, and correlation results. This action cannot
                    be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleDeleteCase}
                    className='bg-destructive text-white hover:bg-destructive/90'
                  >
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>

        {/* ── Error banner ── */}
        {error && (
          <div className='mb-4 flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'>
            <span>{error}</span>
            <Button
              variant='ghost'
              size='icon'
              className='h-6 w-6 shrink-0'
              onClick={() => setError(null)}
            >
              <X className='h-3 w-3' />
            </Button>
          </div>
        )}

        {/* ── Tabs ── */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className='w-full overflow-x-auto pb-2'>
            <TabsList>
              <TabsTrigger value='identifiers'>
                <Users className='h-4 w-4' />
                Identifiers ({identifiers.length})
              </TabsTrigger>
              <TabsTrigger value='osint'>
                <Search className='h-4 w-4' />
                OSINT Discovery
              </TabsTrigger>
              <TabsTrigger value='profiles'>
                <Activity className='h-4 w-4' />
                Profiles & Activity
                {accounts.length > 0 && ` (${accounts.length})`}
              </TabsTrigger>
              <TabsTrigger value='correlation'>
                <GitMerge className='h-4 w-4' />
                Correlation
                {correlationResults.length > 0 &&
                  ` (${correlationResults.length})`}
              </TabsTrigger>
            </TabsList>
          </div>

          {/* ── Identifiers Tab ── */}
          <TabsContent value='identifiers'>
            <div className='grid gap-4 lg:grid-cols-2'>
              {/* Left — Seed Identifiers */}
              <Card>
                <CardHeader className='flex flex-row items-center justify-between'>
                  <div>
                    <CardTitle>Seed Identifiers</CardTitle>
                    <CardDescription>
                      Input data driving this investigation
                    </CardDescription>
                  </div>
                  {!showAddForm && (
                    <Button
                      variant='outline'
                      size='sm'
                      onClick={() => setShowAddForm(true)}
                    >
                      <Plus className='h-4 w-4' />
                      Add Identifier
                    </Button>
                  )}
                </CardHeader>
                <CardContent>
                  {identifiers.length === 0 && !showAddForm ? (
                    <p className='py-6 text-center text-sm text-muted-foreground'>
                      No identifiers yet.
                    </p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Type</TableHead>
                          <TableHead>Value</TableHead>
                          <TableHead>Platform</TableHead>
                          <TableHead className='text-right'>Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {identifiers.map((ident) => (
                          <TableRow key={ident.id}>
                            <TableCell>
                              <Badge
                                variant={
                                  ident.identifier_type === 'username'
                                    ? 'default'
                                    : 'secondary'
                                }
                              >
                                {ident.identifier_type === 'profile_url'
                                  ? 'URL'
                                  : capitalize(ident.identifier_type)}
                              </Badge>
                            </TableCell>
                            <TableCell className='font-mono text-sm'>
                              {ident.value}
                            </TableCell>
                            <TableCell>
                              {ident.platform_hint ? (
                                <Badge variant='secondary'>
                                  {capitalize(ident.platform_hint)}
                                </Badge>
                              ) : (
                                <span className='text-muted-foreground'>
                                  —
                                </span>
                              )}
                            </TableCell>
                            <TableCell className='text-right'>
                              {ident.identifier_type === 'username' && (
                                <Button
                                  variant='outline'
                                  size='sm'
                                  disabled={!!collecting[ident.id]}
                                  onClick={() => handleCollect(ident)}
                                >
                                  {collecting[ident.id] ? (
                                    <>
                                      <Loader2 className='h-3 w-3 animate-spin' />
                                      Collecting...
                                    </>
                                  ) : (
                                    <>
                                      <Download className='h-3 w-3' />
                                      Collect
                                    </>
                                  )}
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}

                  {/* ── Add Identifier Form ── */}
                  {showAddForm && (
                    <div className='mt-4 space-y-3 rounded-lg border p-4'>
                      {addRows.map((row, i) => (
                        <div key={i} className='flex items-center gap-2'>
                          <Select
                            value={row.identifier_type}
                            onValueChange={(v) =>
                              updateRow(i, 'identifier_type', v)
                            }
                            disabled={addingIds}
                          >
                            <SelectTrigger className='w-[130px] shrink-0'>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {IDENTIFIER_TYPES.map((t) => (
                                <SelectItem key={t.value} value={t.value}>
                                  {t.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>

                          <Input
                            className='min-w-0 flex-1'
                            placeholder={
                              PLACEHOLDERS[row.identifier_type] || 'Value'
                            }
                            value={row.value}
                            onChange={(e) =>
                              updateRow(i, 'value', e.target.value)
                            }
                            disabled={addingIds}
                          />

                          {row.identifier_type === 'username' && (
                            <Select
                              value={row.platform_hint || 'none'}
                              onValueChange={(v) =>
                                updateRow(i, 'platform_hint', v)
                              }
                              disabled={addingIds}
                            >
                              <SelectTrigger className='w-[130px] shrink-0'>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value='none'>
                                  No Platform
                                </SelectItem>
                                {PLATFORMS.map((p) => (
                                  <SelectItem key={p.value} value={p.value}>
                                    {p.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          )}

                          {addRows.length > 1 && (
                            <Button
                              type='button'
                              variant='outline'
                              size='icon'
                              className='shrink-0'
                              disabled={addingIds}
                              onClick={() =>
                                setAddRows((prev) =>
                                  prev.filter((_, j) => j !== i)
                                )
                              }
                            >
                              <X className='h-4 w-4' />
                            </Button>
                          )}
                        </div>
                      ))}

                      <div className='flex items-center justify-between'>
                        <Button
                          type='button'
                          variant='link'
                          size='sm'
                          className='h-auto p-0'
                          disabled={addingIds}
                          onClick={() =>
                            setAddRows((prev) => [...prev, { ...EMPTY_ROW }])
                          }
                        >
                          <Plus className='h-3 w-3' />
                          More
                        </Button>
                        <div className='flex gap-2'>
                          <Button
                            variant='outline'
                            size='sm'
                            disabled={addingIds}
                            onClick={() => {
                              setShowAddForm(false)
                              setAddRows([{ ...EMPTY_ROW }])
                            }}
                          >
                            Cancel
                          </Button>
                          <Button
                            size='sm'
                            disabled={
                              addingIds ||
                              addRows.every((r) => !r.value.trim())
                            }
                            onClick={handleAddIdentifiers}
                          >
                            {addingIds ? (
                              <>
                                <Loader2 className='h-3 w-3 animate-spin' />
                                Saving...
                              </>
                            ) : (
                              'Save'
                            )}
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Right — Collection Status */}
              <Card>
                <CardHeader>
                  <CardTitle>Collected Accounts</CardTitle>
                  <CardDescription>
                    Platform data gathered for this case
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {accounts.length === 0 ? (
                    <p className='py-6 text-center text-sm text-muted-foreground'>
                      No data collected yet. Use the Collect buttons to gather
                      platform data.
                    </p>
                  ) : (
                    <div className='space-y-3'>
                      {accounts.map((acc) => (
                        <div
                          key={acc.id}
                          className='flex items-center justify-between rounded-lg border p-3'
                        >
                          <div className='flex items-center gap-3'>
                            <Badge variant='secondary'>
                              {capitalize(acc.platform)}
                            </Badge>
                            <span className='font-mono text-sm'>
                              {acc.username}
                            </span>
                            <span className='text-xs text-muted-foreground'>
                              {acc.posts.length} posts
                            </span>
                          </div>
                          <Button
                            variant='ghost'
                            size='icon'
                            className='h-8 w-8'
                            disabled={!!collecting[acc.id]}
                            onClick={() =>
                              handleCollect({
                                id: acc.id,
                                platform_hint: acc.platform,
                                value: acc.username,
                              })
                            }
                          >
                            {collecting[acc.id] ? (
                              <Loader2 className='h-3 w-3 animate-spin' />
                            ) : (
                              <RefreshCw className='h-3 w-3' />
                            )}
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* ── OSINT Tab ── */}
          <TabsContent value='osint'>
            <OsintPanel
              caseId={id}
              identifiers={identifiers}
              onAccountImported={fetchCase}
            />
          </TabsContent>

          {/* ── Profiles & Activity Tab ── */}
          <TabsContent value='profiles'>
            <ProfilesTab
              accounts={accounts}
              postView={postView}
              expandedPosts={expandedPosts}
              networkSearch={networkSearch}
              networkTab={networkTab}
              setFilter={setFilter}
              toggleFeedExpanded={toggleFeedExpanded}
              togglePostExpand={togglePostExpand}
              setNetworkSearch={setNetworkSearch}
              setNetworkTab={(accId, tab) =>
                setNetworkTab((prev) => ({ ...prev, [accId]: tab }))
              }
            />
          </TabsContent>

          {/* ── Correlation Tab ── */}
          <TabsContent value='correlation'>
            <CorrelationResults
              results={correlationResults as any}
              accounts={accounts}
              isCorrelating={isCorrelating}
              onCorrelate={handleCorrelate}
            />
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}

// ── Profiles & Activity Tab ──

function ProfilesTab({
  accounts,
  postView,
  expandedPosts,
  networkSearch,
  networkTab,
  setFilter,
  toggleFeedExpanded,
  togglePostExpand,
  setNetworkSearch,
  setNetworkTab,
}: {
  accounts: Account[]
  postView: Record<number, { filter: string; expanded: boolean }>
  expandedPosts: Set<number>
  networkSearch: string
  networkTab: Record<number, string>
  setFilter: (accId: number, filter: string) => void
  toggleFeedExpanded: (accId: number) => void
  togglePostExpand: (postId: number) => void
  setNetworkSearch: (q: string) => void
  setNetworkTab: (accId: number, tab: string) => void
}) {
  if (accounts.length === 0) {
    return (
      <Card>
        <CardContent className='py-12 text-center'>
          <p className='text-sm text-muted-foreground'>
            No accounts collected yet. Go to the Identifiers tab and use the
            Collect buttons to gather platform data.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className='space-y-6'>
      {accounts.map((acc, accIdx) => {
        const posts = acc.posts || []
        const contentPosts = posts.filter(
          (p) => (p.metadata?.type as string) !== 'network'
        )
        const pv = postView[acc.id] || { filter: 'all', expanded: false }
        const postTypes = [
          ...new Set(
            contentPosts
              .map((p) => p.metadata?.type as string)
              .filter(Boolean)
          ),
        ]
        const filtered = contentPosts.filter(
          (p) => pv.filter === 'all' || p.metadata?.type === pv.filter
        )
        const visiblePosts = pv.expanded ? filtered : filtered.slice(0, 5)

        const subreddits =
          acc.platform === 'reddit'
            ? [
                ...new Set(
                  posts
                    .map((p) => p.metadata?.subreddit as string)
                    .filter(Boolean)
                ),
              ]
            : []

        const topLanguages =
          acc.platform === 'github'
            ? [
                ...new Set(
                  posts
                    .filter(
                      (p) =>
                        p.metadata?.type === 'repo' && p.metadata?.language
                    )
                    .map((p) => p.metadata.language as string)
                ),
              ].slice(0, 5)
            : []

        const repoCount =
          acc.platform === 'github'
            ? posts.filter((p) => p.metadata?.type === 'repo').length
            : 0

        const joinedDate = acc.created_at
          ? new Date(acc.created_at).toISOString().slice(0, 10)
          : null

        const networkFollowers = posts.find(
          (p) =>
            p.metadata?.type === 'network' &&
            p.metadata?.direction === 'followers'
        )
        const networkFollowing = posts.find(
          (p) =>
            p.metadata?.type === 'network' &&
            p.metadata?.direction === 'following'
        )
        const hasNetwork = !!(networkFollowers || networkFollowing)

        return (
          <div key={acc.id}>
            {accIdx > 0 && <Separator className='mb-6' />}

            {/* Profile Card */}
            <Card>
              <CardContent className='pt-6'>
                <div className='flex items-start gap-4'>
                  <Avatar className='h-12 w-12'>
                    {acc.profile_image_url && (
                      <AvatarImage src={acc.profile_image_url} />
                    )}
                    <AvatarFallback>
                      {(acc.display_name || acc.username || '?')[0].toUpperCase()}
                    </AvatarFallback>
                  </Avatar>

                  <div className='min-w-0 flex-1'>
                    <div className='flex items-center gap-2'>
                      <span className='text-lg font-medium'>
                        {acc.display_name || acc.username}
                      </span>
                      <Badge variant='secondary'>
                        {capitalize(acc.platform)}
                      </Badge>
                    </div>
                    <p className='font-mono text-sm text-muted-foreground'>
                      {platformHandle(acc.platform, acc.username)}
                    </p>
                  </div>
                </div>

                {acc.bio && (
                  <p className='mt-3 line-clamp-2 text-sm text-muted-foreground'>
                    {acc.bio}
                  </p>
                )}

                {acc.location && (
                  <p className='mt-1 flex items-center gap-1 text-xs text-muted-foreground'>
                    <MapPin className='h-3 w-3' />
                    {acc.location}
                  </p>
                )}

                {/* Stats */}
                <div className='mt-4 flex flex-wrap gap-6'>
                  {acc.karma != null && (
                    <StatItem label='Karma' value={acc.karma.toLocaleString()} />
                  )}
                  {acc.follower_count != null && (
                    <StatItem
                      label='Followers'
                      value={acc.follower_count.toLocaleString()}
                    />
                  )}
                  {acc.following_count != null && (
                    <StatItem
                      label='Following'
                      value={acc.following_count.toLocaleString()}
                    />
                  )}
                  {acc.platform === 'github' ? (
                    <StatItem label='Repos' value={String(repoCount)} />
                  ) : (
                    <StatItem
                      label={acc.platform === 'twitter' ? 'Tweets' : 'Posts'}
                      value={String(contentPosts.length)}
                    />
                  )}
                  {subreddits.length > 0 && (
                    <StatItem
                      label='Subreddits'
                      value={String(subreddits.length)}
                    />
                  )}
                  {joinedDate && <StatItem label='Joined' value={joinedDate} />}
                </div>

                {topLanguages.length > 0 && (
                  <div className='mt-3 flex items-center gap-1 text-xs text-muted-foreground'>
                    <span>Languages:</span>
                    {topLanguages.map((l) => (
                      <Badge key={l} variant='outline' className='text-xs'>
                        {l}
                      </Badge>
                    ))}
                  </div>
                )}

                {subreddits.length > 0 && (
                  <div className='mt-3'>
                    <p className='mb-1 text-xs font-medium text-muted-foreground'>
                      ACTIVE SUBREDDITS
                    </p>
                    <div className='flex flex-wrap gap-1'>
                      {subreddits.slice(0, 8).map((s) => (
                        <Badge key={s} variant='outline' className='text-xs'>
                          r/{s}
                        </Badge>
                      ))}
                      {subreddits.length > 8 && (
                        <span className='text-xs text-muted-foreground'>
                          +{subreddits.length - 8} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* GitHub Network Panel */}
            {acc.platform === 'github' && hasNetwork && (
              <NetworkPanel
                followers={networkFollowers}
                following={networkFollowing}
                search={networkSearch}
                activeTab={networkTab[acc.id] || 'followers'}
                onSearchChange={setNetworkSearch}
                onTabChange={(tab) => setNetworkTab(acc.id, tab)}
              />
            )}

            {/* Post Feed */}
            {contentPosts.length > 0 && (
              <Card className='mt-3'>
                <CardHeader className='pb-3'>
                  <div className='flex items-center justify-between'>
                    <span className='font-mono text-xs uppercase text-muted-foreground'>
                      {acc.platform} Activity
                    </span>
                    <Badge variant='secondary'>
                      {filtered.length} records
                    </Badge>
                  </div>
                  <div className='flex flex-wrap gap-1 pt-2'>
                    <Button
                      variant={pv.filter === 'all' ? 'default' : 'ghost'}
                      size='sm'
                      className='h-7 text-xs'
                      onClick={() => setFilter(acc.id, 'all')}
                    >
                      All
                    </Button>
                    {postTypes.map((t) => (
                      <Button
                        key={t}
                        variant={pv.filter === t ? 'default' : 'ghost'}
                        size='sm'
                        className='h-7 text-xs'
                        onClick={() => setFilter(acc.id, t)}
                      >
                        {t}
                      </Button>
                    ))}
                  </div>
                </CardHeader>
                <CardContent className='pt-0'>
                  {filtered.length === 0 ? (
                    <p className='py-6 text-center text-sm text-muted-foreground'>
                      No records match filter.
                    </p>
                  ) : (
                    <div className='divide-y'>
                      {visiblePosts.map((post, i) => (
                        <PostRow
                          key={post.id}
                          post={post}
                          index={i}
                          platform={acc.platform}
                          isExpanded={expandedPosts.has(post.id)}
                          onToggleExpand={() => togglePostExpand(post.id)}
                        />
                      ))}
                    </div>
                  )}

                  {filtered.length > 5 && (
                    <Button
                      variant='ghost'
                      className='mt-2 w-full'
                      onClick={() => toggleFeedExpanded(acc.id)}
                    >
                      {pv.expanded
                        ? 'Show less'
                        : `Show all ${filtered.length} records`}
                    </Button>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )
      })}
    </div>
  )
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className='text-xs text-muted-foreground'>{label}</p>
      <p className='text-sm font-medium'>{value}</p>
    </div>
  )
}

function PostRow({
  post,
  index,
  platform,
  isExpanded,
  onToggleExpand,
}: {
  post: Post
  index: number
  platform: string
  isExpanded: boolean
  onToggleExpand: () => void
}) {
  const meta = post.metadata || {}
  const text = post.text || ''
  const isLong = text.length > 120
  const displayText = isExpanded || !isLong ? text : text.slice(0, 120) + '...'
  const ts = post.timestamp || (meta.timestamp as string)
  const images = (meta.images as string[]) || []
  const showImages = platform !== 'github' && images.length > 0

  return (
    <div className='py-2'>
      <div className='flex items-start gap-2'>
        <span className='mt-0.5 shrink-0 font-mono text-xs text-muted-foreground'>
          {String(index + 1).padStart(3, '0')}
        </span>

        {!!meta.type && (
          <Badge variant='outline' className='shrink-0 text-xs'>
            {(meta.type as string).toUpperCase()}
          </Badge>
        )}

        {!!meta.subreddit && (
          <span className='shrink-0 text-xs text-muted-foreground'>
            r/{String(meta.subreddit)}
          </span>
        )}

        <div className='min-w-0 flex-1'>
          <p className='text-sm'>
            {displayText}
            {isLong && (
              <button
                onClick={onToggleExpand}
                className='ml-1 text-xs text-primary hover:underline'
              >
                {isExpanded ? '▲ collapse' : '▼ expand'}
              </button>
            )}
          </p>

          {/* Stats line */}
          <div className='mt-0.5 flex items-center gap-3 text-xs text-muted-foreground'>
            {ts && <span>{formatTimestamp(ts)}</span>}
            {platform === 'reddit' && meta.score != null && (
              <span>▲ {Number(meta.score)}</span>
            )}
            {platform === 'twitter' && meta.retweet_count != null && (
              <span>⟳ {Number(meta.retweet_count)}</span>
            )}
            {platform === 'twitter' && meta.favorite_count != null && (
              <span>♥ {Number(meta.favorite_count)}</span>
            )}
            {platform === 'github' &&
              meta.type === 'repo' &&
              meta.stars != null && (
                <span>★ {Number(meta.stars)}</span>
              )}
            {platform === 'github' && !!meta.language && (
              <span>{String(meta.language)}</span>
            )}
            {platform === 'instagram' && meta.like_count != null && (
              <span>♥ {Number(meta.like_count)}</span>
            )}
            {platform === 'instagram' && meta.comment_count != null && (
              <span>💬 {Number(meta.comment_count)}</span>
            )}
            {!!meta.url && (
              <a
                href={meta.url as string}
                target='_blank'
                rel='noopener noreferrer'
                className='hover:text-primary'
              >
                <ExternalLink className='h-3 w-3' />
              </a>
            )}
          </div>
        </div>
      </div>

      {showImages && (
        <div className='mt-1 flex gap-1 pl-10'>
          {images.slice(0, 3).map((img, i) => (
            <a
              key={i}
              href={img}
              target='_blank'
              rel='noopener noreferrer'
            >
              <img
                src={img}
                alt=''
                className='max-h-16 rounded object-cover'
              />
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function NetworkPanel({
  followers,
  following,
  search,
  activeTab,
  onSearchChange,
  onTabChange,
}: {
  followers: Post | undefined
  following: Post | undefined
  search: string
  activeTab: string
  onSearchChange: (q: string) => void
  onTabChange: (tab: string) => void
}) {
  const activePost = activeTab === 'followers' ? followers : following
  const logins = ((activePost?.metadata?.logins as string[]) || [])
  const totalCount = (activePost?.metadata?.total_count as number) || 0
  const fetchedCount = (activePost?.metadata?.fetched_count as number) || 0

  const filtered = search.trim()
    ? logins.filter((l) => l.toLowerCase().includes(search.toLowerCase()))
    : logins

  return (
    <Collapsible className='mt-3'>
      <Card>
        <CollapsibleTrigger asChild>
          <CardHeader className='cursor-pointer pb-3'>
            <div className='flex items-center justify-between'>
              <CardTitle className='text-sm'>GitHub Network</CardTitle>
              <ChevronDown className='h-4 w-4 text-muted-foreground' />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className='pt-0'>
            <div className='mb-3 flex items-center gap-2'>
              {followers && (
                <Button
                  variant={activeTab === 'followers' ? 'default' : 'ghost'}
                  size='sm'
                  className='h-7 text-xs'
                  onClick={() => {
                    onTabChange('followers')
                    onSearchChange('')
                  }}
                >
                  Followers{' '}
                  <Badge variant='secondary' className='ml-1'>
                    {(followers.metadata?.total_count as number) || 0}
                  </Badge>
                </Button>
              )}
              {following && (
                <Button
                  variant={activeTab === 'following' ? 'default' : 'ghost'}
                  size='sm'
                  className='h-7 text-xs'
                  onClick={() => {
                    onTabChange('following')
                    onSearchChange('')
                  }}
                >
                  Following{' '}
                  <Badge variant='secondary' className='ml-1'>
                    {(following.metadata?.total_count as number) || 0}
                  </Badge>
                </Button>
              )}
              {logins.length > 0 && (
                <Input
                  placeholder='Filter...'
                  value={search}
                  onChange={(e) => onSearchChange(e.target.value)}
                  className='ml-auto h-7 w-40 text-xs'
                />
              )}
            </div>

            {logins.length === 0 ? (
              <p className='text-sm text-muted-foreground'>
                No {activeTab} collected
              </p>
            ) : (
              <>
                <div className='grid grid-cols-2 gap-1 sm:grid-cols-3 md:grid-cols-4'>
                  {filtered.map((login) => (
                    <a
                      key={login}
                      href={`https://github.com/${login}`}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='truncate rounded px-1.5 py-0.5 font-mono text-xs text-primary hover:bg-muted hover:underline'
                    >
                      {login}
                    </a>
                  ))}
                </div>
                {filtered.length === 0 && (
                  <p className='text-sm text-muted-foreground'>
                    No matches for &quot;{search}&quot;
                  </p>
                )}
                {fetchedCount < totalCount && (
                  <p className='mt-2 text-xs text-muted-foreground'>
                    Showing {fetchedCount} of {totalCount}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
