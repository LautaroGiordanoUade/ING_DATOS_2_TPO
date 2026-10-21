import type { PropsWithChildren } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthContext, type AuthState } from '../../src/features/auth/context'
import type { AuthRequest } from '../../src/features/auth/api'

export const user = {
  id: '11000000-0000-4000-8000-000000000001', username: 'qa_p1', full_name: 'QA Niche', biography: null,
  account_type: 'public' as const, account_status: 'active' as const, role: 'user' as const, registered_at: '2026-10-21T12:00:00Z',
}
export const postId = '22000000-0000-4000-8000-000000000001'
export const operationId = '33000000-0000-4000-8000-000000000001'
export function sessionWrapper(request: AuthRequest, overrides: Partial<AuthState> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const auth: AuthState = { user, status: 'authenticated', error: null, request, signIn: async () => {}, signOut: () => {}, retry: () => {}, ...overrides }
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}><AuthContext.Provider value={auth}>{children}</AuthContext.Provider></QueryClientProvider>
  }
}
