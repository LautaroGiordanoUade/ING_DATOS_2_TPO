import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { getUserProfile } from '../recommendations/api'

export function Person({ id }: { id: string }) {
  const { request } = useAuth()
  const profile = useQuery({ queryKey: ['users', 'profile', id], queryFn: ({ signal }) => getUserProfile(request, id, signal), retry: false, staleTime: 60_000 })
  return <Link to={`/perfiles/${id}`}>{profile.data?.full_name ?? (profile.isPending ? 'Cargando cuenta…' : 'Cuenta no disponible')}</Link>
}
