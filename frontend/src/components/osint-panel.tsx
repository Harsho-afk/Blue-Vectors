import { useState, useEffect, useCallback } from 'react'
import { ChevronDown, Globe, Loader2, Mail, Phone, Search, Shield } from 'lucide-react'
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
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { MaigretResults } from './maigret-results'
import { BreachResults } from './breach-results'
import { PhoneResults } from './phone-results'
import { DorkingResults } from './dorking-results'
import { HoleheResults } from './holehe-results'

interface Identifier {
  id: number
  identifier_type: string
  value: string
  platform_hint: string | null
}

interface Lookup {
  id: number
  lookup_type: string
  input_value?: string
  result?: Record<string, unknown>
}

interface Props {
  caseId: string
  identifiers: Identifier[]
  onAccountImported?: () => void
}

export function OsintPanel({ caseId, identifiers, onAccountImported }: Props) {
  const [lookups, setLookups] = useState<Lookup[]>([])
  const [searchingUsername, setSearchingUsername] = useState<string | null>(null)
  const [searchingEmail, setSearchingEmail] = useState<string | null>(null)
  const [searchingPhone, setSearchingPhone] = useState<string | null>(null)
  const [searchingHolehe, setSearchingHolehe] = useState<string | null>(null)
  const [dorkingIdent, setDorkingIdent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchLookups = useCallback(() => {
    fetch(`${API}/api/cases/${caseId}/osint`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data) => setLookups(data.lookups || []))
      .catch((e) => setError(e.message))
  }, [caseId])

  useEffect(() => {
    fetchLookups()
  }, [fetchLookups])

  const handleUsernameSearch = async (value: string) => {
    setSearchingUsername(value)
    setError(null)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/osint/username-search`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ username: value }),
        }
      )
      if (!res.ok) {
        const detail = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(detail)
      }
      fetchLookups()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setSearchingUsername(null)
    }
  }

  const handleBreachLookup = async (value: string) => {
    setSearchingEmail(value)
    setError(null)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/osint/breach-lookup`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ email: value }),
        }
      )
      if (!res.ok) {
        const detail = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(detail)
      }
      fetchLookups()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lookup failed')
    } finally {
      setSearchingEmail(null)
    }
  }

  const handlePhoneLookup = async (value: string) => {
    setSearchingPhone(value)
    setError(null)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/osint/phone-lookup`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ phone: value }),
        }
      )
      if (!res.ok) {
        const detail = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(detail)
      }
      fetchLookups()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lookup failed')
    } finally {
      setSearchingPhone(null)
    }
  }

  const handleHoleheLookup = async (value: string) => {
    setSearchingHolehe(value)
    setError(null)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/osint/holehe-lookup`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ email: value }),
        }
      )
      if (!res.ok) {
        const detail = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(detail)
      }
      fetchLookups()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Holehe lookup failed')
    } finally {
      setSearchingHolehe(null)
    }
  }

  const handleDorking = async (ident: Identifier) => {
    setDorkingIdent(ident.value)
    setError(null)
    try {
      const res = await fetch(
        `${API}/api/cases/${caseId}/osint/dorking`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            identifier_type: ident.identifier_type,
            value: ident.value,
            platform_hint: ident.platform_hint,
            use_llm: true,
          }),
        }
      )
      if (!res.ok) {
        const detail = await res
          .json()
          .then((d) => d.detail)
          .catch(() => res.statusText)
        throw new Error(detail)
      }
      fetchLookups()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Dorking survey failed')
    } finally {
      setDorkingIdent(null)
    }
  }

  const usernameIdents = identifiers.filter(
    (i) => i.identifier_type === 'username'
  )
  const emailIdents = identifiers.filter((i) => i.identifier_type === 'email')
  const phoneIdents = identifiers.filter((i) => i.identifier_type === 'phone')

  const hasIdents =
    usernameIdents.length > 0 ||
    emailIdents.length > 0 ||
    phoneIdents.length > 0

  const maigretLookups = lookups.filter((l) => l.lookup_type === 'maigret')
  const breachLookups = lookups.filter(
    (l) => l.lookup_type === 'xposedornot' || l.lookup_type === 'hibp'
  )
  const phoneLookups = lookups.filter((l) => l.lookup_type === 'phone')
  const holeheLookups = lookups.filter((l) => l.lookup_type === 'holehe')
  const dorkingLookups = lookups.filter((l) => l.lookup_type === 'dorking')
  const hasResults = lookups.length > 0

  return (
    <div className='space-y-4'>
      {/* ── Actions Card ── */}
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>Run Lookups</CardTitle>
          <CardDescription>
            Select an identifier to run an OSINT lookup
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <div className='mb-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive'>
              {error}
            </div>
          )}

          {!hasIdents && (
            <p className='py-4 text-center text-sm text-muted-foreground'>
              No identifiers to look up. Add identifiers in the Identifiers tab
              first.
            </p>
          )}

          {hasIdents && (
            <div className='space-y-2'>
              {usernameIdents.map((ident) => (
                <div
                  key={ident.id}
                  className='flex items-center justify-between rounded-lg border p-3'
                >
                  <div className='flex items-center gap-2'>
                    <Badge variant='default'>Username</Badge>
                    <span className='font-mono text-sm'>{ident.value}</span>
                  </div>
                  <div className='flex gap-1.5'>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={searchingUsername === ident.value}
                      onClick={() => handleUsernameSearch(ident.value)}
                    >
                      {searchingUsername === ident.value ? (
                        <>
                          <Loader2 className='h-3 w-3 animate-spin' />
                          Searching...
                        </>
                      ) : (
                        <>
                          <Search className='h-3 w-3' />
                          Platforms
                        </>
                      )}
                    </Button>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={dorkingIdent === ident.value}
                      onClick={() => handleDorking(ident)}
                    >
                      {dorkingIdent === ident.value ? (
                        <>
                          <Loader2 className='h-3 w-3 animate-spin' />
                          Surveying...
                        </>
                      ) : (
                        <>
                          <Globe className='h-3 w-3' />
                          Web Survey
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ))}
              {emailIdents.map((ident) => (
                <div
                  key={ident.id}
                  className='flex items-center justify-between rounded-lg border p-3'
                >
                  <div className='flex items-center gap-2'>
                    <Badge variant='secondary'>Email</Badge>
                    <span className='font-mono text-sm'>{ident.value}</span>
                  </div>
                  <div className='flex gap-1.5'>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={searchingHolehe === ident.value}
                      onClick={() => handleHoleheLookup(ident.value)}
                    >
                      {searchingHolehe === ident.value ? (
                        <>
                          <Loader2 className='h-3 w-3 animate-spin' />
                          Checking...
                        </>
                      ) : (
                        <>
                          <Mail className='h-3 w-3' />
                          Accounts
                        </>
                      )}
                    </Button>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={searchingEmail === ident.value}
                      onClick={() => handleBreachLookup(ident.value)}
                    >
                      {searchingEmail === ident.value ? (
                        <>
                          <Loader2 className='h-3 w-3 animate-spin' />
                          Checking...
                        </>
                      ) : (
                        <>
                          <Shield className='h-3 w-3' />
                          Breaches
                        </>
                      )}
                    </Button>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={dorkingIdent === ident.value}
                      onClick={() => handleDorking(ident)}
                    >
                      {dorkingIdent === ident.value ? (
                        <>
                          <Loader2 className='h-3 w-3 animate-spin' />
                          Surveying...
                        </>
                      ) : (
                        <>
                          <Globe className='h-3 w-3' />
                          Web Survey
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ))}
              {phoneIdents.map((ident) => (
                <div
                  key={ident.id}
                  className='flex items-center justify-between rounded-lg border p-3'
                >
                  <div className='flex items-center gap-2'>
                    <Badge variant='secondary'>Phone</Badge>
                    <span className='font-mono text-sm'>{ident.value}</span>
                  </div>
                  <div className='flex gap-1.5'>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={searchingPhone === ident.value}
                      onClick={() => handlePhoneLookup(ident.value)}
                    >
                      {searchingPhone === ident.value ? (
                        <>
                          <Loader2 className='h-3 w-3 animate-spin' />
                          Looking up...
                        </>
                      ) : (
                        <>
                          <Phone className='h-3 w-3' />
                          Phone
                        </>
                      )}
                    </Button>
                    <Button
                      variant='outline'
                      size='sm'
                      disabled={dorkingIdent === ident.value}
                      onClick={() => handleDorking(ident)}
                    >
                      {dorkingIdent === ident.value ? (
                        <>
                          <Loader2 className='h-3 w-3 animate-spin' />
                          Surveying...
                        </>
                      ) : (
                        <>
                          <Globe className='h-3 w-3' />
                          Web Survey
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Results ── */}
      {!hasResults && (
        <Card>
          <CardContent className='py-10 text-center'>
            <Search className='mx-auto mb-2 h-8 w-8 text-muted-foreground/40' />
            <p className='text-sm text-muted-foreground'>
              No results yet. Run a lookup above to discover OSINT data.
            </p>
          </CardContent>
        </Card>
      )}

      {maigretLookups.length > 0 && (
        <ResultSection
          title='Platform Searches'
          icon={<Search className='h-4 w-4' />}
          count={maigretLookups.length}
        >
          {maigretLookups.map((lookup) => (
            <MaigretResults
              key={lookup.id}
              lookup={lookup as any}
              caseId={caseId}
              onAccountImported={() => {
                fetchLookups()
                onAccountImported?.()
              }}
            />
          ))}
        </ResultSection>
      )}

      {breachLookups.length > 0 && (
        <ResultSection
          title='Breach Lookups'
          icon={<Shield className='h-4 w-4' />}
          count={breachLookups.length}
        >
          {breachLookups.map((lookup) => (
            <BreachResults key={lookup.id} lookup={lookup as any} />
          ))}
        </ResultSection>
      )}

      {holeheLookups.length > 0 && (
        <ResultSection
          title='Email Account Discovery'
          icon={<Mail className='h-4 w-4' />}
          count={holeheLookups.length}
        >
          {holeheLookups.map((lookup) => (
            <HoleheResults key={lookup.id} lookup={lookup as any} />
          ))}
        </ResultSection>
      )}

      {phoneLookups.length > 0 && (
        <ResultSection
          title='Phone Lookups'
          icon={<Phone className='h-4 w-4' />}
          count={phoneLookups.length}
        >
          {phoneLookups.map((lookup) => (
            <PhoneResults key={lookup.id} lookup={lookup as any} />
          ))}
        </ResultSection>
      )}

      {dorkingLookups.length > 0 && (
        <ResultSection
          title='Web Survey (Dorking)'
          icon={<Globe className='h-4 w-4' />}
          count={dorkingLookups.length}
        >
          {dorkingLookups.map((lookup) => (
            <DorkingResults
              key={lookup.id}
              lookup={lookup as any}
              caseId={caseId}
              onAccountImported={() => {
                fetchLookups()
                onAccountImported?.()
              }}
            />
          ))}
        </ResultSection>
      )}
    </div>
  )
}

function ResultSection({
  title,
  icon,
  count,
  children,
}: {
  title: string
  icon: React.ReactNode
  count: number
  children: React.ReactNode
}) {
  return (
    <Collapsible defaultOpen>
      <Card>
        <CollapsibleTrigger asChild>
          <CardHeader className='cursor-pointer pb-3 transition-colors hover:bg-muted/30'>
            <div className='flex items-center justify-between'>
              <div className='flex items-center gap-2'>
                {icon}
                <CardTitle className='text-base'>{title}</CardTitle>
                <Badge variant='secondary'>{count}</Badge>
              </div>
              <ChevronDown className='h-4 w-4 text-muted-foreground transition-transform [[data-state=closed]_&]:rotate-[-90deg]' />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className='space-y-3 pt-0'>{children}</CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
