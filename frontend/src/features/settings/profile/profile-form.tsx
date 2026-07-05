import { useEffect } from 'react'
import { z } from 'zod'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '@/context/auth-context'
import { API } from '@/lib/aria-api'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'

const profileFormSchema = z.object({
  username: z
    .string('Please enter your name.')
    .min(2, 'Name must be at least 2 characters.')
    .max(30, 'Name must not be longer than 30 characters.'),
  email: z.string().email(),
})

type ProfileFormValues = z.infer<typeof profileFormSchema>

export function ProfileForm() {
  const { user, login } = useAuth()

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: {
      username: user?.full_name || '',
      email: user?.email || '',
    },
    mode: 'onChange',
  })

  // Keep form fields synced if user info changes or loads late
  useEffect(() => {
    if (user) {
      form.reset({
        username: user.full_name || '',
        email: user.email || '',
      })
    }
  }, [user, form.reset])

  async function onSubmit(data: ProfileFormValues) {
    try {
      const res = await fetch(`${API}/api/auth/profile`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ full_name: data.username }),
        credentials: 'include',
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to update profile')
      }

      const updatedUser = await res.json()
      login(updatedUser) // Update authentication store immediately
      toast.success('Investigator profile updated successfully!')
    } catch (e: any) {
      toast.error(e.message || 'Failed to update profile')
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className='space-y-8'>
        <FormField
          control={form.control}
          name='username'
          render={({ field }) => (
            <FormItem>
              <FormLabel>Investigator Name</FormLabel>
              <FormControl>
                <Input placeholder='Enter your full name' {...field} />
              </FormControl>
              <FormDescription>
                This name will appear on all generated investigation reports.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name='email'
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email Address</FormLabel>
              <FormControl>
                <Input disabled {...field} />
              </FormControl>
              <FormDescription>
                Your email is used to log in and cannot be edited.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type='submit' disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? 'Updating...' : 'Update profile'}
        </Button>
      </form>
    </Form>
  )
}
