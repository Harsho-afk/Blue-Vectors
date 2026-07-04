import { createFileRoute, redirect } from '@tanstack/react-router'
import { useAuthStore } from '@/stores/auth-store'
import { SignUp } from '@/features/auth/sign-up'

export const Route = createFileRoute('/(auth)/sign-up')({
  beforeLoad: () => {
    const { user, isLoading } = useAuthStore.getState()
    if (!isLoading && user) {
      throw redirect({ to: '/' })
    }
  },
  component: SignUp,
})
