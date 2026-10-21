import { z } from 'zod'
import { ApiError, http } from '../../services/http/client'
import type { components } from '../../services/api/schema'

const readinessSchema = z.object({
  status: z.enum(['ready', 'degraded']),
  services: z.object({ mongodb: z.string(), redis: z.string(), neo4j: z.string() }),
})
export type Readiness = z.infer<typeof readinessSchema>

export async function getReadiness(signal?: AbortSignal): Promise<Readiness> {
  try {
    const body = await http<components['schemas']['ReadinessResponse']>('/health/ready', signal ? { signal } : {})
    return readinessSchema.parse(body)
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      const degraded = readinessSchema.safeParse(error.payload)
      if (degraded.success && degraded.data.status === 'degraded') return degraded.data
    }
    if (error instanceof z.ZodError) throw new Error('El servidor devolvió un estado de conexión inesperado.')
    throw error
  }
}
