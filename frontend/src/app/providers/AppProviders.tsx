import { useState, type PropsWithChildren } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

export function AppProviders({ children }: PropsWithChildren) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000, refetchOnWindowFocus: false } },
  }))
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
