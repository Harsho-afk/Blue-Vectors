import { create } from 'zustand'
import { API } from '@/lib/aria-api'

interface AuthUser {
  id: number
  email: string
  full_name: string
  role: string
}

interface AuthState {
  user: AuthUser | null
  isLoading: boolean
  init: () => Promise<void>
  login: (userData: AuthUser) => void
  logout: () => Promise<void>
  reset: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  isLoading: true,

  init: async () => {
    try {
      const res = await fetch(`${API}/api/auth/me`, { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        set({ user: data, isLoading: false })
      } else {
        set({ user: null, isLoading: false })
      }
    } catch {
      set({ user: null, isLoading: false })
    }
  },

  login: (userData) => set({ user: userData }),

  logout: async () => {
    await fetch(`${API}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    }).catch(() => {})
    set({ user: null })
  },

  reset: () => set({ user: null }),
}))
