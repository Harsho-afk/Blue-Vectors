import { beforeEach, describe, expect, it, vi } from 'vitest'

async function importAuthStore() {
  const { useAuthStore } = await import('./auth-store')
  return useAuthStore
}

const sampleUser = {
  id: 1,
  email: 'user@example.com',
  full_name: 'Test User',
  role: 'user',
}

describe('useAuthStore', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('starts with null user and isLoading true', async () => {
    const useAuthStore = await importAuthStore()

    expect(useAuthStore.getState().user).toBeNull()
    expect(useAuthStore.getState().isLoading).toBe(true)
  })

  it('sets user via login', async () => {
    const useAuthStore = await importAuthStore()

    useAuthStore.getState().login({ ...sampleUser })

    expect(useAuthStore.getState().user).toEqual(sampleUser)
  })

  it('reset clears user', async () => {
    const useAuthStore = await importAuthStore()
    useAuthStore.getState().login({ ...sampleUser })

    useAuthStore.getState().reset()

    expect(useAuthStore.getState().user).toBeNull()
  })
})
