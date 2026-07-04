import { useState } from 'react'
import { z } from 'zod'
import { useFieldArray, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Loader2, Plus, X } from 'lucide-react'
import { API } from '@/lib/aria-api'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ConfigDrawer } from '@/components/config-drawer'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Header } from '@/components/layout/header'
import { Input } from '@/components/ui/input'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ThemeSwitch } from '@/components/theme-switch'

export const Route = createFileRoute('/_authenticated/investigate/')({
  component: NewInvestigation,
})

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

const formSchema = z.object({
  title: z.string().min(1, 'Case title is required.').max(255),
  identifiers: z.array(
    z.object({
      identifier_type: z.enum(['username', 'email', 'phone', 'profile_url']),
      value: z.string(),
      platform_hint: z.string(),
    })
  ),
})

type FormValues = z.infer<typeof formSchema>

function NewInvestigation() {
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      title: '',
      identifiers: [
        { identifier_type: 'username', value: '', platform_hint: '' },
      ],
    },
  })

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'identifiers',
  })

  async function onSubmit(data: FormValues) {
    const cleaned = data.identifiers
      .filter((row) => row.value.trim() !== '')
      .map((row) => ({
        identifier_type: row.identifier_type,
        value: row.value.trim(),
        platform_hint:
          row.identifier_type === 'username' &&
          row.platform_hint &&
          row.platform_hint !== 'none'
            ? row.platform_hint
            : null,
      }))

    if (cleaned.length === 0) {
      setSubmitError('Add at least one identifier with a value')
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)

    try {
      const res = await fetch(`${API}/api/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ title: data.title.trim(), identifiers: cleaned }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(
          err.detail ||
            (typeof err === 'string' ? err : 'Failed to create case')
        )
      }
      const result = await res.json()
      navigate({
        to: '/cases/$id',
        params: { id: String(result.case_id) },
      })
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to create case')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <Header>
        <Search className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main>
        <div className='mb-2'>
          <h1 className='text-2xl font-bold tracking-tight'>
            New Investigation
          </h1>
          <p className='text-muted-foreground'>
            Create a case and add seed identifiers to begin
          </p>
        </div>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className='mx-auto mt-4 max-w-3xl space-y-4'
          >
            {/* Card 1 — Case Details */}
            <Card>
              <CardHeader>
                <CardTitle>Case Details</CardTitle>
                <CardDescription>
                  Give this investigation a descriptive title
                </CardDescription>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name='title'
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Case Title</FormLabel>
                      <FormControl>
                        <Input
                          placeholder='e.g. Cross-platform analysis — johndoe'
                          disabled={isSubmitting}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            {/* Card 2 — Seed Identifiers */}
            <Card>
              <CardHeader>
                <CardTitle>Seed Identifiers</CardTitle>
                <CardDescription>
                  Add usernames, emails, or other identifiers to investigate
                </CardDescription>
              </CardHeader>
              <CardContent className='space-y-3'>
                {fields.map((field, index) => {
                  const identifierType = form.watch(
                    `identifiers.${index}.identifier_type`
                  )
                  return (
                    <div key={field.id} className='flex items-start gap-2'>
                      <FormField
                        control={form.control}
                        name={`identifiers.${index}.identifier_type`}
                        render={({ field }) => (
                          <FormItem className='w-[140px] shrink-0'>
                            {index === 0 && <FormLabel>Type</FormLabel>}
                            <Select
                              onValueChange={field.onChange}
                              value={field.value}
                              disabled={isSubmitting}
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {IDENTIFIER_TYPES.map((t) => (
                                  <SelectItem key={t.value} value={t.value}>
                                    {t.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name={`identifiers.${index}.value`}
                        render={({ field }) => (
                          <FormItem className='min-w-0 flex-1'>
                            {index === 0 && <FormLabel>Value</FormLabel>}
                            <FormControl>
                              <Input
                                placeholder={
                                  PLACEHOLDERS[identifierType] || 'Value'
                                }
                                disabled={isSubmitting}
                                {...field}
                              />
                            </FormControl>
                          </FormItem>
                        )}
                      />

                      {identifierType === 'username' && (
                        <FormField
                          control={form.control}
                          name={`identifiers.${index}.platform_hint`}
                          render={({ field }) => (
                            <FormItem className='w-[140px] shrink-0'>
                              {index === 0 && <FormLabel>Platform</FormLabel>}
                              <Select
                                onValueChange={field.onChange}
                                value={field.value}
                                disabled={isSubmitting}
                              >
                                <FormControl>
                                  <SelectTrigger>
                                    <SelectValue placeholder='No Platform' />
                                  </SelectTrigger>
                                </FormControl>
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
                            </FormItem>
                          )}
                        />
                      )}

                      {fields.length > 1 && (
                        <Button
                          type='button'
                          variant='outline'
                          size='icon'
                          className={index === 0 ? 'mt-7' : 'mt-0'}
                          disabled={isSubmitting}
                          onClick={() => remove(index)}
                        >
                          <X className='h-4 w-4' />
                        </Button>
                      )}
                    </div>
                  )
                })}

                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='mt-2'
                  disabled={isSubmitting}
                  onClick={() =>
                    append({
                      identifier_type: 'username',
                      value: '',
                      platform_hint: '',
                    })
                  }
                >
                  <Plus className='h-4 w-4' />
                  Add Identifier
                </Button>

                <p className='text-xs text-muted-foreground'>
                  At least one identifier required. Empty rows are ignored on
                  submit.
                </p>
              </CardContent>
            </Card>

            {/* Submit */}
            {submitError && (
              <div className='rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive'>
                {submitError}
              </div>
            )}

            <div className='flex justify-end'>
              <Button type='submit' disabled={isSubmitting}>
                {isSubmitting ? (
                  <Loader2 className='animate-spin' />
                ) : (
                  <Plus />
                )}
                {isSubmitting ? 'Creating...' : 'Create Case'}
              </Button>
            </div>
          </form>
        </Form>
      </Main>
    </>
  )
}
