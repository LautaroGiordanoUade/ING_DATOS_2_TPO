import { z } from 'zod'
import type { AuthRequest } from '../auth/api'
import { postSchema, type Post } from '../posts/contracts'

export const feedSchema = z.object({ items: z.array(postSchema).max(20), next_cursor: z.string().nullable() })
export type FeedPage = z.infer<typeof feedSchema>

export async function getFeed(request: AuthRequest, userId: string, cursor: string | null, signal: AbortSignal): Promise<FeedPage> {
  const query = cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`
  return feedSchema.parse(await request(`/api/v1/feeds/${userId}${query}`, { signal }))
}

export function uniquePosts(pages: FeedPage[]): Post[] {
  // Preserve server order; a repeated ID updates its values without moving its position.
  const posts = new Map<string, Post>()
  for (const page of pages) for (const post of page.items) posts.set(post.id, post)
  return [...posts.values()]
}
