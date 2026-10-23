import type { AuthRequest } from '../auth/api'
import { userSchema, type User } from '../auth/contracts'
import { uuidListSchema, type UuidList } from './contracts'

export async function getRecommendations(
  request: AuthRequest,
  userId: string,
  signal?: AbortSignal,
): Promise<UuidList> {
  const data = await request(`/api/v1/problems/4/recommendations/${userId}`, {
    ...(signal ? { signal } : {}),
  })
  return uuidListSchema.parse(data)
}

export async function getMutualFriends(
  request: AuthRequest,
  userId: string,
  otherUserId: string,
  signal?: AbortSignal,
): Promise<UuidList> {
  const data = await request(
    `/api/v1/problems/4/mutual-friends?user_id=${encodeURIComponent(userId)}&other_user_id=${encodeURIComponent(otherUserId)}`,
    {
      ...(signal ? { signal } : {}),
    },
  )
  return uuidListSchema.parse(data)
}

export async function getUserProfile(
  request: AuthRequest,
  userId: string,
  signal?: AbortSignal,
): Promise<User> {
  const data = await request(`/api/v1/users/${userId}`, {
    ...(signal ? { signal } : {}),
  })
  return userSchema.parse(data)
}
